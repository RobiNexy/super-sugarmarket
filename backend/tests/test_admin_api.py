"""@purpose Verify back-office order completion and product maintenance APIs.
@spec [[admin-backoffice]]
@covers One-time stock deduction, transaction rollback, admin listing, product CRUD and Emoji art.
"""

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from fastapi import FastAPI

from app.database import initialize_database
from app.main import create_app


class ExactPredictor:
    def predict(
        self, matrix: np.ndarray[Any, Any]
    ) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
        batch_size = matrix.shape[0]
        digits = np.zeros((batch_size, 8), dtype=np.int64)
        for batch_index in range(batch_size):
            total = sum(
                int(matrix[batch_index, row, digit]) * 10**digit
                for row in range(10)
                for digit in range(8)
            )
            digits[batch_index] = [(total // (10**position)) % 10 for position in range(8)]
        return digits, np.zeros((batch_size, 8), dtype=np.int64)


def run_request(
    app: FastAPI,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> httpx.Response:
    async def run() -> httpx.Response:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.request(method, path, json=body)

    return asyncio.run(run())


def seed_order(database_path: Path, quantity: int = 2) -> None:
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO orders (
                room_no, status, tier, total_fen, model_fen, exact_fen, addend_count, created_at
            ) VALUES ('1208', 'pending', 'none', 400, 400, 400, 2, '2026-10-17T00:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO order_items (
                order_id, product_id, product_name, unit_price_fen, quantity
            ) VALUES (?, 1, '农夫山泉 550ml', 200, ?)
            """,
            (cursor.lastrowid, quantity),
        )


def test_admin_completes_order_and_deducts_stock_exactly_once(tmp_path: Path) -> None:
    database_path = tmp_path / "admin.sqlite3"
    seed_order(database_path)
    app = create_app(database_path, ExactPredictor())

    orders = run_request(app, "GET", "/api/admin/orders")
    assert orders.status_code == 200
    assert orders.json()[0]["room_no"] == "1208"
    assert orders.json()[0]["items"][0]["unit_price_yuan"] == "2.00"

    completed = run_request(app, "POST", "/api/admin/orders/1/complete")
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None

    products = run_request(app, "GET", "/api/admin/products").json()
    water = next(product for product in products if product["id"] == 1)
    assert water["stock_quantity"] == 10
    assert run_request(app, "POST", "/api/admin/orders/1/complete").status_code == 409
    products_again = run_request(app, "GET", "/api/admin/products").json()
    assert next(product for product in products_again if product["id"] == 1)["stock_quantity"] == 10


def test_admin_rejects_completion_without_mutating_stock_or_order(tmp_path: Path) -> None:
    database_path = tmp_path / "admin.sqlite3"
    seed_order(database_path, quantity=13)
    app = create_app(database_path, ExactPredictor())

    response = run_request(app, "POST", "/api/admin/orders/1/complete")

    assert response.status_code == 409
    assert response.json()["code"] == "INSUFFICIENT_STOCK"
    with sqlite3.connect(database_path) as connection:
        stock, status = connection.execute(
            """
            SELECT p.stock_quantity, o.status
            FROM products AS p JOIN orders AS o ON o.id = 1 WHERE p.id = 1
            """
        ).fetchone()
    assert stock == 12
    assert status == "pending"


def test_admin_creates_and_updates_product_with_composed_emoji_art(tmp_path: Path) -> None:
    database_path = tmp_path / "admin.sqlite3"
    app = create_app(database_path, ExactPredictor())
    art = {
        "version": 1,
        "layers": [
            {
                "emoji": "🍓", "x": 50.0, "y": 55.0, "size": 60.0, "rotate": -10.0,
                "scale_x": 1.1, "scale_y": 0.9, "z": 1, "clip": None,
            },
            {
                "emoji": "🍃", "x": 64.0, "y": 22.0, "size": 30.0, "rotate": 30.0,
                "scale_x": 0.8, "scale_y": 1.2, "z": 2, "clip": "ellipse",
            },
        ],
    }
    created = run_request(
        app,
        "POST",
        "/api/admin/products",
        {
            "name": "草莓叶子小饮料",
            "category": "饮品",
            "description": "酸甜小可爱 🍓",
            "emoji": "🍓🍃",
            "emoji_art": art,
            "unit_price_yuan": "3.50",
            "stock_quantity": 5,
            "is_active": True,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["unit_price_yuan"] == "3.50"
    assert len(body["emoji_art"]["layers"]) == 2

    updated = run_request(
        app,
        "PATCH",
        f"/api/admin/products/{body['id']}",
        {"unit_price_yuan": "12.34", "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["unit_price_yuan"] == "12.34"
    assert updated.json()["is_active"] is False
    assert isinstance(updated.json()["emoji_art"], dict)


def test_admin_price_rejects_more_than_two_decimal_places(tmp_path: Path) -> None:
    app = create_app(tmp_path / "admin.sqlite3", ExactPredictor())
    response = run_request(
        app,
        "POST",
        "/api/admin/products",
        {
            "name": "坏掉的小数",
            "category": "零食",
            "description": "价格写太细啦 🪙",
            "unit_price_yuan": "12.345",
            "stock_quantity": 1,
        },
    )

    assert response.status_code == 422
