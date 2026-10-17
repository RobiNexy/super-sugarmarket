"""@purpose Read active catalog products from SQLite.
@spec [[storefront-product-catalog-browsing-and-category-filter]]
@invariants Prices are non-negative integer fen; inactive products never appear in the catalog.
@adr [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]
"""

import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .money import format_yuan


class EmojiLayer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    emoji: str = Field(min_length=1, max_length=16)
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    size: float = Field(gt=0, le=100)
    rotate: float = Field(ge=-180, le=180)
    scale_x: float = Field(ge=0.2, le=2)
    scale_y: float = Field(ge=0.2, le=2)
    skew_x: float = Field(default=0, ge=-30, le=30)
    skew_y: float = Field(default=0, ge=-30, le=30)
    origin_x: float = Field(default=50, ge=0, le=100)
    origin_y: float = Field(default=50, ge=0, le=100)
    z: int = Field(ge=0, le=20)
    clip: str | None = Field(
        default=None,
        pattern="^(circle|ellipse|rounded|left_half|right_half|top_half|bottom_half)$",
    )


class EmojiArt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: int = Field(ge=1, le=1)
    layers: list[EmojiLayer] = Field(min_length=2, max_length=12)


class ProductSeed(BaseModel):
    model_config = ConfigDict(strict=True)

    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str
    emoji: str | None
    emoji_art: EmojiArt | None = None
    unit_price_fen: int = Field(ge=0, le=9_999_999)
    stock_quantity: int = Field(ge=0)
    is_active: bool


class ProductRead(BaseModel):
    """Validated public catalog representation of a product."""

    model_config = ConfigDict(strict=True)

    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str
    emoji: str | None
    unit_price_yuan: str = Field(pattern=r"^\d+\.\d{2}$")
    stock_quantity: int = Field(ge=0)
    available_quantity: int = Field(ge=0)
    emoji_art: EmojiArt | None
    is_active: bool


def list_active_products(database_path: Path) -> list[ProductRead]:
    """Return active products in stable category/name order."""
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT p.id, p.name, p.category, p.description, p.emoji, p.unit_price_fen,
                   p.stock_quantity, p.emoji_art_json, p.is_active,
                   MAX(0, p.stock_quantity - COALESCE((
                       SELECT SUM(oi.quantity)
                       FROM order_items AS oi
                       JOIN orders AS o ON o.id = oi.order_id
                       WHERE oi.product_id = p.id AND o.status = 'pending'
                   ), 0)) AS available_quantity
            FROM products AS p
            WHERE p.is_active = 1
            ORDER BY p.category COLLATE NOCASE, p.name COLLATE NOCASE
            """
        ).fetchall()

    products: list[ProductRead] = []
    for row in rows:
        emoji_art: EmojiArt | None = None
        if row["emoji_art_json"] is not None:
            try:
                emoji_art = EmojiArt.model_validate_json(str(row["emoji_art_json"]))
            except ValidationError:
                # Invalid persisted art should not make the whole catalog unavailable.
                emoji_art = None
        emoji = row["emoji"]
        if row["emoji_art_json"] is not None and emoji_art is None:
            # Never show a broken composition as a side-by-side string.
            emoji = None
        products.append(
            ProductRead.model_validate(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "category": row["category"],
                    "description": row["description"],
                    "emoji": emoji,
                    "unit_price_yuan": format_yuan(int(row["unit_price_fen"])),
                    "stock_quantity": row["stock_quantity"],
                    "available_quantity": row["available_quantity"],
                    "emoji_art": emoji_art,
                    "is_active": bool(row["is_active"]),
                }
            )
        )
    return products
