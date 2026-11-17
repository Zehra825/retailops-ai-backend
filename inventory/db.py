import os

from dotenv import load_dotenv
from sqlalchemy import CheckConstraint, Column, DateTime, Integer, MetaData, Numeric, Table, Text, create_engine, func
from sqlalchemy.engine import make_url

load_dotenv(dotenv_path=".env")


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value or not value.strip():
        raise RuntimeError(f"Set {name} before starting.")
    return value


def database_engine(url: str):
    parsed = make_url(url)
    if parsed.get_backend_name() not in {"postgres", "postgresql"}:
        raise ValueError("A PostgreSQL connection URL is required.")
    return create_engine(
        parsed.set(drivername="postgresql+psycopg"),
        pool_pre_ping=True,
        pool_timeout=5,
        connect_args={"connect_timeout": 5},
        hide_parameters=True,
    )


metadata = MetaData()
products = Table(
    "products", metadata,
    Column("sku", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("price_eur", Numeric(10, 2), nullable=False),
    Column("stock_quantity", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("length(trim(name)) > 0", name="ck_products_name"),
    CheckConstraint("price_eur >= 0 AND price_eur <> 'NaN'::numeric", name="ck_products_price"),
    CheckConstraint("stock_quantity >= 0", name="ck_products_stock"),
)
