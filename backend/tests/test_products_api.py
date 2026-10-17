"""@purpose Verify the catalog API contract and approved product invariants.
@spec [[storefront-product-catalog-browsing-and-category-filter]]
@covers Active product listing, empty catalog, JSON DTO validation, integer fen prices.
"""

import asyncio
import json
import sqlite3
from pathlib import Path

import httpx
from fastapi import FastAPI
from pydantic import TypeAdapter

from app.main import create_app
from app.products import ProductRead

PRODUCT_LIST_ADAPTER = TypeAdapter(list[ProductRead])


def get_products(app: FastAPI) -> list[ProductRead]:
    async def request_products() -> list[ProductRead]:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/api/products")
        assert response.status_code == 200
        return PRODUCT_LIST_ADAPTER.validate_python(response.json())

    return asyncio.run(request_products())


def test_catalog_returns_seed_products_with_yuan_and_available_stock(tmp_path: Path) -> None:
    app = create_app(tmp_path / "catalog.sqlite3")

    products = get_products(app)
    assert len(products) == 100
    assert {product.category for product in products} == {"饮品", "零食", "泡面速食", "日用品"}
    assert sum(product.emoji_art is not None for product in products) >= 10
    bottled_water = next(product for product in products if product.id == 1)
    assert bottled_water.unit_price_yuan == "2.00"
    assert bottled_water.available_quantity == 12
    assert bottled_water.is_active is True
    assert bottled_water.description


def test_catalog_omits_inactive_products(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite3"
    app = create_app(database_path)

    assert len(get_products(app)) == 100
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE products SET is_active = 0 WHERE id = 1")
    products = get_products(app)

    assert len(products) == 99
    assert all(product.id != 1 for product in products)


def test_catalog_returns_empty_array_when_every_product_is_inactive(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite3"
    app = create_app(database_path)

    get_products(app)
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE products SET is_active = 0")

    assert get_products(app) == []


def test_catalog_decodes_compositional_emoji_art(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite3"
    app = create_app(database_path)
    get_products(app)
    art = {
        "version": 1,
        "layers": [
            {
                "emoji": "🍓",
                "x": 50.0,
                "y": 55.0,
                "size": 60.0,
                "rotate": -10.0,
                "scale_x": 1.1,
                "scale_y": 0.9,
                "z": 1,
                "clip": None,
            },
            {
                "emoji": "🍃",
                "x": 64.0,
                "y": 22.0,
                "size": 30.0,
                "rotate": 30.0,
                "scale_x": 0.8,
                "scale_y": 1.2,
                "z": 2,
                "clip": "ellipse",
            },
        ],
    }
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE products SET emoji_art_json = ? WHERE id = 1", (json.dumps(art),)
        )

    product = next(item for item in get_products(app) if item.id == 1)

    assert product.emoji_art is not None
    assert len(product.emoji_art.layers) == 2
    assert product.emoji_art.layers[1].clip == "ellipse"


def test_database_adds_missing_seed_products_without_overwriting_shop_edits(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite3"
    app = create_app(database_path)
    get_products(app)
    with sqlite3.connect(database_path) as connection:
        connection.execute("DELETE FROM products WHERE id > 20")
        connection.execute("UPDATE products SET name = '老板改过的水' WHERE id = 1")

    products = get_products(app)

    assert len(products) == 100
    assert next(product for product in products if product.id == 1).name == "老板改过的水"


def test_invalid_composition_never_falls_back_to_parallel_emoji_text(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite3"
    app = create_app(database_path)
    get_products(app)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE products SET emoji = '🍓🍃', emoji_art_json = '{bad json' WHERE id = 1"
        )

    product = next(item for item in get_products(app) if item.id == 1)

    assert product.emoji is None
    assert product.emoji_art is None
