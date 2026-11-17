import os
import socket
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from inventory.api import create_app
from inventory.db import database_engine, products
from inventory.seed import seed

HEADERS = {"X-API-Key": "test-only"}


@pytest.fixture
def db(monkeypatch):
    url = make_url(os.environ["TEST_DATABASE_URL"])
    admin = database_engine(url)
    schema = "inventory_test_" + uuid4().hex
    isolated_url = url.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = database_engine(isolated_url)
    monkeypatch.setenv("DATABASE_URL", isolated_url.render_as_string(hide_password=False))
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", isolated_url.render_as_string(hide_password=False))
    monkeypatch.setenv("API_KEY", HEADERS["X-API-Key"])
    with admin.begin() as conn:
        conn.exec_driver_sql(f"CREATE SCHEMA {schema}")
    try:
        command.upgrade(Config("alembic.ini"), "head")
        seed(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")
        admin.dispose()


@pytest.fixture
def client(db):
    with TestClient(create_app()) as api:
        yield api


def test_product(client):
    response = client.get("/products/HP-001", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {
        "sku": "HP-001", "name": "Sony WH-1000XM5", "stock_quantity": 8,
        "price_eur": "299.00", "currency": "EUR", "data_source": "POSTGRESQL_DEMO",
    }


def test_out_of_stock(client):
    response = client.get("/products/HP-002", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["stock_quantity"] == 0


def test_unknown(client):
    assert client.get("/products/unknown", headers=HEADERS).status_code == 404


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "incorrect"}])
def test_auth(client, headers):
    assert client.get("/products/HP-001", headers=headers).status_code == 401


@pytest.mark.parametrize("changes", [{"stock_quantity": -1}, {"price_eur": -1}])
def test_database_constraints(db, changes):
    with pytest.raises(IntegrityError), db.begin() as conn:
        conn.execute(update(products).where(products.c.sku == "HP-001").values(**changes))


def test_live_change(client, db):
    assert client.get("/products/HP-001", headers=HEADERS).json()["stock_quantity"] == 8
    with db.begin() as conn:
        conn.execute(update(products).where(products.c.sku == "HP-001").values(stock_quantity=3, price_eur=4.5))
    result = client.get("/products/HP-001", headers=HEADERS).json()
    assert result["stock_quantity"] == 3
    assert result["price_eur"] == "4.50"


def test_seed_restores_only_missing(db):
    with db.begin() as conn:
        conn.execute(update(products).where(products.c.sku == "HP-001").values(stock_quantity=1))
        conn.execute(products.delete().where(products.c.sku == "AC-003"))
    seed(db)
    with db.connect() as conn:
        assert dict(conn.execute(select(products.c.sku, products.c.stock_quantity)).all()) == {
            "HP-001": 1, "HP-002": 0, "AC-003": 25,
        }


def test_ready(client):
    assert client.get("/ready").status_code == 200


def test_database_unavailable(monkeypatch):
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
        monkeypatch.setenv("DATABASE_URL", f"postgresql://inventory@127.0.0.1:{port}/offline")
        monkeypatch.setenv("API_KEY", HEADERS["X-API-Key"])
        with TestClient(create_app()) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/products/HP-001").status_code == 401
            for path in ("/ready", "/products/HP-001"):
                response = client.get(path, headers=HEADERS)
                assert response.status_code == 503
                assert response.json() == {"detail": "Database unavailable"}
