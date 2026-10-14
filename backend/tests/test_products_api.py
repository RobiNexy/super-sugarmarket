"""@purpose Verify the catalog API contract and approved product invariants.
@spec [[storefront-product-catalog-browsing-and-category-filter]]
@covers Active product listing, empty catalog, JSON DTO validation, integer fen prices.
"""

import asyncio
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


def test_catalog_returns_seed_products_with_integer_fen(tmp_path: Path) -> None:
    app = create_app(tmp_path / "catalog.sqlite3")

    products = get_products(app)
    assert len(products) == 20
    bottled_water = next(product for product in products if product.id == 1)
    assert bottled_water.unit_price_fen == 200
    assert bottled_water.is_active is True
    assert bottled_water.description


def test_catalog_omits_inactive_products(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite3"
    app = create_app(database_path)

    assert len(get_products(app)) == 20
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE products SET is_active = 0 WHERE id = 1")
    products = get_products(app)

    assert len(products) == 19
    assert all(product.id != 1 for product in products)


def test_catalog_returns_empty_array_when_every_product_is_inactive(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite3"
    app = create_app(database_path)

    get_products(app)
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE products SET is_active = 0")

    assert get_products(app) == []
