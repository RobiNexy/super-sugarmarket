"""@purpose Validate checkout requests, neural totals, and transactional stock availability.
@spec [[checkout-cart-and-order]]
@invariants Product prices are re-read from SQLite; only model output becomes the order total;
pending orders reserve stock until completed.
@adr [[ADR-0006-checkout-room-identity-and-stock-reservation]]
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from adder.onnx_runtime import OnnxAdder
from adder.tree_sum import MAX_ROW, tree_sum

MAX_CART_LINES = 50
MAX_QUANTITY_PER_LINE = 99
MAX_ADDENDS = 1000
DEFAULT_ONNX_PATH = (
    Path(__file__).resolve().parents[1] / "checkpoints" / "adder-onnx" / "adder.onnx"
)


class CheckoutLine(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=MAX_QUANTITY_PER_LINE)


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    room_no: str
    items: list[CheckoutLine]

    @field_validator("room_no")
    @classmethod
    def strip_room_number(cls, value: str) -> str:
        return value.strip()


class StockAdjustment(BaseModel):
    product_id: int
    name: str
    requested: int
    taken: int


class SkippedProduct(BaseModel):
    product_id: int
    name: str
    reason: str


class CheckoutResponse(BaseModel):
    order_id: int
    status: str
    room_no: str
    total_yuan: str
    exact_yuan: str
    tier: str
    adjustments: list[StockAdjustment]
    skipped: list[SkippedProduct]


class CheckoutFailure(Exception):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


class Predictor(Protocol):
    def predict(self, matrix: Any) -> tuple[Any, Any]: ...


ERROR_MESSAGES = {
    "ROOM_REQUIRED": "房间号要填哦～🚪",
    "ROOM_TOO_LONG": "房间号太长啦，缩短一点吧 🏠",
    "INVALID_QUANTITY": "数量要在 1 到 99 之间哦 🔢",
    "TOO_MANY_LINES": "购物车行数有点多，分几次挑吧 🧺",
    "NO_PURCHASABLE": "购物车空空如也，或者货都被抢光啦～🥺",
    "TOO_MANY_ADDENDS": "你不如把我店盘下来 🏪💸",
    "INVALID_REQUEST": "结账信息好像写歪啦，请检查后再试哦 🧾",
    "INTERNAL_ERROR": "订单没有存好，请稍等一下再试哦 🐿️",
}


def format_yuan(fen: int) -> str:
    """Format integer fen without floating-point arithmetic."""
    return f"{fen // 100}.{fen % 100:02d}"


def validation_error_response(error: RequestValidationError) -> JSONResponse:
    """Translate request-body validation failures into the documented error shape."""
    errors = error.errors()
    locations = [tuple(item.get("loc", ())) for item in errors]
    if any("room_no" in location for location in locations):
        code = "ROOM_REQUIRED"
    elif any("quantity" in location or "product_id" in location for location in locations):
        code = "INVALID_QUANTITY"
    else:
        code = "INVALID_REQUEST"
    return JSONResponse(
        status_code=422,
        content={"code": code, "message": ERROR_MESSAGES[code]},
    )


def checkout_validation_handler(_: Request, error: Exception) -> JSONResponse:
    if isinstance(error, RequestValidationError):
        return validation_error_response(error)
    return JSONResponse(
        status_code=422,
        content={"code": "INVALID_REQUEST", "message": ERROR_MESSAGES["INVALID_REQUEST"]},
    )


def build_checkout_router(
    database_path: Path,
    predictor_factory: Callable[[], Predictor],
) -> APIRouter:
    router = APIRouter()

    def create_checkout(payload: CheckoutRequest) -> CheckoutResponse:
        try:
            return create_order(database_path, payload, predictor_factory)
        except CheckoutFailure as error:
            return JSONResponse(  # type: ignore[return-value]
                status_code=error.status_code,
                content={"code": error.code, "message": ERROR_MESSAGES[error.code]},
            )
        except sqlite3.Error:
            return JSONResponse(  # type: ignore[return-value]
                status_code=500,
                content={"code": "INTERNAL_ERROR", "message": ERROR_MESSAGES["INTERNAL_ERROR"]},
            )

    router.add_api_route(
        "/api/checkout",
        create_checkout,
        methods=["POST"],
        response_model=CheckoutResponse,
        status_code=201,
    )
    return router


def create_order(
    database_path: Path,
    payload: CheckoutRequest,
    predictor_factory: Callable[[], Predictor],
) -> CheckoutResponse:
    room_no = payload.room_no
    if not room_no:
        raise CheckoutFailure(422, "ROOM_REQUIRED")
    if len(room_no) > 10:
        raise CheckoutFailure(422, "ROOM_TOO_LONG")
    if len(payload.items) > MAX_CART_LINES:
        raise CheckoutFailure(422, "TOO_MANY_LINES")

    merged: dict[int, int] = {}
    for item in payload.items:
        merged[item.product_id] = merged.get(item.product_id, 0) + item.quantity
        if merged[item.product_id] > MAX_QUANTITY_PER_LINE:
            raise CheckoutFailure(422, "INVALID_QUANTITY")

    with closing(sqlite3.connect(database_path, timeout=10)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        try:
            adjustments: list[StockAdjustment] = []
            skipped: list[SkippedProduct] = []
            purchasable: list[tuple[int, str, int, int]] = []

            for product_id, requested in merged.items():
                product = connection.execute(
                    """
                    SELECT p.id, p.name, p.unit_price_fen, p.stock_quantity, p.is_active,
                           COALESCE((
                               SELECT SUM(oi.quantity)
                               FROM order_items AS oi
                               JOIN orders AS o ON o.id = oi.order_id
                               WHERE oi.product_id = p.id AND o.status = 'pending'
                           ), 0) AS pending_quantity
                    FROM products AS p
                    WHERE p.id = ?
                    """,
                    (product_id,),
                ).fetchone()

                if product is None:
                    skipped.append(
                        SkippedProduct(product_id=product_id, name="未知商品", reason="not_found")
                    )
                    continue
                if not bool(product["is_active"]):
                    skipped.append(
                        SkippedProduct(
                            product_id=product_id,
                            name=str(product["name"]),
                            reason="inactive",
                        )
                    )
                    continue

                price_fen = int(product["unit_price_fen"])
                if price_fen < 0 or price_fen > MAX_ROW:
                    raise CheckoutFailure(422, "INVALID_REQUEST")
                available = max(
                    0, int(product["stock_quantity"]) - int(product["pending_quantity"])
                )
                taken = min(requested, available)
                if taken == 0:
                    skipped.append(
                        SkippedProduct(
                            product_id=product_id,
                            name=str(product["name"]),
                            reason="sold_out",
                        )
                    )
                    continue
                if taken < requested:
                    adjustments.append(
                        StockAdjustment(
                            product_id=product_id,
                            name=str(product["name"]),
                            requested=requested,
                            taken=taken,
                        )
                    )
                purchasable.append((product_id, str(product["name"]), price_fen, taken))

            if not purchasable:
                raise CheckoutFailure(422, "NO_PURCHASABLE")

            addend_count = sum(quantity for _, _, _, quantity in purchasable)
            if addend_count > MAX_ADDENDS:
                raise CheckoutFailure(422, "TOO_MANY_ADDENDS")

            addends = [
                price_fen
                for _, _, price_fen, quantity in purchasable
                for _ in range(quantity)
            ]
            exact_fen = sum(addends)
            try:
                model_value: Any = tree_sum(addends, predictor_factory())
                if model_value is not None and (
                    not isinstance(model_value, int)
                    or isinstance(model_value, bool)
                    or model_value < 0
                ):
                    raise ValueError("adder returned an invalid amount")
                model_fen = model_value
            except Exception:
                # Null and any inference failure deliberately create a free order.
                model_fen = None

            if model_fen is None:
                tier = "tier3_free"
                total_fen = 0
            elif exact_fen == 0 and model_fen != 0:
                tier = "zero_compare"
                total_fen = model_fen
            elif exact_fen > 0 and 5 * abs(model_fen - exact_fen) > exact_fen:
                tier = "tier2_wild"
                total_fen = model_fen
            else:
                tier = "none"
                total_fen = model_fen

            created_at = datetime.now(UTC).isoformat()
            cursor = connection.execute(
                """
                INSERT INTO orders (
                    room_no, status, tier, total_fen, model_fen, exact_fen,
                    addend_count, created_at
                ) VALUES (?, 'pending', ?, ?, ?, ?, ?, ?)
                """,
                (room_no, tier, total_fen, model_fen, exact_fen, addend_count, created_at),
            )
            if cursor.lastrowid is None:
                raise sqlite3.IntegrityError("SQLite did not return an order id")
            order_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO order_items (
                    order_id, product_id, product_name, unit_price_fen, quantity
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (order_id, product_id, name, price_fen, quantity)
                    for product_id, name, price_fen, quantity in purchasable
                ],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return CheckoutResponse(
        order_id=order_id,
        status="pending",
        room_no=room_no,
        total_yuan=format_yuan(total_fen),
        exact_yuan=format_yuan(exact_fen),
        tier=tier,
        adjustments=adjustments,
        skipped=skipped,
    )


def default_predictor_factory() -> Predictor:
    """Load the local ONNX artifact; inference failures become free orders."""
    return OnnxAdder(DEFAULT_ONNX_PATH, threads=1)
