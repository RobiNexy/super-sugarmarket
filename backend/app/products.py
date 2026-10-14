"""@purpose Read active catalog products from SQLite.
@spec [[storefront-product-catalog-browsing-and-category-filter]]
@invariants Prices are non-negative integer fen; inactive products never appear in the catalog.
@adr [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]
"""

import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ProductRead(BaseModel):
    """Validated public catalog representation of a product."""

    model_config = ConfigDict(strict=True)

    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str
    emoji: str | None
    unit_price_fen: int = Field(ge=0)
    stock_quantity: int = Field(ge=0)
    is_active: bool


def list_active_products(database_path: Path) -> list[ProductRead]:
    """Return active products in stable category/name order."""
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, name, category, description, emoji, unit_price_fen,
                   stock_quantity, is_active
            FROM products
            WHERE is_active = 1
            ORDER BY category COLLATE NOCASE, name COLLATE NOCASE
            """
        ).fetchall()

    return [
        ProductRead.model_validate({**dict(row), "is_active": bool(row["is_active"])})
        for row in rows
    ]
