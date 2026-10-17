"""@purpose Initialize SQLite catalog/order schemas and add missing demo products.
@spec [[storefront-product-catalog-browsing-and-category-filter]]
@invariants Seed missing catalog entries without overwriting shopkeeper edits;
prices and stock are non-negative.
@adr [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]
"""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import TypeAdapter

from .products import ProductSeed

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = BACKEND_ROOT / "data" / "sugarmarket.sqlite3"
SEED_DATA_PATH = Path(__file__).resolve().parent / "data" / "products.json"


def database_path_from_environment() -> Path:
    """Resolve the local database path, allowing isolated test databases."""
    configured_path = os.environ.get("SUGARMARKET_DB_PATH")
    return Path(configured_path) if configured_path else DEFAULT_DATABASE_PATH


def initialize_database(database_path: Path) -> None:
    """Create catalog/order tables and insert seed entries missing from the catalog."""
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
                    emoji_art_json TEXT,
                    unit_price_fen INTEGER NOT NULL CHECK (unit_price_fen BETWEEN 0 AND 9999999),
                    stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
                    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
                )
                """
            )
            product_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(products)").fetchall()
            }
            if "emoji_art_json" not in product_columns:
                connection.execute("ALTER TABLE products ADD COLUMN emoji_art_json TEXT")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_no TEXT NOT NULL CHECK (length(room_no) BETWEEN 1 AND 10),
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'completed')),
                    tier TEXT NOT NULL DEFAULT 'none'
                        CHECK (tier IN ('none', 'tier2_wild', 'zero_compare', 'tier3_free')),
                    total_fen INTEGER NOT NULL CHECK (total_fen >= 0),
                    model_fen INTEGER CHECK (model_fen IS NULL OR model_fen >= 0),
                    exact_fen INTEGER NOT NULL CHECK (exact_fen >= 0),
                    addend_count INTEGER NOT NULL CHECK (addend_count >= 0),
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    CHECK ((status = 'pending' AND completed_at IS NULL)
                        OR (status = 'completed' AND completed_at IS NOT NULL))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL REFERENCES orders(id),
                    product_id INTEGER NOT NULL REFERENCES products(id),
                    product_name TEXT NOT NULL,
                    unit_price_fen INTEGER NOT NULL CHECK (unit_price_fen >= 0),
                    quantity INTEGER NOT NULL CHECK (quantity > 0)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_orders_status_created ON orders(status, created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id)"
            )
            _insert_seed_products(connection)


def _insert_seed_products(connection: sqlite3.Connection) -> None:
    with SEED_DATA_PATH.open(encoding="utf-8") as seed_file:
        raw_products = TypeAdapter(list[ProductSeed]).validate_python(json.load(seed_file))

    for raw_product in raw_products:
        connection.execute(
            """
            INSERT OR IGNORE INTO products (
                id, name, category, description, emoji, emoji_art_json, unit_price_fen,
                stock_quantity, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw_product.id,
                raw_product.name,
                raw_product.category,
                raw_product.description,
                raw_product.emoji,
                raw_product.emoji_art.model_dump_json() if raw_product.emoji_art else None,
                raw_product.unit_price_fen,
                raw_product.stock_quantity,
                int(raw_product.is_active),
            ),
        )
