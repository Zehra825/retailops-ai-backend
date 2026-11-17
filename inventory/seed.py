from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from .db import database_engine, products, required


def seed(engine: Engine) -> None:
    rows = [
        {"sku": "HP-001", "name": "Sony WH-1000XM5", "price_eur": Decimal("299.00"), "stock_quantity": 8},
        {"sku": "HP-002", "name": "JBL Tune 770NC", "price_eur": Decimal("89.00"), "stock_quantity": 0},
        {"sku": "AC-003", "name": "USB-C Charger 30W", "price_eur": Decimal("24.00"), "stock_quantity": 25},
    ]
    with engine.begin() as conn:
        conn.execute(insert(products).values(rows).on_conflict_do_nothing(index_elements=["sku"]))


if __name__ == "__main__":
    engine = database_engine(required("DATABASE_URL"))
    try:
        seed(engine)
    finally:
        engine.dispose()
