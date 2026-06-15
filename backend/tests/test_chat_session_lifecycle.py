from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.db import Base, get_db
from app.main import app
from app.models import (
    BehaviorInsight,
    Budget,
    Category,
    ChatMessage,
    FinancialFact,
    FinancialMemory,
    FinancialPersona,
    FinancialWarning,
    FutureCommitment,
    Goal,
    Transaction,
    User,
)
from app.models.agent_idempotency import PendingAgentIntent
from app.models.chat import MessageRole
from app.models.transaction import TransactionType
from app.services.agent_orchestrator.goal_intake import (
    GOAL_INTENT_TYPE,
    STATE_AWAITING_CHOICE,
    STATE_CANCELLED,
    STATE_COLLECTING_AMOUNT,
    STATE_CONSULTATION,
)
from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
from app.services.agent_orchestrator.types import AgentOperationType, AgentPlan, AgentPlanStep, SourceScope
from app.services.chat_session_lifecycle import clear_chat_history_and_transient_state


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
            Category(id=1, name="Transport", icon="t", color="#111", is_default=True),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def current_user(db) -> User:
    return db.query(User).filter(User.id == 1).first()


class SequencePlanner:
    def __init__(self, plans):
        self.plans = list(plans)
        self.calls = 0
        self._last: AgentPlan | None = None

    async def plan(self, *args, **kwargs):
        self.calls += 1
        if self.plans:
            self._last = self.plans.pop(0)
            return self._last
        return AgentPlan(
            intent=self._last.intent if self._last else "final",
            final_response_hint=self._last.final_response_hint if self._last else "",
        )


def _make_intent(db, state: str, user_id: int = 1, title: str = "wired speaker") -> PendingAgentIntent:
    intent = PendingAgentIntent(
        user_id=user_id,
        intent_type=GOAL_INTENT_TYPE,
        payload_json={
            "item_title": title,
            "target_amount": 17_000_000,
            "target_date_text": "two weeks",
            "state": state,
        },
        status="pending",
    )
    db.add(intent)
    db.commit()
    db.refresh(intent)
    return intent


def _patch_gate_detect_as_transaction(monkeypatch):
    async def _fake(messages, **kwargs):
        return json.dumps(
            {
                "is_goal_like": False,
                "is_explicit_add": False,
                "is_commitment": False,
                "is_transaction": True,
                "item_title": None,
                "amount": 300_000,
                "target_date_text": None,
            }
        )

    monkeypatch.setattr("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", _fake)


def _taxi_insert_plan() -> AgentPlan:
    return AgentPlan(
        intent="expense_registration",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="tx",
                operation_type=AgentOperationType.insert,
                purpose="record taxi expense from current message",
                table_name="transactions",
                sql="INSERT INTO transactions (category_id, amount, type, description, date) VALUES (:category_id, :amount, :type, :description, :date)",
                params={
                    "category_id": 1,
                    "amount": 300_000,
                    "type": "expense",
                    "description": "taxi",
                    "date": "2026-06-15",
                },
                source_scope=SourceScope.current_message,
            )
        ],
        final_response_hint="Taxi expense recorded.",
    )


def test_clear_history_cancels_pending_goal_intake(db):
    intent = _make_intent(db, STATE_COLLECTING_AMOUNT)
    db.add(ChatMessage(user_id=1, role=MessageRole.user, content="old goal flow"))
    db.commit()

    result = clear_chat_history_and_transient_state(db, 1)

    db.refresh(intent)
    assert result.cleared_messages == 1
    assert result.cancelled_pending_intents == 1
    assert result.cancelled_advisory_sessions == 0
    assert intent.status == "cancelled"
    assert intent.payload_json["state"] == STATE_CANCELLED
    assert intent.consumed_at is not None


def test_clear_history_cancels_advisory_session_then_taxi_expense_is_fresh(monkeypatch, db):
    intent = _make_intent(db, STATE_CONSULTATION, title="wired speaker")
    clear_result = clear_chat_history_and_transient_state(db, 1)
    assert clear_result.cancelled_advisory_sessions == 1
    db.refresh(intent)
    assert intent.status == "cancelled"

    _patch_gate_detect_as_transaction(monkeypatch)
    planner = SequencePlanner([_taxi_insert_plan()])
    response = asyncio.run(
        AgentOrchestrator(planner=planner).run(
            db,
            current_user(db),
            "300 thousand toman taxi today",
            history=[],
        )
    )

    assert db.query(Transaction).filter(Transaction.user_id == 1, Transaction.amount == 300_000).count() == 1
    assert "speaker" not in response.message.lower()
    assert "wired" not in response.message.lower()
    assert "Taxi" in response.message or "taxi" in response.message


def test_clear_history_does_not_delete_durable_financial_data(db):
    db.add_all(
        [
            ChatMessage(user_id=1, role=MessageRole.user, content="old message"),
            Goal(user_id=1, title="wired speaker", target_amount=17_000_000, current_amount=0, is_active=True),
            Transaction(user_id=1, category_id=1, amount=100_000, type=TransactionType.expense, description="bus"),
            FutureCommitment(user_id=1, title="rent", amount=20_000_000, status="pending"),
            Budget(user_id=1, month=3, year=1405, amount=80_000_000),
            FinancialMemory(user_id=1, memory_type="preference", title="saving", content_json={"x": 1}),
            FinancialFact(user_id=1, fact_type="income_note", subject="salary", value_json={"x": 1}),
            FinancialPersona(user_id=1, financial_literacy_level="medium"),
            BehaviorInsight(user_id=1, insight_type="stress_spending", evidence_json={"x": 1}),
            FinancialWarning(user_id=1, warning_type="budget", severity="info", message="watch budget", evidence_json={"x": 1}),
        ]
    )
    _make_intent(db, STATE_AWAITING_CHOICE)
    db.commit()

    result = clear_chat_history_and_transient_state(db, 1)

    assert result.cleared_messages == 1
    assert db.query(ChatMessage).filter(ChatMessage.user_id == 1).count() == 0
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 1
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 1
    assert db.query(Budget).filter(Budget.user_id == 1).count() == 1
    assert db.query(FinancialMemory).filter(FinancialMemory.user_id == 1).count() == 1
    assert db.query(FinancialFact).filter(FinancialFact.user_id == 1).count() == 1
    assert db.query(FinancialPersona).filter(FinancialPersona.user_id == 1).count() == 1
    assert db.query(BehaviorInsight).filter(BehaviorInsight.user_id == 1).count() == 1
    assert db.query(FinancialWarning).filter(FinancialWarning.user_id == 1).count() == 1


def test_orchestrator_ignores_cancelled_pending_intent(monkeypatch, db):
    intent = _make_intent(db, STATE_COLLECTING_AMOUNT)
    intent.status = "cancelled"
    intent.payload_json = {**intent.payload_json, "state": STATE_CANCELLED}
    db.commit()

    async def _fake_detect(messages, **kwargs):
        return json.dumps(
            {
                "is_goal_like": False,
                "is_explicit_add": False,
                "is_commitment": False,
                "is_transaction": False,
                "item_title": None,
                "amount": None,
                "target_date_text": None,
            }
        )

    monkeypatch.setattr("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", _fake_detect)
    planner = SequencePlanner(
        [
            AgentPlan(
                intent="ambiguous_amount",
                requires_db=False,
                clarification_question="What should I do with this amount?",
            )
        ]
    )

    response = asyncio.run(AgentOrchestrator(planner=planner).run(db, current_user(db), "100 million"))

    assert planner.calls == 1
    assert "What should I do" in response.message
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0


def test_simple_expense_after_clear_has_no_stale_goal_advisory(monkeypatch, db):
    _make_intent(db, STATE_CONSULTATION, title="wired speaker")
    clear_chat_history_and_transient_state(db, 1)

    _patch_gate_detect_as_transaction(monkeypatch)
    response = asyncio.run(
        AgentOrchestrator(planner=SequencePlanner([_taxi_insert_plan()])).run(
            db,
            current_user(db),
            "300 thousand toman taxi today",
        )
    )

    assert db.query(Transaction).filter(Transaction.user_id == 1, Transaction.description == "taxi").count() == 1
    assert "speaker" not in response.message.lower()
    assert "savings plan" not in response.message.lower()


def test_explicit_goal_question_after_clear_uses_durable_goal_not_transient_session(monkeypatch, db):
    db.add(Goal(user_id=1, title="wired speaker", target_amount=17_000_000, current_amount=0, is_active=True))
    db.commit()
    _make_intent(db, STATE_CONSULTATION, title="wired speaker")
    clear_chat_history_and_transient_state(db, 1)

    async def _fake_detect(messages, **kwargs):
        return json.dumps(
            {
                "is_goal_like": False,
                "is_explicit_add": False,
                "is_commitment": False,
                "is_transaction": False,
                "item_title": None,
                "amount": None,
                "target_date_text": None,
            }
        )

    monkeypatch.setattr("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", _fake_detect)
    plan = AgentPlan(
        intent="goal_question",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="goals",
                operation_type=AgentOperationType.select,
                purpose="read active goals",
                table_name="goals",
                sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE is_active = :active",
                params={"active": True},
                source_scope=SourceScope.current_message,
            )
        ],
    )

    response = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(db, current_user(db), "what happened to my wired speaker goal?"))

    assert "wired speaker" in response.message
    assert db.query(PendingAgentIntent).filter(PendingAgentIntent.status == "pending").count() == 0


def test_clear_history_endpoint_returns_counts_and_waits_for_backend_cleanup(db):
    _make_intent(db, STATE_CONSULTATION)
    _make_intent(db, STATE_COLLECTING_AMOUNT)
    db.add_all(
        [
            ChatMessage(user_id=1, role=MessageRole.user, content="hello"),
            ChatMessage(user_id=1, role=MessageRole.assistant, content="hi"),
        ]
    )
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current_user(db)
    client = TestClient(app)
    try:
        response = client.delete("/api/v1/chat/history")
        assert response.status_code == 200
        assert response.json() == {
            "cleared_messages": 2,
            "cancelled_pending_intents": 2,
            "cancelled_advisory_sessions": 1,
        }
        assert db.query(ChatMessage).filter(ChatMessage.user_id == 1).count() == 0
        assert db.query(PendingAgentIntent).filter(PendingAgentIntent.user_id == 1, PendingAgentIntent.status == "pending").count() == 0
    finally:
        app.dependency_overrides.clear()
