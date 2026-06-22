"""Phase 5.8 — Goal Intake Decision Gate + Financial Advisory tests."""
from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Category, FutureCommitment, Goal, Transaction, User
from app.models.agent_idempotency import PendingAgentIntent
from app.services.agent_orchestrator.goal_intake import (
    GOAL_INTENT_TYPE,
    STATE_AWAITING_CHOICE,
    STATE_COLLECTING_AMOUNT,
    STATE_COLLECTING_DATE,
    STATE_CONSULTATION,
    STATE_CONSUMED,
    GoalIntakeGate,
)
from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
from app.services.agent_orchestrator.types import (
    AgentFinalResponse,
    AgentOperationType,
    AgentPlan,
    AgentPlanStep,
    SourceScope,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

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
    session.add_all([
        User(id=1, phone="09120000001", name="Test", language="fa", chat_mode="normal"),
        User(id=2, phone="09120000002", name="Other", language="fa"),
        Category(id=1, name="Food", icon="f", color="#111", is_default=True),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()


def u(db) -> User:
    return db.query(User).filter(User.id == 1).first()


# ── Mock helpers ──────────────────────────────────────────────────────────────

class SequencePlanner:
    """Deterministic stub planner that returns plans in order."""
    def __init__(self, plans):
        self.plans = list(plans)
        self._last = None

    async def plan(self, *args, **kwargs):
        if self.plans:
            self._last = self.plans.pop(0)
            return self._last
        return AgentPlan(
            intent="final",
            final_response_hint=self._last.final_response_hint if self._last else "ثبت شد.",
        )


def _patch_detect(monkeypatch, data: dict):
    """Patch get_ai_chat_completion for detection calls to return structured JSON."""
    async def _fake(messages, **kwargs):
        return json.dumps(data)
    monkeypatch.setattr(
        "app.services.agent_orchestrator.goal_intake.get_ai_chat_completion",
        _fake,
    )


def _patch_detect_sequence(monkeypatch, responses: list[dict | str]):
    """Patch with a sequence of responses (dict → JSON, str → literal)."""
    calls = list(responses)

    async def _fake(messages, **kwargs):
        if calls:
            r = calls.pop(0)
            return json.dumps(r) if isinstance(r, dict) else r
        return json.dumps({})

    monkeypatch.setattr(
        "app.services.agent_orchestrator.goal_intake.get_ai_chat_completion",
        _fake,
    )


def _make_intent(db, user_id: int, item_title: str, amount=None, date_text=None, state=STATE_COLLECTING_AMOUNT):
    intent = PendingAgentIntent(
        user_id=user_id,
        intent_type=GOAL_INTENT_TYPE,
        payload_json={
            "item_title": item_title,
            "normalized_title": item_title.lower(),
            "target_amount": amount,
            "target_date_text": date_text,
            "source_message": "original msg",
            "state": state,
        },
        status="pending",
    )
    db.add(intent)
    db.commit()
    db.refresh(intent)
    return intent


# ── SECTION 1: Intent detection — item only ───────────────────────────────────

def test_goal_item_only_asks_amount(monkeypatch, db):
    """Item without amount → gate asks for amount, no goal inserted."""
    _patch_detect(monkeypatch, {
        "is_goal_like": True, "is_explicit_add": False,
        "is_commitment": False, "is_transaction": False,
        "item_title": "انگشتر طلا", "amount": None, "target_date_text": None,
    })
    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "میخوام انگشتر طلا بخرم", None, {}))
    assert response is not None
    assert "مبلغ" in response.message or "چه" in response.message
    assert response.metadata["goal_intake_state"] == STATE_COLLECTING_AMOUNT
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0


def test_goal_item_and_amount_asks_date(monkeypatch, db):
    """Item + amount without date → gate asks for target date."""
    _patch_detect(monkeypatch, {
        "is_goal_like": True, "is_explicit_add": False,
        "is_commitment": False, "is_transaction": False,
        "item_title": "لپتاپ", "amount": 200_000_000, "target_date_text": None,
    })
    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "میخوام لپتاپ بخرم ۲۰۰ میلیون", None, {}))
    assert response is not None
    assert "زمان" in response.message or "چه" in response.message
    assert response.metadata["goal_intake_state"] == STATE_COLLECTING_DATE
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0


def test_goal_all_details_asks_add_or_consult(monkeypatch, db):
    """Item + amount + date → gate asks add-or-consult, no goal inserted."""
    _patch_detect(monkeypatch, {
        "is_goal_like": True, "is_explicit_add": False,
        "is_commitment": False, "is_transaction": False,
        "item_title": "ماشین لباسشویی", "amount": 47_000_000, "target_date_text": "آخر خرداد",
    })
    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "میخوام ماشین لباسشویی بخرم ۴۷ میلیون آخر خرداد", None, {}))
    assert response is not None
    assert "اضافه" in response.message or "مشاوره" in response.message
    assert response.metadata["goal_intake_state"] == STATE_AWAITING_CHOICE
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0


# ── SECTION 2: Multi-turn collection ─────────────────────────────────────────

def test_amount_follow_up_advances_to_date(monkeypatch, db):
    """After amount question, user gives amount → advances to collecting date."""
    _make_intent(db, 1, "انگشتر طلا", amount=None, date_text=None, state=STATE_COLLECTING_AMOUNT)

    _patch_detect_sequence(monkeypatch, [
        {"amount": 100_000_000, "target_date_text": None},  # extraction call
    ])

    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "حدود ۱۰۰ میلیون", None, {}))
    assert response is not None
    assert response.metadata["goal_intake_state"] == STATE_COLLECTING_DATE
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0


def test_date_follow_up_advances_to_decision_gate(monkeypatch, db):
    """After date question, user gives date → shows add-or-consult question."""
    _make_intent(db, 1, "انگشتر طلا", amount=100_000_000, date_text=None, state=STATE_COLLECTING_DATE)

    _patch_detect_sequence(monkeypatch, [
        {"amount": None, "target_date_text": "آخر سال"},  # extraction call
    ])

    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "تا آخر سال", None, {}))
    assert response is not None
    assert "اضافه" in response.message or "مشاوره" in response.message
    assert response.metadata["goal_intake_state"] == STATE_AWAITING_CHOICE
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0


# ── SECTION 3: Add choice ─────────────────────────────────────────────────────

def test_add_choice_inserts_goal_exactly_once(monkeypatch, db):
    """After decision gate, 'اضافه کن' → exactly one goal inserted."""
    _make_intent(db, 1, "انگشتر طلا", amount=100_000_000, date_text="آخر سال", state=STATE_AWAITING_CHOICE)

    async def _fake_classify(messages, **kwargs):
        return "add"

    async def _fake_date_llm(messages, **kwargs):
        return json.dumps({
            "raw_text": "آخر سال",
            "resolved_date": "2026-12-31",
            "confidence": 0.9,
            "date_kind": "deadline",
            "interpretation_fa": "آخر سال میلادی",
            "needs_confirmation": False,
        })

    monkeypatch.setattr("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", _fake_classify)
    monkeypatch.setattr("app.services.agent_orchestrator.llm_date_resolver.get_ai_chat_completion", _fake_date_llm)

    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "اضافه کن", None, {}))
    assert response is not None
    assert "ثبت شد" in response.message or "هدف" in response.message
    assert response.metadata["goal_intake_state"] == STATE_CONSUMED
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1

    goal = db.query(Goal).filter(Goal.user_id == 1).first()
    assert goal.title == "انگشتر طلا"
    assert goal.target_amount == 100_000_000
    assert goal.status == "active"

    # Intent consumed
    intent = db.query(PendingAgentIntent).filter(PendingAgentIntent.user_id == 1).first()
    assert intent.status == "consumed"


def test_add_choice_does_not_duplicate_goal(monkeypatch, db):
    """Sending 'اضافه کن' twice does not create two goals."""
    _make_intent(db, 1, "انگشتر طلا", amount=100_000_000, date_text="آخر سال", state=STATE_AWAITING_CHOICE)

    async def _fake_classify(messages, **kwargs):
        return "add"

    async def _fake_date_llm(messages, **kwargs):
        return json.dumps({
            "raw_text": "آخر سال",
            "resolved_date": "2026-12-31",
            "confidence": 0.9,
            "date_kind": "deadline",
            "interpretation_fa": "آخر سال میلادی",
            "needs_confirmation": False,
        })

    monkeypatch.setattr("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", _fake_classify)
    monkeypatch.setattr("app.services.agent_orchestrator.llm_date_resolver.get_ai_chat_completion", _fake_date_llm)

    gate = GoalIntakeGate()
    response1 = asyncio.run(gate.process(db, u(db), "اضافه کن", None, {}))
    assert response1 is not None
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1

    # Re-insert same goal should be blocked by idempotency
    _make_intent(db, 1, "انگشتر طلا", amount=100_000_000, date_text="آخر سال", state=STATE_AWAITING_CHOICE)
    response2 = asyncio.run(gate.process(db, u(db), "ثبت کن", None, {}))
    assert response2 is not None
    assert "قبلاً ثبت" in response2.message or "وجود دارد" in response2.message
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1


# ── SECTION 4: Consult choice ─────────────────────────────────────────────────

def test_consult_choice_does_not_insert_goal(monkeypatch, db):
    """After decision gate, 'مشاوره بده' → no goal inserted, advisory returned."""
    _make_intent(db, 1, "انگشتر طلا", amount=100_000_000, date_text="آخر سال", state=STATE_AWAITING_CHOICE)

    # _classify_choice now always calls LLM (LLM-first architecture).
    # Use a sequential mock: first call = classify result, second call = advisory text.
    call_count = [0]
    async def _fake_llm(messages, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return "consult"  # classification
        return "با توجه به وضعیت مالی فعلیت، خرید انگشتر طلا نیاز به بررسی دارد. آیا این خرید برایت ضروری است؟"

    monkeypatch.setattr("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", _fake_llm)

    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "مشاوره بده", None, {}))
    assert response is not None
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0
    assert response.metadata["goal_intake_state"] == STATE_CONSULTATION

    intent = db.query(PendingAgentIntent).filter(PendingAgentIntent.user_id == 1).first()
    assert intent.payload_json["state"] == STATE_CONSULTATION


def test_consultation_add_after_advice_inserts_goal(monkeypatch, db):
    """After advisory conversation, 'حالا ثبتش کن' → goal inserted, intent consumed."""
    _make_intent(db, 1, "انگشتر طلا", amount=100_000_000, date_text="آخر سال", state=STATE_CONSULTATION)

    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "حالا ثبتش کن", None, {}))
    assert response is not None
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1
    assert response.metadata["goal_intake_state"] == STATE_CONSUMED


def test_consultation_continue_does_not_insert(monkeypatch, db):
    """Continuing advisory conversation without add choice → no goal."""
    _make_intent(db, 1, "انگشتر طلا", amount=100_000_000, date_text="آخر سال", state=STATE_CONSULTATION)

    async def _fake_llm(messages, **kwargs):
        return "سوال خوبیه. بگذار بیشتر بررسی کنیم."

    monkeypatch.setattr("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", _fake_llm)

    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "به نظرت چقدر منطقیه؟", None, {}))
    assert response is not None
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0
    assert response.metadata["goal_intake_state"] == STATE_CONSULTATION


# ── SECTION 5: Ambiguous choice ──────────────────────────────────────────────

def test_ambiguous_choice_asks_clarification(monkeypatch, db):
    """Ambiguous reply → ask clarification, no goal inserted."""
    _make_intent(db, 1, "لپتاپ", amount=200_000_000, date_text="ماه بعد", state=STATE_AWAITING_CHOICE)

    async def _fake_llm(messages, **kwargs):
        return "ambiguous"

    monkeypatch.setattr("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", _fake_llm)

    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "نمیدونم", None, {}))
    assert response is not None
    assert "ثبت" in response.message or "مشاوره" in response.message
    assert response.metadata["goal_intake_state"] == STATE_AWAITING_CHOICE
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0


# ── SECTION 6: Explicit add bypasses gate ─────────────────────────────────────

def test_explicit_goal_add_passes_through(monkeypatch, db):
    """Explicit 'یک هدف اضافه کن' with amount + date passes to orchestrator (returns None)."""
    _patch_detect(monkeypatch, {
        "is_goal_like": True, "is_explicit_add": True,
        "is_commitment": False, "is_transaction": False,
        "item_title": "ساعت طلا", "amount": 80_000_000, "target_date_text": "آخر سال",
    })
    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(
        db, u(db),
        "یک هدف جدید اضافه کن برای خرید ساعت طلا به مبلغ ۸۰ میلیون تا آخر سال",
        None, {}
    ))
    # Gate should return None → pass through to orchestrator
    assert response is None


def test_explicit_add_via_orchestrator_inserts_goal(db):
    """Explicit add via orchestrator uses SequencePlanner to insert exactly one goal."""
    plan = AgentPlan(
        intent="explicit_goal_add",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="g1",
                operation_type=AgentOperationType.insert,
                purpose="insert explicit goal",
                table_name="goals",
                sql="INSERT INTO goals (title, target_amount, deadline, status) VALUES (:title, :target_amount, :deadline, :status)",
                params={
                    "title": "ساعت طلا",
                    "target_amount": 80_000_000,
                    "deadline": "آخر سال",
                    "status": "active",
                },
                source_scope=SourceScope.current_message,
            )
        ],
        final_response_hint="هدف خرید ساعت طلا ثبت شد.",
    )

    async def _fake_gate(self, *args, **kwargs):
        return None  # gate passes through

    from unittest.mock import patch
    with patch.object(type(GoalIntakeGate()), "process", _fake_gate):
        result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
            db, u(db), "یک هدف جدید اضافه کن برای خرید ساعت طلا به مبلغ ۸۰ میلیون تا آخر سال"
        ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1
    goal = db.query(Goal).filter(Goal.user_id == 1).first()
    assert goal.title == "ساعت طلا"
    assert goal.target_amount == 80_000_000


# ── SECTION 7: Goal vs commitment vs transaction ──────────────────────────────

def test_commitment_passes_through_gate(monkeypatch, db):
    """'چک دارم' → gate returns None (commitment, not goal)."""
    _patch_detect(monkeypatch, {
        "is_goal_like": False, "is_explicit_add": False,
        "is_commitment": True, "is_transaction": False,
        "item_title": None, "amount": 50_000_000, "target_date_text": "ماه بعد",
    })
    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "چک دارم ماه بعد ۵۰ میلیون", None, {}))
    assert response is None  # pass through to orchestrator


def test_transaction_passes_through_gate(monkeypatch, db):
    """'خریدم ۴۰۰ هزار تومان' → gate returns None (transaction)."""
    _patch_detect(monkeypatch, {
        "is_goal_like": False, "is_explicit_add": False,
        "is_commitment": False, "is_transaction": True,
        "item_title": None, "amount": 400_000, "target_date_text": None,
    })
    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "دیروز ۴۰۰ هزار تومان خرید کردم", None, {}))
    assert response is None


def test_washing_machine_is_goal_not_commitment(monkeypatch, db):
    """Desire wording 'میخام بخرم' → treated as goal-like by gate."""
    _patch_detect(monkeypatch, {
        "is_goal_like": True, "is_explicit_add": False,
        "is_commitment": False, "is_transaction": False,
        "item_title": "ماشین لباسشویی", "amount": 47_000_000, "target_date_text": "آخر خرداد",
    })
    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "میخام تا آخر خرداد ماشین لباسشویی بخرم ۴۷ میلیون", None, {}))
    assert response is not None
    assert response.metadata["goal_intake_state"] == STATE_AWAITING_CHOICE
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 0


# ── SECTION 8: Advisory uses financial context ─────────────────────────────────

def test_advisory_uses_finance_context(monkeypatch, db):
    """Advisory response should be returned; no goal inserted; consultation state set."""
    _make_intent(db, 1, "لپتاپ", amount=200_000_000, date_text="۶ ماه دیگه", state=STATE_AWAITING_CHOICE)

    received_messages: list = []
    call_count = [0]

    async def _fake_llm(messages, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return "consult"  # _classify_choice call
        received_messages.extend(messages)
        return "با توجه به بودجه باقی‌مانده‌ات، این خرید قابل مدیریت است. آیا اولویتت در حال حاضر این لپتاپ است؟"

    monkeypatch.setattr("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", _fake_llm)

    finance_context = {
        "budget": 5_000_000,
        "total_spent_this_month": 3_000_000,
        "remaining_budget": 2_000_000,
        "total_income_this_month": 8_000_000,
        "active_goals": [],
        "future_commitments": [],
    }
    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "مشاوره بده", None, finance_context))
    assert response is not None
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0
    assert response.metadata["goal_intake_state"] == STATE_CONSULTATION
    # Advisory LLM was called
    assert len(received_messages) > 0


def test_advisory_no_fake_numbers(monkeypatch, db):
    """Advisory should use real data from finance context, not invent numbers."""
    _make_intent(db, 1, "رینگ اسپورت", amount=20_000_000, date_text="ماه آینده", state=STATE_AWAITING_CHOICE)

    captured_content = []
    call_count = [0]

    async def _fake_llm(messages, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return "consult"  # _classify_choice call
        # Capture what the advisory prompt receives
        for m in messages:
            captured_content.append(m.get("content", ""))
        return "با توجه به بودجه فعلیت، بررسی بیشتر لازم است. آیا این خرید برای هدف بلندمدتت ضروری است؟"

    monkeypatch.setattr("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", _fake_llm)

    finance_context = {
        "budget": 10_000_000,
        "total_spent_this_month": 7_000_000,
        "remaining_budget": 3_000_000,
        "total_income_this_month": 12_000_000,
        "active_goals": [{"title": "لپتاپ", "target_amount": 200_000_000, "remaining_amount": 200_000_000}],
        "future_commitments": [],
    }
    gate = GoalIntakeGate()
    asyncio.run(gate.process(db, u(db), "مشاوره بده", None, finance_context))

    # Finance context must be included in advisory prompt
    full_text = " ".join(captured_content)
    assert "budget" in full_text or "بودجه" in full_text or "10000000" in full_text or "10,000,000" in full_text


# ── SECTION 9: Idempotency ────────────────────────────────────────────────────

def test_repeated_add_after_consume_does_not_duplicate(db):
    """After goal is inserted and intent consumed, repeating 'اضافه کن' reports already exists."""
    # Create and immediately consume intent (goal already inserted)
    _make_intent(db, 1, "لپتاپ", amount=200_000_000, date_text="ماه بعد", state=STATE_AWAITING_CHOICE)
    goal = Goal(user_id=1, title="لپتاپ", target_amount=200_000_000, current_amount=0, is_active=True)
    db.add(goal)
    db.commit()

    gate = GoalIntakeGate()
    # New intent with same goal
    _make_intent(db, 1, "لپتاپ", amount=200_000_000, date_text="ماه بعد", state=STATE_AWAITING_CHOICE)
    response = asyncio.run(gate.process(db, u(db), "ثبت کن", None, {}))
    assert response is not None
    assert "قبلاً" in response.message or "وجود دارد" in response.message
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1


def test_stale_intent_cancelled_on_new_goal(monkeypatch, db):
    """Starting a new goal-like message cancels old pending intent."""
    # Existing intent
    old_intent = _make_intent(db, 1, "انگشتر طلا", amount=None, state=STATE_COLLECTING_AMOUNT)

    _patch_detect(monkeypatch, {
        "is_goal_like": True, "is_explicit_add": False,
        "is_commitment": False, "is_transaction": False,
        "item_title": "لپتاپ", "amount": None, "target_date_text": None,
    })

    gate = GoalIntakeGate()
    asyncio.run(gate.process(db, u(db), "میخوام لپتاپ بخرم", None, {}))

    # Old intent must be cancelled
    db.refresh(old_intent)
    assert old_intent.status == "consumed"
    assert old_intent.payload_json["state"] == "cancelled"

    # New intent should be for لپتاپ
    new_intent = (
        db.query(PendingAgentIntent)
        .filter(PendingAgentIntent.user_id == 1, PendingAgentIntent.status == "pending")
        .first()
    )
    assert new_intent is not None
    assert new_intent.payload_json["item_title"] == "لپتاپ"


# ── SECTION 10: History cannot re-trigger intake ──────────────────────────────

def test_history_context_does_not_start_new_intake(monkeypatch, db):
    """A greeting with history of a goal conversation must not restart goal intake."""
    # No active intent
    _patch_detect(monkeypatch, {
        "is_goal_like": False, "is_explicit_add": False,
        "is_commitment": False, "is_transaction": False,
        "item_title": None, "amount": None, "target_date_text": None,
    })
    history = [
        {"role": "user", "content": "میخوام انگشتر طلا بخرم"},
        {"role": "assistant", "content": "حدوداً چه مبلغی در نظر داری؟"},
    ]
    gate = GoalIntakeGate()
    response = asyncio.run(gate.process(db, u(db), "سلام", history, {}))
    assert response is None  # no active intent, not goal-like → pass through
    assert db.query(PendingAgentIntent).filter(PendingAgentIntent.user_id == 1).count() == 0


# ── SECTION 11: User-scoping ──────────────────────────────────────────────────

def test_goal_intake_is_user_scoped(monkeypatch, db):
    """User 1's intent is invisible to user 2."""
    _make_intent(db, 1, "لپتاپ", amount=200_000_000, state=STATE_AWAITING_CHOICE)

    user2 = db.query(User).filter(User.id == 2).first()
    gate = GoalIntakeGate()

    _patch_detect(monkeypatch, {
        "is_goal_like": False, "is_explicit_add": False,
        "is_commitment": False, "is_transaction": False,
        "item_title": None, "amount": None, "target_date_text": None,
    })
    response = asyncio.run(gate.process(db, user2, "سلام", None, {}))
    # User2 should not see user1's intent
    assert response is None


# ── SECTION 12: Provider abstraction ─────────────────────────────────────────

def test_gate_uses_provider_abstraction(monkeypatch, db):
    """GoalIntakeGate uses get_ai_chat_completion (provider-agnostic)."""
    call_log = []

    async def _spy(messages, **kwargs):
        call_log.append(messages)
        return json.dumps({
            "is_goal_like": True, "is_explicit_add": False,
            "is_commitment": False, "is_transaction": False,
            "item_title": "لپتاپ", "amount": None, "target_date_text": None,
        })

    monkeypatch.setattr("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", _spy)

    gate = GoalIntakeGate()
    asyncio.run(gate.process(db, u(db), "میخوام لپتاپ بخرم", None, {}))

    # Must have used the abstracted provider
    assert len(call_log) >= 1
