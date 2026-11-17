from contextlib import asynccontextmanager
from decimal import Decimal
from secrets import compare_digest
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, field_serializer
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .db import database_engine, products, required


class Product(BaseModel):
    sku: str
    name: str
    stock_quantity: int
    price_eur: Decimal
    currency: Literal["EUR"] = "EUR"
    data_source: Literal["POSTGRESQL_DEMO"] = "POSTGRESQL_DEMO"

    @field_serializer("price_eur")
    def serialize_price(self, value: Decimal) -> str:
        return format(value, ".2f")


def create_app() -> FastAPI:
    expected_key = required("API_KEY").encode()
    engine = database_engine(required("DATABASE_URL"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(title="RetailOps AI Inventory", lifespan=lifespan)
    header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def authenticate(key: Annotated[str | None, Depends(header)]):
        if not key or not compare_digest(key.encode(), expected_key):
            raise HTTPException(401, "Missing or invalid API key")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        try:
            with engine.connect() as conn:
                conn.execute(select(1))
        except SQLAlchemyError:
            raise HTTPException(503, "Database unavailable") from None
        return {"status": "ready"}

    @app.get("/products/{sku}", response_model=Product, dependencies=[Depends(authenticate)])
    def lookup(sku: str, response: Response):
        try:
            with engine.connect() as conn:
                row = conn.execute(select(products).where(products.c.sku == sku)).mappings().one_or_none()
        except SQLAlchemyError:
            raise HTTPException(503, "Database unavailable") from None
        if row is None:
            raise HTTPException(404, "Product not found")
        response.headers["Cache-Control"] = "no-store"
        return Product.model_validate(row)

    return app
