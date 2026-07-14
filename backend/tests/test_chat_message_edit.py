from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.db import Base, get_db
from app.main import app
from app.models import Category, ChatMessage, Transaction, User
from app.models.agent_idempotency import AgentOperationEvent
from app.models.chat import MessageRole
from app.models.future_commitment import FutureCommitment
from app.models.personal_cfo import FinancialFact
from app.models.transaction import TransactionType
from app.routers import chat as chat_router
from app.services.agent_orchestrator.types import AgentFinalResponse
from app.services.chat_session_lifecycle import (
    ChatMessageNotEditableError,
    edit_chat_message_and_truncate,
)


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
            User(id=1, phone="09120000001", name="Test", language="en", chat_mode="normal"),
            User(id=2, phone="09120000002", name="Other", language="en", chat_mode="normal"),
            Category(id=1, name="Food", icon="f", color="#111", is_default=True),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _add_timeline(db, user_id: int = 1, pair_count: int = 3) -> list[ChatMessage]:
    base = datetime.utcnow() - timedelta(hours=1)
    rows: list[ChatMessage] = []
    for index in range(pair_count):
        rows.extend(
            [
                ChatMessage(
                    user_id=user_id,
                    role=MessageRole.user,
                    content=f"user-{index}",
                    created_at=base + timedelta(seconds=index * 2),
                ),
                ChatMessage(
                    user_id=user_id,
                    role=MessageRole.assistant,
                    content=f"assistant-{index}",
                    created_at=base + timedelta(seconds=index * 2 + 1),
                ),
            ]
        )
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def _client(db, user_id: int = 1) -> TestClient:
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: db.query(User).filter(User.id == user_id).one()
    return TestClient(app)


def test_edit_latest_user_message_preserves_earlier_messages(db):
    rows = _add_timeline(db, pair_count=2)
    latest_user = ChatMessage(
        user_id=1,
        role=MessageRole.user,
        content="latest",
        created_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db.add(latest_user)
    db.commit()
    db.refresh(latest_user)

    result = edit_chat_message_and_truncate(db, 1, latest_user.id, "edited latest")

    assert result.removed_messages == 0
    assert result.message.content == "edited latest"
    assert [item["content"] for item in result.history] == [row.content for row in rows]


def test_edit_older_message_removes_multiple_later_pairs_and_keeps_prefix(db):
    prefix = ChatMessage(
        user_id=1,
        role=MessageRole.assistant,
        content="preserved prefix",
        created_at=datetime.utcnow() - timedelta(hours=2),
    )
    db.add(prefix)
    db.commit()
    rows = _add_timeline(db, pair_count=6)
    target = rows[0]

    result = edit_chat_message_and_truncate(db, 1, target.id, "edited first question")
    persisted = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == 1)
        .order_by(ChatMessage.created_at, ChatMessage.id)
        .all()
    )

    assert result.removed_messages == 11
    assert [(row.role.value, row.content) for row in persisted] == [
        ("assistant", "preserved prefix"),
        ("user", "edited first question"),
    ]
    assert result.history == [{"role": "assistant", "content": "preserved prefix"}]


def test_edit_deletes_created_transactions_from_removed_branch(db):
    """A transaction whose source_message_id belongs to a message in the
    superseded branch is removed by the deterministic rollback path."""
    rows = _add_timeline(db, pair_count=2)
    later_user = rows[2]
    transaction = Transaction(
        user_id=1,
        category_id=1,
        amount=100_000,
        type=TransactionType.expense,
        description="later branch expense",
        source_message_id=later_user.id,
    )
    db.add(transaction)
    db.commit()
    tx_id = transaction.id

    edit_result = edit_chat_message_and_truncate(db, 1, rows[0].id, "new branch")

    assert db.query(Transaction).filter(Transaction.id == tx_id).first() is None
    assert edit_result.rollback.deleted_transactions == 1


def test_edit_preserves_manual_transactions_and_earlier_chat_transactions(db):
    """Manual UI transactions (source_message_id IS NULL) and transactions
    tied to messages BEFORE the target must survive rollback."""
    rows = _add_timeline(db, pair_count=3)
    manual_tx = Transaction(
        user_id=1,
        amount=999_000,
        type=TransactionType.expense,
        description="manual entry",
        source_message_id=None,
    )
    earlier_tx = Transaction(
        user_id=1,
        amount=250_000,
        type=TransactionType.expense,
        description="earlier chat expense",
        source_message_id=rows[0].id,  # earlier message than the target
    )
    later_tx = Transaction(
        user_id=1,
        amount=500_000,
        type=TransactionType.expense,
        description="later chat expense",
        source_message_id=rows[4].id,  # later message than the target
    )
    db.add_all([manual_tx, earlier_tx, later_tx])
    db.commit()
    manual_id, earlier_id, later_id = manual_tx.id, earlier_tx.id, later_tx.id

    # Target rows[2] — the second user message. rows[0] is BEFORE, rows[4] is AFTER.
    edit_chat_message_and_truncate(db, 1, rows[2].id, "edited middle")

    assert db.query(Transaction).filter(Transaction.id == manual_id).first() is not None
    assert db.query(Transaction).filter(Transaction.id == earlier_id).first() is not None
    assert db.query(Transaction).filter(Transaction.id == later_id).first() is None


def test_edit_deletes_created_future_commitments_and_facts(db):
    rows = _add_timeline(db, pair_count=2)
    later_user = rows[2]
    fc = FutureCommitment(
        user_id=1,
        title="later commitment",
        amount=1_000_000,
        source_message_id=later_user.id,
    )
    fact = FinancialFact(
        user_id=1,
        fact_type="chat_reasoning_state",
        subject="reasoning",
        value_json={"stated_balance": 1000000},
        source_message_id=later_user.id,
    )
    db.add_all([fc, fact])
    db.commit()
    fc_id, fact_id = fc.id, fact.id

    edit_chat_message_and_truncate(db, 1, rows[0].id, "new branch")

    assert db.query(FutureCommitment).filter(FutureCommitment.id == fc_id).first() is None
    assert db.query(FinancialFact).filter(FinancialFact.id == fact_id).first() is None


def test_edit_is_idempotent_on_repeated_submission(db):
    """Submitting the same edit twice must not double-rollback or duplicate."""
    rows = _add_timeline(db, pair_count=2)
    later_user = rows[2]
    transaction = Transaction(
        user_id=1,
        amount=100_000,
        type=TransactionType.expense,
        description="later branch expense",
        source_message_id=later_user.id,
    )
    db.add(transaction)
    db.commit()

    edit_chat_message_and_truncate(db, 1, rows[0].id, "same content")
    # Second call is deduplicated by the edit-guard fingerprint.
    result_second = edit_chat_message_and_truncate(db, 1, rows[0].id, "same content")

    assert result_second.duplicate_edit is True
    # Row was removed by the first call; not resurrected by the second.
    assert db.query(Transaction).filter(Transaction.description == "later branch expense").count() == 0
    # Only one edit_guard event recorded.
    guards = (
        db.query(AgentOperationEvent)
        .filter(AgentOperationEvent.user_id == 1)
        .filter(AgentOperationEvent.operation_type == "chat_edit_guard")
        .all()
    )
    assert len(guards) == 1


def test_edit_restores_updated_row_from_before_state_snapshot(db):
    """UPDATE operations recorded with a before-state snapshot get restored."""
    from app.models.goal import Goal
    rows = _add_timeline(db, pair_count=2)
    goal = Goal(
        user_id=1,
        title="Trip to Kish",
        target_amount=50_000_000,
        current_amount=10_000_000,
        status="active",
        is_active=True,
    )
    db.add(goal)
    db.commit()

    # Simulate an LLM-driven UPDATE operation from the later branch: record
    # the before-state event, then apply the update.
    before_snapshot = {
        "id": goal.id,
        "target_amount": 50_000_000,
        "current_amount": 10_000_000,
        "status": "active",
        "is_active": True,
    }
    goal.target_amount = 80_000_000  # user "raised the target" via chat
    db.add(
        AgentOperationEvent(
            user_id=1,
            operation_fingerprint="goal-update-fp",
            operation_type="update",
            table_name="goals",
            target_record_id=goal.id,
            status="executed",
            payload_json={"params": {"target_amount": 80_000_000}, "before": before_snapshot},
            source_message_id=rows[2].id,  # later branch message
        )
    )
    db.commit()

    edit_chat_message_and_truncate(db, 1, rows[0].id, "edited earlier")

    restored = db.query(Goal).filter(Goal.id == goal.id).first()
    assert restored is not None
    assert restored.target_amount == 50_000_000
    assert restored.current_amount == 10_000_000


def test_edit_rejects_assistant_message(db):
    assistant = _add_timeline(db, pair_count=1)[1]

    with pytest.raises(ChatMessageNotEditableError):
        edit_chat_message_and_truncate(db, 1, assistant.id, "not allowed")

    assert db.query(ChatMessage).filter(ChatMessage.id == assistant.id).one().content == "assistant-0"


def test_edit_endpoint_rejects_other_user_and_empty_content(db):
    other_message = _add_timeline(db, user_id=2, pair_count=1)[0]
    client = _client(db, user_id=1)
    try:
        forbidden = client.patch(
            f"/api/v1/chat/messages/{other_message.id}", json={"content": "changed"}
        )
        empty = client.patch(
            f"/api/v1/chat/messages/{other_message.id}", json={"content": "   "}
        )
    finally:
        app.dependency_overrides.clear()

    assert forbidden.status_code == 404
    assert empty.status_code == 422
    assert db.query(ChatMessage).filter(ChatMessage.id == other_message.id).one().content == "user-0"


def test_edit_stream_rebuilds_context_and_persists_regenerated_history(monkeypatch, db):
    rows = _add_timeline(db, pair_count=3)
    target = rows[2]
    captured: dict = {}

    async def fake_run(*args, **kwargs):
        captured["user_message"] = args[2]
        captured["history"] = kwargs["history"]
        captured["source_message_id"] = kwargs["source_message_id"]
        return AgentFinalResponse(message="regenerated answer")

    monkeypatch.setattr(chat_router.orchestrator, "run", fake_run)
    client = _client(db)
    try:
        response = client.patch(
            f"/api/v1/chat/messages/{target.id}",
            json={"content": "edited middle", "client_message_id": "edit-context-test"},
        )
        history_response = client.get("/api/v1/chat/history?page_size=100")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "regenerated answer" in response.text
    assert captured == {
        "user_message": "edited middle",
        "history": [
            {"role": "user", "content": "user-0"},
            {"role": "assistant", "content": "assistant-0"},
        ],
        "source_message_id": target.id,
    }
    active = list(reversed(history_response.json()["messages"]))
    assert [(row["role"], row["content"]) for row in active] == [
        ("user", "user-0"),
        ("assistant", "assistant-0"),
        ("user", "edited middle"),
        ("assistant", "regenerated answer"),
    ]


def test_concurrent_generation_rejects_edit_without_changing_history(db):
    target = _add_timeline(db, pair_count=1)[0]
    lock = chat_router._try_acquire_generation(1)
    assert lock is not None
    client = _client(db)
    try:
        response = client.patch(
            f"/api/v1/chat/messages/{target.id}", json={"content": "concurrent edit"}
        )
    finally:
        lock.release()
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert db.query(ChatMessage).filter(ChatMessage.id == target.id).one().content == "user-0"
