"""@purpose Initialize SQLite and the approved demo catalog schema.
@spec [[storefront-product-catalog-browsing-and-category-filter]]
@invariants Seed only an empty catalog; prices and stock are non-negative.
@adr [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]
"""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import TypeAdapter

from .products import ProductRead

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = BACKEND_ROOT / "data" / "sugarmarket.sqlite3"
SEED_DATA_PATH = Path(__file__).resolve().parent / "data" / "products.json"


def database_path_from_environment() -> Path:
    """Resolve the local database path, allowing isolated test databases."""
    configured_path = os.environ.get("SUGARMARKET_DB_PATH")
    return Path(configured_path) if configured_path else DEFAULT_DATABASE_PATH


def initialize_database(database_path: Path) -> None:
    """Create the catalog table and seed it once when it is empty."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    emoji TEXT,
                    unit_price_fen INTEGER NOT NULL CHECK (unit_price_fen >= 0),
                    stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
                    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
                )
                """
            )
            product_count = connection.execute("SELECT COUNT(*) FROM products").fetchone()
            if product_count is None:
                raise RuntimeError("Unable to count catalog products")
            if product_count[0] == 0:
                _insert_seed_products(connection)


def _insert_seed_products(connection: sqlite3.Connection) -> None:
    with SEED_DATA_PATH.open(encoding="utf-8") as seed_file:
        raw_products = TypeAdapter(list[ProductRead]).validate_python(json.load(seed_file))

    for raw_product in raw_products:
        connection.execute(
            """
            INSERT INTO products (
                id, name, category, description, emoji, unit_price_fen,
                stock_quantity, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw_product.id,
                raw_product.name,
                raw_product.category,
                raw_product.description,
                raw_product.emoji,
                raw_product.unit_price_fen,
                raw_product.stock_quantity,
                int(raw_product.is_active),
            ),
        )
