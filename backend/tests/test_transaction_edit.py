"""Tests for the transaction-management PATCH endpoint.

Covers ownership scoping, field validation, category access, and the
observable behavior needed for budgets/dashboards to reflect the edit.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.db import Base, get_db
from app.main import app
from app.models import Category, Transaction, User
from app.models.transaction import TransactionType


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add_all(
        [
            User(id=1, phone="09120000001", name="Test", language="fa", chat_mode="normal"),
            User(id=2, phone="09120000002", name="Other", language="fa", chat_mode="normal"),
            Category(id=1, name="Food", icon="f", color="#111", is_default=True),
            Category(id=2, name="Transport", icon="t", color="#222", is_default=True),
            Category(id=3, name="Private", icon="p", color="#333", is_default=False, user_id=2),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _client(db, user_id: int = 1) -> TestClient:
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: db.query(User).filter(User.id == user_id).one()
    return TestClient(app)


def _make_tx(db, **kwargs) -> Transaction:
    tx = Transaction(
        user_id=kwargs.get("user_id", 1),
        category_id=kwargs.get("category_id", 1),
        amount=kwargs.get("amount", 100_000),
        type=kwargs.get("type", TransactionType.expense),
        description=kwargs.get("description", "coffee"),
        date=kwargs.get("date", date.today()),
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def test_patch_updates_amount(db):
    tx = _make_tx(db, amount=100_000)
    client = _client(db)
    try:
        r = client.patch(f"/api/v1/transactions/{tx.id}", json={"amount": 250_000})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["amount"] == 250_000
    db.refresh(tx)
    assert tx.amount == 250_000


def test_patch_changes_type(db):
    tx = _make_tx(db, type=TransactionType.expense)
    client = _client(db)
    try:
        r = client.patch(f"/api/v1/transactions/{tx.id}", json={"type": "income"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["type"] == "income"
    db.refresh(tx)
    assert tx.type == TransactionType.income


def test_patch_changes_category(db):
    tx = _make_tx(db, category_id=1)
    client = _client(db)
    try:
        r = client.patch(f"/api/v1/transactions/{tx.id}", json={"category_id": 2})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    db.refresh(tx)
    assert tx.category_id == 2


def test_patch_changes_description_and_date(db):
    tx = _make_tx(db)
    new_date = (date.today() - timedelta(days=3)).isoformat()
    client = _client(db)
    try:
        r = client.patch(
            f"/api/v1/transactions/{tx.id}",
            json={"description": "updated", "date": new_date},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    db.refresh(tx)
    assert tx.description == "updated"
    assert tx.date.isoformat() == new_date


def test_patch_rejects_zero_or_negative_amount(db):
    tx = _make_tx(db, amount=100_000)
    client = _client(db)
    try:
        r_zero = client.patch(f"/api/v1/transactions/{tx.id}", json={"amount": 0})
        r_neg = client.patch(f"/api/v1/transactions/{tx.id}", json={"amount": -50})
    finally:
        app.dependency_overrides.clear()
    assert r_zero.status_code == 422
    assert r_neg.status_code == 422
    db.refresh(tx)
    assert tx.amount == 100_000


def test_patch_rejects_inaccessible_category(db):
    tx = _make_tx(db, category_id=1)
    client = _client(db)
    try:
        # Category 3 belongs to user 2 and is not default; user 1 cannot use it.
        r = client.patch(f"/api/v1/transactions/{tx.id}", json={"category_id": 3})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 400
    db.refresh(tx)
    assert tx.category_id == 1


def test_patch_cannot_edit_other_users_transaction(db):
    tx = _make_tx(db, user_id=2)
    client = _client(db, user_id=1)
    try:
        r = client.patch(f"/api/v1/transactions/{tx.id}", json={"amount": 999})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 404
    db.refresh(tx)
    assert tx.amount == 100_000


def test_patch_ignores_user_id_field(db):
    tx = _make_tx(db, user_id=1)
    client = _client(db)
    try:
        # Even if the client tries to smuggle user_id, PATCH schema does not
        # include it and the DB row's user_id must not change.
        r = client.patch(
            f"/api/v1/transactions/{tx.id}",
            json={"amount": 500_000, "user_id": 2},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    db.refresh(tx)
    assert tx.user_id == 1
    assert tx.amount == 500_000


def test_summary_reflects_transaction_edit(db):
    tx = _make_tx(db, amount=1_000_000, type=TransactionType.expense)
    client = _client(db)
    try:
        before = client.get("/api/v1/transactions/summary").json()
        client.patch(f"/api/v1/transactions/{tx.id}", json={"amount": 4_000_000})
        after = client.get("/api/v1/transactions/summary").json()
    finally:
        app.dependency_overrides.clear()
    assert after["total_expense"] - before["total_expense"] == 3_000_000
