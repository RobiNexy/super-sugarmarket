"""@purpose Verify checkout stock reservations, neural pricing tiers, and order persistence.
@spec [[checkout-cart-and-order]]
@covers Addend expansion, tier selection, free orders, partial stock, skipped items, validation.
"""

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from fastapi import FastAPI

from app.checkout import DEFAULT_ONNX_PATH
from app.main import create_app


class ExactPredictor:
    def predict(
        self, matrix: np.ndarray[Any, Any]
    ) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
        batch_size = matrix.shape[0]
        digits = np.zeros((batch_size, 8), dtype=np.int64)
        carries = np.zeros((batch_size, 8), dtype=np.int64)
        powers = [10**position for position in range(8)]
        for batch_index in range(batch_size):
            total = sum(
                int(sum(int(matrix[batch_index, row, digit] * powers[digit]) for digit in range(8)))
                for row in range(10)
            )
            digits[batch_index] = [(total // power) % 10 for power in powers]
        return digits, carries


class FixedPredictor:
    def __init__(self, amount_fen: int) -> None:
        self.amount_fen = amount_fen

    def predict(
        self, matrix: np.ndarray[Any, Any]
    ) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
        batch_size = matrix.shape[0]
        digits = np.zeros((batch_size, 8), dtype=np.int64)
        for position in range(8):
            digits[:, position] = (self.amount_fen // (10**position)) % 10
        return digits, np.zeros((batch_size, 8), dtype=np.int64)


class BrokenPredictor:
    def predict(
        self, matrix: np.ndarray[Any, Any]
    ) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
        raise RuntimeError("model inference failed")


def request(
    app: FastAPI, method: str, path: str, body: dict[str, Any] | None = None
) -> httpx.Response:
    async def run() -> httpx.Response:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.request(method, path, json=body)

    return asyncio.run(run())


def checkout_app(tmp_path: Path, predictor: Any | None = None) -> FastAPI:
    return create_app(tmp_path / "checkout.sqlite3", predictor or ExactPredictor())


def test_checkout_expands_multiplication_and_persists_order(tmp_path: Path) -> None:
    app = checkout_app(tmp_path)

    response = request(
        app,
        "POST",
        "/api/checkout",
        {"room_no": " 1208 ", "items": [{"product_id": 1, "quantity": 4}]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["room_no"] == "1208"
    assert body["total_yuan"] == "8.00"
    assert body["exact_yuan"] == "8.00"
    assert body["tier"] == "none"
    assert body["status"] == "pending"

    products = request(app, "GET", "/api/products").json()
    water = next(product for product in products if product["id"] == 1)
    assert water["stock_quantity"] == 12
    assert water["available_quantity"] == 8


def test_checkout_uses_model_total_and_second_tier_only_above_twenty_percent(
    tmp_path: Path,
) -> None:
    exact_boundary = checkout_app(tmp_path / "boundary", FixedPredictor(240))
    boundary_response = request(
        exact_boundary,
        "POST",
        "/api/checkout",
        {"room_no": "1", "items": [{"product_id": 1, "quantity": 1}]},
    )
    assert boundary_response.json()["tier"] == "none"
    assert boundary_response.json()["total_yuan"] == "2.40"

    over_boundary = checkout_app(tmp_path / "over", FixedPredictor(241))
    over_response = request(
        over_boundary,
        "POST",
        "/api/checkout",
        {"room_no": "1", "items": [{"product_id": 1, "quantity": 1}]},
    )
    assert over_response.json()["tier"] == "tier2_wild"
    assert over_response.json()["total_yuan"] == "2.41"


def test_zero_reference_uses_special_tier(tmp_path: Path) -> None:
    database_path = tmp_path / "zero.sqlite3"
    from app.database import initialize_database

    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE products SET unit_price_fen = 0, stock_quantity = 1 WHERE id = 1"
        )
    app = create_app(database_path, FixedPredictor(1))
    response = request(
        app,
        "POST",
        "/api/checkout",
        {"room_no": "1", "items": [{"product_id": 1, "quantity": 1}]},
    )

    assert response.status_code == 201
    assert response.json()["tier"] == "zero_compare"
    assert response.json()["total_yuan"] == "0.01"


@pytest.mark.parametrize("predictor", [None, "broken"])
def test_null_or_inference_error_creates_free_order(tmp_path: Path, predictor: Any) -> None:
    selected = BrokenPredictor() if predictor == "broken" else ExactPredictor()
    app = checkout_app(tmp_path, selected)
    if predictor is None:
        class NullPredictor:
            def predict(self, matrix: np.ndarray[Any, Any]) -> tuple[None, None]:
                return None, None

        app = checkout_app(tmp_path / "null", NullPredictor())

    response = request(
        app,
        "POST",
        "/api/checkout",
        {"room_no": "1", "items": [{"product_id": 1, "quantity": 1}]},
    )

    assert response.status_code == 201
    assert response.json()["tier"] == "tier3_free"
    assert response.json()["total_yuan"] == "0.00"


def test_partial_stock_is_taken_and_unavailable_products_are_skipped(tmp_path: Path) -> None:
    app = checkout_app(tmp_path)
    response = request(
        app,
        "POST",
        "/api/checkout",
        {
            "room_no": "1208",
            "items": [
                {"product_id": 1, "quantity": 99},
                {"product_id": 19, "quantity": 1},
            ],
        },
    )

    body = response.json()
    assert response.status_code == 201
    assert body["adjustments"] == [
        {"product_id": 1, "name": "农夫山泉 550ml", "requested": 99, "taken": 12}
    ]
    assert body["skipped"] == [
        {"product_id": 19, "name": "创可贴 草莓款", "reason": "sold_out"}
    ]
    assert body["total_yuan"] == "24.00"


def test_all_unavailable_returns_friendly_error_without_creating_order(tmp_path: Path) -> None:
    app = checkout_app(tmp_path)
    response = request(
        app,
        "POST",
        "/api/checkout",
        {"room_no": "1208", "items": [{"product_id": 19, "quantity": 1}]},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "NO_PURCHASABLE"
    assert "🥺" in response.json()["message"]


def test_room_validation_and_addend_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = checkout_app(tmp_path)
    empty_room = request(
        app,
        "POST",
        "/api/checkout",
        {"room_no": "   ", "items": [{"product_id": 1, "quantity": 1}]},
    )
    assert empty_room.status_code == 422
    assert empty_room.json()["code"] == "ROOM_REQUIRED"

    import app.checkout as checkout

    monkeypatch.setattr(checkout, "MAX_ADDENDS", 1)
    over_cap = request(
        app,
        "POST",
        "/api/checkout",
        {"room_no": "1", "items": [{"product_id": 1, "quantity": 2}]},
    )
    assert over_cap.status_code == 422
    assert over_cap.json()["code"] == "TOO_MANY_ADDENDS"


@pytest.mark.skipif(not DEFAULT_ONNX_PATH.exists(), reason="local ignored ONNX artifact is absent")
def test_checkout_uses_the_configured_onnx_artifact(tmp_path: Path) -> None:
    app = create_app(tmp_path / "onnx-checkout.sqlite3")
    response = request(
        app,
        "POST",
        "/api/checkout",
        {"room_no": "1208", "items": [{"product_id": 1, "quantity": 1}]},
    )

    assert response.status_code == 201
    assert response.json()["total_yuan"] == "2.00"
    assert response.json()["tier"] == "none"
