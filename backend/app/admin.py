"""@purpose Provide local, unauthenticated back-office APIs for orders and products.
@spec [[admin-backoffice]]
@invariants Completing an order decrements stock exactly once in the same SQLite transaction.
@adr [[ADR-0006-checkout-room-identity-and-stock-reservation]]
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .money import format_yuan
from .products import EmojiArt

MAX_PRICE_FEN = 9_999_999
PRICE_PATTERN = re.compile(r"^\d{1,5}(?:\.\d{1,2})?$")


class AdminFailure(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message


class OrderItemRead(BaseModel):
    product_id: int
    name: str
    unit_price_yuan: str
    quantity: int


class OrderRead(BaseModel):
    id: int
    room_no: str
    status: Literal["pending", "completed"]
    total_yuan: str
    tier: str
    created_at: str
    completed_at: str | None
    items: list[OrderItemRead]


class ProductWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=500)
    emoji: str | None = Field(default=None, max_length=32)
    emoji_art: EmojiArt | None = None
    unit_price_yuan: str
    stock_quantity: int = Field(ge=0, le=1_000_000)
    is_active: bool = True

    @field_validator("name", "category", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("emoji")
    @classmethod
    def strip_emoji(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("unit_price_yuan")
    @classmethod
    def validate_yuan(cls, value: str) -> str:
        if not PRICE_PATTERN.fullmatch(value):
            raise ValueError("price must have at most two decimal places")
        fen = parse_yuan(value)
        if fen > MAX_PRICE_FEN:
            raise ValueError("price exceeds model input maximum")
        return format_yuan(fen)


class ProductPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, min_length=1, max_length=500)
    emoji: str | None = Field(default=None, max_length=32)
    emoji_art: EmojiArt | None = None
    unit_price_yuan: str | None = None
    stock_quantity: int | None = Field(default=None, ge=0, le=1_000_000)
    is_active: bool | None = None

    @field_validator("name", "category", "description")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("emoji")
    @classmethod
    def strip_emoji(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("unit_price_yuan")
    @classmethod
    def validate_yuan(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not PRICE_PATTERN.fullmatch(value):
            raise ValueError("price must have at most two decimal places")
        fen = parse_yuan(value)
        if fen > MAX_PRICE_FEN:
            raise ValueError("price exceeds model input maximum")
        return format_yuan(fen)


class ProductRead(BaseModel):
    id: int
    name: str
    category: str
    description: str
    emoji: str | None
    emoji_art: EmojiArt | None
    unit_price_yuan: str
    stock_quantity: int
    is_active: bool


def parse_yuan(value: str) -> int:
    whole, _, fractional = value.partition(".")
    return int(whole) * 100 + int((fractional + "00")[:2])


def _product_read(row: sqlite3.Row) -> ProductRead:
    emoji_art: EmojiArt | None = None
    if row["emoji_art_json"] is not None:
        try:
            emoji_art = EmojiArt.model_validate_json(str(row["emoji_art_json"]))
        except ValidationError:
            emoji_art = None
    return ProductRead(
        id=int(row["id"]),
        name=str(row["name"]),
        category=str(row["category"]),
        description=str(row["description"]),
        emoji=row["emoji"],
        emoji_art=emoji_art,
        unit_price_yuan=format_yuan(int(row["unit_price_fen"])),
        stock_quantity=int(row["stock_quantity"]),
        is_active=bool(row["is_active"]),
    )


def build_admin_router(database_path: Path) -> APIRouter:
    router = APIRouter()

    def get_orders(status: Literal["pending", "completed"] = "pending") -> list[OrderRead]:
        with closing(sqlite3.connect(database_path)) as connection:
            connection.row_factory = sqlite3.Row
            orders = connection.execute(
                """
                SELECT id, room_no, status, total_fen, tier, created_at, completed_at
                FROM orders WHERE status = ? ORDER BY created_at ASC, id ASC
                """,
                (status,),
            ).fetchall()
            order_ids = [int(order["id"]) for order in orders]
            items_by_order: dict[int, list[OrderItemRead]] = {
                order_id: [] for order_id in order_ids
            }
            if order_ids:
                placeholders = ",".join("?" for _ in order_ids)
                items = connection.execute(
                    f"""
                    SELECT order_id, product_id, product_name, unit_price_fen, quantity
                    FROM order_items WHERE order_id IN ({placeholders}) ORDER BY id
                    """,
                    order_ids,
                ).fetchall()
                for item in items:
                    items_by_order[int(item["order_id"])].append(
                        OrderItemRead(
                            product_id=int(item["product_id"]),
                            name=str(item["product_name"]),
                            unit_price_yuan=format_yuan(int(item["unit_price_fen"])),
                            quantity=int(item["quantity"]),
                        )
                    )

        return [
            OrderRead(
                id=int(order["id"]),
                room_no=str(order["room_no"]),
                status=str(order["status"]),  # type: ignore[arg-type]
                total_yuan=format_yuan(int(order["total_fen"])),
                tier=str(order["tier"]),
                created_at=str(order["created_at"]),
                completed_at=(
                    str(order["completed_at"]) if order["completed_at"] is not None else None
                ),
                items=items_by_order[int(order["id"])],
            )
            for order in orders
        ]

    def complete_order(order_id: int) -> OrderRead | JSONResponse:
        try:
            return _complete_order(database_path, order_id)
        except AdminFailure as error:
            return JSONResponse(
                status_code=error.status_code,
                content={"code": error.code, "message": error.message},
            )
        except sqlite3.Error:
            return JSONResponse(
                status_code=500,
                content={
                    "code": "INTERNAL_ERROR",
                    "message": "订单没有存好，请稍等一下再试哦 🐿️",
                },
            )

    def get_admin_products() -> list[ProductRead]:
        with closing(sqlite3.connect(database_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT id, name, category, description, emoji, emoji_art_json,
                       unit_price_fen, stock_quantity, is_active
                FROM products ORDER BY category COLLATE NOCASE, name COLLATE NOCASE
                """
            ).fetchall()
        return [_product_read(row) for row in rows]

    def create_product(payload: ProductWrite) -> ProductRead:
        if not payload.name or not payload.category:
            return JSONResponse(  # type: ignore[return-value]
                status_code=422,
                content={
                    "code": "INVALID_PRODUCT",
                    "message": "商品名称和分类要填好哦 🏷️",
                },
            )
        with closing(sqlite3.connect(database_path)) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(
                """
                INSERT INTO products (
                    name, category, description, emoji, emoji_art_json,
                    unit_price_fen, stock_quantity, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.name,
                    payload.category,
                    payload.description,
                    payload.emoji,
                    payload.emoji_art.model_dump_json() if payload.emoji_art else None,
                    parse_yuan(payload.unit_price_yuan),
                    payload.stock_quantity,
                    int(payload.is_active),
                ),
            )
            product_id = cursor.lastrowid
            connection.commit()
            row = connection.execute(
                """
                SELECT id, name, category, description, emoji, emoji_art_json,
                       unit_price_fen, stock_quantity, is_active FROM products WHERE id = ?
                """,
                (product_id,),
            ).fetchone()
        if row is None:
            raise sqlite3.IntegrityError("created product could not be reloaded")
        return _product_read(row)

    def update_product(product_id: int, payload: ProductPatch) -> ProductRead | JSONResponse:
        try:
            return _update_product(database_path, product_id, payload)
        except AdminFailure as error:
            return JSONResponse(
                status_code=error.status_code,
                content={"code": error.code, "message": error.message},
            )

    router.add_api_route(
        "/api/admin/orders", get_orders, methods=["GET"], response_model=list[OrderRead]
    )
    router.add_api_route(
        "/api/admin/orders/{order_id}/complete",
        complete_order,
        methods=["POST"],
        response_model=OrderRead,
    )
    router.add_api_route(
        "/api/admin/products",
        get_admin_products,
        methods=["GET"],
        response_model=list[ProductRead],
    )
    router.add_api_route(
        "/api/admin/products",
        create_product,
        methods=["POST"],
        response_model=ProductRead,
        status_code=201,
    )
    router.add_api_route(
        "/api/admin/products/{product_id}",
        update_product,
        methods=["PATCH"],
        response_model=ProductRead,
    )
    return router


def _complete_order(database_path: Path, order_id: int) -> OrderRead:
    with closing(sqlite3.connect(database_path, timeout=10)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        try:
            order = connection.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if order is None:
                raise AdminFailure(
                    404, "ORDER_NOT_FOUND", "这个订单找不到了，是不是被小猫叼走了 🐱"
                )
            if order["status"] == "completed":
                raise AdminFailure(
                    409, "ALREADY_COMPLETED", "这个订单已经完成啦，不重复扣库存哦 ✅"
                )

            items = connection.execute(
                """
                SELECT product_id, product_name, unit_price_fen, quantity
                FROM order_items WHERE order_id = ?
                """,
                (order_id,),
            ).fetchall()
            for item in items:
                product = connection.execute(
                    "SELECT stock_quantity FROM products WHERE id = ?", (item["product_id"],)
                ).fetchone()
                if product is None or int(product["stock_quantity"]) < int(item["quantity"]):
                    raise AdminFailure(
                        409,
                        "INSUFFICIENT_STOCK",
                        "库存不够啦，先去补货再完成订单吧 📦💦",
                    )

            for item in items:
                connection.execute(
                    "UPDATE products SET stock_quantity = stock_quantity - ? WHERE id = ?",
                    (item["quantity"], item["product_id"]),
                )
            completed_at = datetime.now(UTC).isoformat()
            connection.execute(
                "UPDATE orders SET status = 'completed', completed_at = ? WHERE id = ?",
                (completed_at, order_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    completed = dict(order)
    completed["status"] = "completed"
    completed["completed_at"] = completed_at
    return OrderRead(
        id=order_id,
        room_no=str(completed["room_no"]),
        status="completed",
        total_yuan=format_yuan(int(completed["total_fen"])),
        tier=str(completed["tier"]),
        created_at=str(completed["created_at"]),
        completed_at=completed_at,
        items=[
            OrderItemRead(
                product_id=int(item["product_id"]),
                name=str(item["product_name"]),
                unit_price_yuan=format_yuan(int(item["unit_price_fen"])),
                quantity=int(item["quantity"]),
            )
            for item in items
        ],
    )


def _update_product(database_path: Path, product_id: int, payload: ProductPatch) -> ProductRead:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise AdminFailure(422, "INVALID_PRODUCT", "至少改一项商品信息哦 ✏️")
    for required_field in ("description", "stock_quantity", "is_active", "unit_price_yuan"):
        if required_field in updates and updates[required_field] is None:
            raise AdminFailure(422, "INVALID_PRODUCT", "商品信息不能留空哦 🧺")
    if "name" in updates and not updates["name"]:
        raise AdminFailure(422, "INVALID_PRODUCT", "商品名称不能为空哦 🏷️")
    if "category" in updates and not updates["category"]:
        raise AdminFailure(422, "INVALID_PRODUCT", "商品分类不能为空哦 🧺")

    column_values: dict[str, object] = {}
    allowed_columns = {
        "name",
        "category",
        "description",
        "emoji",
        "stock_quantity",
        "is_active",
    }
    for field, value in updates.items():
        if field in allowed_columns:
            column_values[field] = (
                int(value) if field == "is_active" and value is not None else value
            )
        elif field == "unit_price_yuan":
            if value is None:
                raise AdminFailure(422, "INVALID_PRODUCT", "价格要填写两位小数哦 💰")
            column_values["unit_price_fen"] = parse_yuan(str(value))
        elif field == "emoji_art":
            column_values["emoji_art_json"] = (
                json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                if value is not None
                else None
            )

    if not column_values:
        raise AdminFailure(422, "INVALID_PRODUCT", "商品信息没有可保存的内容哦 🧺")

    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        try:
            exists = connection.execute(
                "SELECT id FROM products WHERE id = ?", (product_id,)
            ).fetchone()
            if exists is None:
                raise AdminFailure(404, "PRODUCT_NOT_FOUND", "这个商品找不到啦 🐾")
            assignments = ", ".join(f"{column} = ?" for column in column_values)
            connection.execute(
                f"UPDATE products SET {assignments} WHERE id = ?",
                (*column_values.values(), product_id),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT id, name, category, description, emoji, emoji_art_json,
                       unit_price_fen, stock_quantity, is_active FROM products WHERE id = ?
                """,
                (product_id,),
            ).fetchone()
        except Exception:
            connection.rollback()
            raise
    if row is None:
        raise sqlite3.IntegrityError("updated product could not be reloaded")
    return _product_read(row)
