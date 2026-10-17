"""@purpose Serve the local Sugarmarket product catalog API.
@spec [[storefront-product-catalog-browsing-and-category-filter]]
@invariants Only active catalog entries are exposed; response data is Pydantic-validated.
@adr [[ADR-0001-react-typescript-fastapi-pydantic-sqlite-transformer]]
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from .admin import build_admin_router
from .checkout import (
    Predictor,
    build_checkout_router,
    checkout_validation_handler,
    default_predictor_factory,
)
from .database import database_path_from_environment, initialize_database
from .products import ProductRead, list_active_products


def create_app(database_path: Path | None = None, predictor: Predictor | None = None) -> FastAPI:
    selected_database_path = database_path or database_path_from_environment()
    cached_predictor = predictor

    def get_predictor() -> Predictor:
        nonlocal cached_predictor
        if cached_predictor is None:
            cached_predictor = default_predictor_factory()
        return cached_predictor

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        initialize_database(selected_database_path)
        yield

    app = FastAPI(title="Sugarmarket API", lifespan=lifespan)
    app.state.database_path = selected_database_path
    app.add_exception_handler(RequestValidationError, checkout_validation_handler)

    def get_products() -> list[ProductRead]:
        return list_active_products(selected_database_path)

    app.add_api_route(
        "/api/products",
        get_products,
        methods=["GET"],
        response_model=list[ProductRead],
    )
    app.include_router(build_checkout_router(selected_database_path, get_predictor))
    app.include_router(build_admin_router(selected_database_path))

    return app


app = create_app()
