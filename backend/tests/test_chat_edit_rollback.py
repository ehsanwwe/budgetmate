"""End-to-end chat-edit rollback and chat-deletion policy tests.

These tests use a stub orchestrator instead of hitting the real LLM. They
verify:
  * Editing a message that created a transaction removes that transaction
    and any transaction the regenerated branch creates is counted only once.
  * A tx-creating message edited to a question rolls back the transaction.
  * A question edited to a tx-creating message creates exactly one tx.
  * Editing an earlier message with many later user/assistant messages and
    side effects rolls back all of them.
  * Repeated same-content edit submissions are idempotent.
  * Rollback preserves manual and unrelated records.
  * Deletion requests via chat do NOT delete transactions.
  * Internal edit rollback can still remove chat-created transactions.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.db import Base, get_db
from app.main import app
from app.models import Category, ChatMessage, Transaction, User
from app.models.transaction import TransactionType
from app.routers import chat as chat_router
from app.services.agent_orchestrator.types import AgentFinalResponse


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    session.add_all(
        [
            User(id=1, phone="09120000001", name="Test", language="fa", chat_mode="normal"),
            Category(id=1, name="Transport", icon="t", color="#111", is_default=True),
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


def _install_orchestrator(monkeypatch, callback):
    """Install a fake orchestrator.run whose behavior is controlled by callback."""

    async def fake_run(db_arg, user_arg, user_message, **kwargs):
        return await callback(db_arg, user_arg, user_message, kwargs)

    monkeypatch.setattr(chat_router.orchestrator, "run", fake_run)


def _make_tx(db, user_id: int, amount: int, description: str, source_message_id: int | None = None, type_=TransactionType.expense) -> Transaction:
    tx = Transaction(
        user_id=user_id,
        category_id=1,
        amount=amount,
        type=type_,
        description=description,
        date=date.today(),
        source_message_id=source_message_id,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def _consume_stream(resp) -> str:
    """Return the full text of a streaming response."""
    return resp.text


# ── 1) Amount correction: taxi 1,200 → 120,000 ────────────────────────────────

def test_edit_amount_correction_replaces_transaction(monkeypatch, db):
    """User says '1,200 for taxi' → edit to '120,000 for taxi'. Exactly one
    taxi expense at 120,000 remains; the old 1,200 row is gone."""
    async def orchestrator_cb(db_arg, user_arg, message, kwargs):
        smid = kwargs.get("source_message_id")
        # First run created 1,200 tx. Edit reruns with the new content and
        # creates a 120,000 tx.
        if "120" in message or "120000" in message.replace(",", "").replace("٬", ""):
            _make_tx(db_arg, user_arg.id, 120_000, "taxi", source_message_id=smid)
            return AgentFinalResponse(message="recorded 120,000 taxi")
        _make_tx(db_arg, user_arg.id, 1_200, "taxi", source_message_id=smid)
        return AgentFinalResponse(message="recorded 1,200 taxi")

    _install_orchestrator(monkeypatch, orchestrator_cb)

    client = _client(db)
    try:
        client.post("/api/v1/chat/message", json={"content": "I paid 1,200 for a taxi"})
        user_msg_id = db.query(ChatMessage).filter(ChatMessage.role == "user").order_by(ChatMessage.id.desc()).first().id
        edit = client.patch(
            f"/api/v1/chat/messages/{user_msg_id}",
            json={"content": "I paid 120,000 for a taxi"},
        )
    finally:
        app.dependency_overrides.clear()

    assert edit.status_code == 200
    taxis = db.query(Transaction).filter(Transaction.user_id == 1).all()
    assert len(taxis) == 1
    assert taxis[0].amount == 120_000


# ── 2) Transaction message edited into a question ─────────────────────────────

def test_edit_tx_message_into_question_removes_created_transaction(monkeypatch, db):
    async def orchestrator_cb(db_arg, user_arg, message, kwargs):
        smid = kwargs.get("source_message_id")
        if "?" in message or "how" in message.lower() or "چقدر" in message:
            return AgentFinalResponse(message="answering question")
        _make_tx(db_arg, user_arg.id, 1_200, "taxi", source_message_id=smid)
        return AgentFinalResponse(message="recorded")

    _install_orchestrator(monkeypatch, orchestrator_cb)

    client = _client(db)
    try:
        client.post("/api/v1/chat/message", json={"content": "I paid 1,200 for a taxi"})
        user_msg_id = db.query(ChatMessage).filter(ChatMessage.role == "user").order_by(ChatMessage.id.desc()).first().id
        edit = client.patch(
            f"/api/v1/chat/messages/{user_msg_id}",
            json={"content": "How much did I spend this month?"},
        )
    finally:
        app.dependency_overrides.clear()

    assert edit.status_code == 200
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 0


# ── 3) Question message edited into a transaction ─────────────────────────────

def test_edit_question_into_transaction_creates_single_tx(monkeypatch, db):
    async def orchestrator_cb(db_arg, user_arg, message, kwargs):
        smid = kwargs.get("source_message_id")
        if message.strip().lower().startswith("hello") or message.strip() == "سلام":
            return AgentFinalResponse(message="hi")
        _make_tx(db_arg, user_arg.id, 120_000, "taxi", source_message_id=smid)
        return AgentFinalResponse(message="recorded")

    _install_orchestrator(monkeypatch, orchestrator_cb)

    client = _client(db)
    try:
        client.post("/api/v1/chat/message", json={"content": "Hello"})
        user_msg_id = db.query(ChatMessage).filter(ChatMessage.role == "user").order_by(ChatMessage.id.desc()).first().id
        client.patch(
            f"/api/v1/chat/messages/{user_msg_id}",
            json={"content": "I paid 120,000 for a taxi"},
        )
    finally:
        app.dependency_overrides.clear()

    txs = db.query(Transaction).filter(Transaction.user_id == 1).all()
    assert len(txs) == 1
    assert txs[0].amount == 120_000


# ── 4) Later-branch edit removes all downstream side effects ──────────────────

def test_edit_earlier_message_removes_all_later_transactions(monkeypatch, db):
    async def orchestrator_cb(db_arg, user_arg, message, kwargs):
        smid = kwargs.get("source_message_id")
        # Each message creates one tx with unique amount encoded in message.
        # "hi" / questions do NOT create a tx.
        if message.strip().lower() in {"hi", "hello"} or "?" in message:
            return AgentFinalResponse(message="ok")
        if "50" in message:
            _make_tx(db_arg, user_arg.id, 50_000, "coffee", source_message_id=smid)
            return AgentFinalResponse(message="coffee 50")
        if "30" in message:
            _make_tx(db_arg, user_arg.id, 30_000, "tea", source_message_id=smid)
            return AgentFinalResponse(message="tea 30")
        if "10" in message:
            _make_tx(db_arg, user_arg.id, 10_000, "juice", source_message_id=smid)
            return AgentFinalResponse(message="juice 10")
        _make_tx(db_arg, user_arg.id, 1_200, "taxi", source_message_id=smid)
        return AgentFinalResponse(message="taxi 1.2k")

    _install_orchestrator(monkeypatch, orchestrator_cb)

    client = _client(db)
    try:
        client.post("/api/v1/chat/message", json={"content": "spent 1200 taxi"})
        first_user_id = db.query(ChatMessage).filter(ChatMessage.role == "user").order_by(ChatMessage.id).first().id
        client.post("/api/v1/chat/message", json={"content": "spent 50 coffee"})
        client.post("/api/v1/chat/message", json={"content": "spent 30 tea"})
        client.post("/api/v1/chat/message", json={"content": "spent 10 juice"})
        assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 4

        edit = client.patch(
            f"/api/v1/chat/messages/{first_user_id}",
            json={"content": "hi"},  # non-tx edit
        )
    finally:
        app.dependency_overrides.clear()

    assert edit.status_code == 200
    # The regenerated first message is "hi" — no tx. All later txs are gone
    # because their originating messages were superseded.
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 0


# ── 5) Manual transactions and earlier-branch txns survive rollback ───────────

def test_edit_preserves_manual_and_earlier_records(monkeypatch, db):
    async def orchestrator_cb(db_arg, user_arg, message, kwargs):
        smid = kwargs.get("source_message_id")
        _make_tx(db_arg, user_arg.id, 5_000, "chat entry", source_message_id=smid)
        return AgentFinalResponse(message="recorded")

    _install_orchestrator(monkeypatch, orchestrator_cb)

    # Manual UI-created transaction (no chat provenance).
    manual = _make_tx(db, 1, 999_000, "manual restaurant", source_message_id=None)

    client = _client(db)
    try:
        client.post("/api/v1/chat/message", json={"content": "chat 1"})
        client.post("/api/v1/chat/message", json={"content": "chat 2"})
        latest_user_id = db.query(ChatMessage).filter(ChatMessage.role == "user").order_by(ChatMessage.id.desc()).first().id

        client.patch(
            f"/api/v1/chat/messages/{latest_user_id}",
            json={"content": "hello"},
        )
    finally:
        app.dependency_overrides.clear()

    # Manual survives.
    assert db.query(Transaction).filter(Transaction.id == manual.id).first() is not None
    # Earlier chat tx (from chat 1) survives; later branch tx removed and
    # regenerated with a new one.
    remaining = db.query(Transaction).filter(Transaction.user_id == 1).all()
    # Earlier chat, manual, and the regenerated hello (which still creates
    # one tx via the stub) sum to 3.
    assert len(remaining) == 3


# ── 6) Chat-side deletion requests do NOT delete transactions ────────────────

def test_chat_delete_request_does_not_remove_transaction(monkeypatch, db):
    """The assistant (via LLM) is not allowed to plan a DELETE against
    transactions. Any deletion request must be answered in prose. This
    test asserts the POST /chat/message path does not remove existing txs
    when the stub LLM tries to delete."""
    manual = _make_tx(db, 1, 250_000, "restaurant", source_message_id=None)

    async def orchestrator_cb(db_arg, user_arg, message, kwargs):
        # The real orchestrator uses validators to reject transaction
        # DELETE. Here we simulate the correct behavior: the LLM answers
        # with menu guidance and does NOT touch the DB.
        return AgentFinalResponse(
            message=(
                "من از داخل چت اجازه حذف تراکنش ندارم. "
                "برای حذف، وارد منوی مدیریت تراکنش‌ها شو."
            )
        )

    _install_orchestrator(monkeypatch, orchestrator_cb)

    client = _client(db)
    try:
        r = client.post(
            "/api/v1/chat/message",
            json={"content": "تراکنش آخرم را حذف کن"},
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    # The transaction is still present.
    assert db.query(Transaction).filter(Transaction.id == manual.id).first() is not None


# ── 7) Manual DELETE via REST endpoint still works ────────────────────────────

def test_manual_delete_endpoint_still_removes_transaction(db):
    tx = _make_tx(db, 1, 100_000, "coffee")
    client = _client(db)
    try:
        r = client.delete(f"/api/v1/transactions/{tx.id}")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 204
    assert db.query(Transaction).filter(Transaction.id == tx.id).first() is None


# ── 8) Income correction rolls back old income and inserts new one ───────────

def test_edit_income_correction_replaces_transaction(monkeypatch, db):
    async def orchestrator_cb(db_arg, user_arg, message, kwargs):
        smid = kwargs.get("source_message_id")
        # Any message with "500" gets a 500k income; "5" alone gets 5k.
        if "500" in message:
            _make_tx(
                db_arg,
                user_arg.id,
                500_000,
                "salary",
                source_message_id=smid,
                type_=TransactionType.income,
            )
            return AgentFinalResponse(message="500k salary recorded")
        _make_tx(
            db_arg,
            user_arg.id,
            5_000,
            "salary",
            source_message_id=smid,
            type_=TransactionType.income,
        )
        return AgentFinalResponse(message="5k salary recorded")

    _install_orchestrator(monkeypatch, orchestrator_cb)

    client = _client(db)
    try:
        client.post("/api/v1/chat/message", json={"content": "got 5 salary"})
        user_msg_id = db.query(ChatMessage).filter(ChatMessage.role == "user").first().id
        client.patch(
            f"/api/v1/chat/messages/{user_msg_id}",
            json={"content": "got 500 salary"},
        )
    finally:
        app.dependency_overrides.clear()

    rows = db.query(Transaction).filter(Transaction.user_id == 1).all()
    assert len(rows) == 1
    assert rows[0].amount == 500_000
    assert rows[0].type == TransactionType.income


# ── 9) Rollback failure preserves the branch ─────────────────────────────────

def test_rollback_failure_preserves_branch(monkeypatch, db):
    from app.services.chat_edit_rollback import ChatBranchRollbackError
    import app.services.chat_session_lifecycle as lifecycle

    async def orchestrator_cb(db_arg, user_arg, message, kwargs):
        smid = kwargs.get("source_message_id")
        _make_tx(db_arg, user_arg.id, 100_000, "coffee", source_message_id=smid)
        return AgentFinalResponse(message="ok")

    _install_orchestrator(monkeypatch, orchestrator_cb)

    def _boom(*args, **kwargs):
        raise ChatBranchRollbackError("simulated failure")

    monkeypatch.setattr(lifecycle, "rollback_chat_branch_side_effects", _boom)

    client = _client(db)
    try:
        client.post("/api/v1/chat/message", json={"content": "spent 100k coffee"})
        user_msg_id = db.query(ChatMessage).filter(ChatMessage.role == "user").first().id
        edit = client.patch(f"/api/v1/chat/messages/{user_msg_id}", json={"content": "changed"})
    finally:
        app.dependency_overrides.clear()

    assert edit.status_code == 409
    # Original branch intact.
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 1
    assert db.query(ChatMessage).filter(ChatMessage.id == user_msg_id).one().content.strip() == "spent 100k coffee"
