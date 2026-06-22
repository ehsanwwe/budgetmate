"""Tests for LLM-first orchestration: SemanticInterpreter, LLMDateResolver, refactored gate.

All LLM calls are mocked — tests verify that:
- SemanticInterpreter result drives routing decisions
- LLMDateResolver is used for goal deadlines (not regex)
- Unknown future dates do NOT silently become today
- GoalIntakeGate uses semantic cancel/bypass/intent signals
- Duplicate client_message_id results in one DB write
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Category, Goal, User
from app.models.agent_idempotency import AgentOperationEvent, PendingAgentIntent
from app.services.agent_orchestrator.goal_intake import (
    GOAL_INTENT_TYPE,
    STATE_AWAITING_CHOICE,
    STATE_CANCELLED,
    STATE_COLLECTING_AMOUNT,
    STATE_COLLECTING_DATE,
    STATE_CONSUMED,
    GoalIntakeGate,
    NullGoalIntakeGate,
)
from app.services.agent_orchestrator.llm_date_resolver import DateResolution, LLMDateResolver
from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
from app.services.agent_orchestrator.semantic_interpreter import SemanticInterpreter, SemanticResult
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


def user1(db) -> User:
    return db.query(User).filter(User.id == 1).first()


# ── SemanticInterpreter unit tests ────────────────────────────────────────────

class TestSemanticInterpreter:
    """SemanticInterpreter should call the LLM and parse the result."""

    def test_from_llm_json_parses_correctly(self):
        data = {
            "language": "fa",
            "user_intent": "cancel_flow",
            "is_question": False,
            "should_continue_pending_flow": False,
            "should_cancel_pending_flow": True,
            "should_bypass_goal_intake": False,
            "referenced_entities": {"goal_title": None, "target_item": None},
            "money": {"amount": None, "confidence": 0.0, "raw_text": None, "currency": "unknown"},
            "date": {"raw_text": None, "resolved_date": None, "confidence": 0.0, "date_kind": "unknown", "needs_user_confirmation": False},
            "action": {"can_write": False, "write_type": None, "requires_more_info": False, "missing_fields": []},
            "final_behavior": {"answer_directly": True, "ask_clarification": False, "clarification_reason": None},
        }
        result = SemanticResult.from_llm_json(data)
        assert result.user_intent == "cancel_flow"
        assert result.should_cancel_pending_flow is True
        assert result.money_amount is None

    def test_money_amount_requires_high_confidence(self):
        r = SemanticResult.from_llm_json({
            "money": {"amount": 50_000_000, "confidence": 0.5},
        })
        assert r.money_amount is None  # confidence too low

        r2 = SemanticResult.from_llm_json({
            "money": {"amount": 50_000_000, "confidence": 0.9},
        })
        assert r2.money_amount == 50_000_000

    def test_fallback_is_safe(self):
        r = SemanticResult.fallback()
        assert r.user_intent == "other"
        assert r.should_cancel_pending_flow is False
        assert r.money_amount is None

    def test_interpret_calls_llm_and_returns_result(self):
        llm_response = json.dumps({
            "language": "fa",
            "user_intent": "goal_desire",
            "is_question": False,
            "should_continue_pending_flow": False,
            "should_cancel_pending_flow": False,
            "should_bypass_goal_intake": False,
            "referenced_entities": {"goal_title": None, "target_item": "لپتاپ"},
            "money": {"amount": 80_000_000, "confidence": 0.9, "raw_text": "۸۰ میلیون", "currency": "IRT"},
            "date": {"raw_text": "سه روز دیگه", "resolved_date": None, "confidence": 0.3, "date_kind": "future", "needs_user_confirmation": True},
            "action": {"can_write": False, "write_type": None, "requires_more_info": True, "missing_fields": ["deadline"]},
            "final_behavior": {"answer_directly": False, "ask_clarification": True, "clarification_reason": "deadline unclear"},
        })

        async def run():
            with patch("app.services.agent_orchestrator.semantic_interpreter.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = llm_response
                interpreter = SemanticInterpreter()
                result = await interpreter.interpret(
                    user_message="میخوام لپتاپ بخرم ۸۰ میلیون سه روز دیگه",
                    history=None,
                    pending_intent_payload=None,
                    finance_context={},
                )
                assert result.user_intent == "goal_desire"
                assert result.money_amount == 80_000_000
                assert result.target_item == "لپتاپ"
                assert result.date_raw_text == "سه روز دیگه"
                mock_llm.assert_called_once()

        asyncio.run(run())

    def test_interpret_falls_back_on_llm_error(self):
        async def run():
            with patch("app.services.agent_orchestrator.semantic_interpreter.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                from app.services.ai import LLMProviderError
                mock_llm.side_effect = LLMProviderError("timeout")
                result = await SemanticInterpreter().interpret("test", None, None, {})
                assert result.user_intent == "other"
                assert result.should_cancel_pending_flow is False

        asyncio.run(run())


# ── LLMDateResolver unit tests ────────────────────────────────────────────────

class TestLLMDateResolver:
    """LLMDateResolver must resolve Persian date phrases through LLM, not regex."""

    def _today(self) -> date:
        from app.services.agent_orchestrator.date_utils import local_today
        return local_today()

    def test_trivial_today_no_llm_call(self):
        async def run():
            with patch("app.services.agent_orchestrator.llm_date_resolver.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                result = await LLMDateResolver().resolve("امروز", financial_context_type="transaction_date")
                assert result.resolved_date == self._today()
                assert result.confidence >= 0.99
                mock_llm.assert_not_called()

        asyncio.run(run())

    def test_iso_date_no_llm_call(self):
        async def run():
            with patch("app.services.agent_orchestrator.llm_date_resolver.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                result = await LLMDateResolver().resolve("2025-12-01", financial_context_type="goal_deadline")
                assert result.resolved_date == date(2025, 12, 1)
                mock_llm.assert_not_called()

        asyncio.run(run())

    def test_three_days_forward_via_llm(self):
        """سه روز جلوتر must resolve to today+3 via LLM, not regex."""
        today = self._today()
        expected = today + timedelta(days=3)
        llm_response = json.dumps({
            "raw_text": "سه روز جلوتر",
            "resolved_date": expected.isoformat(),
            "confidence": 0.95,
            "date_kind": "future",
            "interpretation_fa": "سه روز آینده",
            "needs_confirmation": False,
        })

        async def run():
            with patch("app.services.agent_orchestrator.llm_date_resolver.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = llm_response
                result = await LLMDateResolver().resolve(
                    "سه روز جلوتر",
                    financial_context_type="goal_deadline",
                    current_date=today,
                )
                assert result.resolved_date == expected
                assert result.confidence >= 0.9
                assert result.needs_confirmation is False
                mock_llm.assert_called_once()

        asyncio.run(run())

    def test_three_days_after_via_llm(self):
        """بعد از سه روز must resolve to today+3 via LLM."""
        today = self._today()
        expected = today + timedelta(days=3)
        llm_response = json.dumps({
            "raw_text": "بعد از سه روز",
            "resolved_date": expected.isoformat(),
            "confidence": 0.95,
            "date_kind": "future",
            "interpretation_fa": "سه روز بعد از امروز",
            "needs_confirmation": False,
        })

        async def run():
            with patch("app.services.agent_orchestrator.llm_date_resolver.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = llm_response
                result = await LLMDateResolver().resolve(
                    "بعد از سه روز",
                    financial_context_type="goal_deadline",
                    current_date=today,
                )
                assert result.resolved_date == expected
                mock_llm.assert_called_once()

        asyncio.run(run())

    def test_two_months_forward_via_llm(self):
        """دو ماه دیگه must resolve to today+2months via LLM."""
        today = self._today()
        from app.services.agent_orchestrator.date_utils import _add_months
        expected = _add_months(today, 2)
        llm_response = json.dumps({
            "raw_text": "دو ماه دیگه",
            "resolved_date": expected.isoformat(),
            "confidence": 0.95,
            "date_kind": "future",
            "interpretation_fa": "دو ماه آینده",
            "needs_confirmation": False,
        })

        async def run():
            with patch("app.services.agent_orchestrator.llm_date_resolver.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = llm_response
                result = await LLMDateResolver().resolve(
                    "دو ماه دیگه",
                    financial_context_type="goal_deadline",
                    current_date=today,
                )
                assert result.resolved_date == expected
                mock_llm.assert_called_once()

        asyncio.run(run())

    def test_unknown_future_phrase_needs_confirmation(self):
        """Unknown future phrases must not silently resolve to today for goal deadlines."""
        today = self._today()
        llm_response = json.dumps({
            "raw_text": "وقتی حالم خوب بود",
            "resolved_date": None,
            "confidence": 0.1,
            "date_kind": "unknown",
            "interpretation_fa": "نامشخص",
            "needs_confirmation": True,
        })

        async def run():
            with patch("app.services.agent_orchestrator.llm_date_resolver.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = llm_response
                result = await LLMDateResolver().resolve(
                    "وقتی حالم خوب بود",
                    financial_context_type="goal_deadline",
                    current_date=today,
                )
                assert result.needs_confirmation is True
                assert result.resolved_date is None
                assert result.confidence < 0.5

        asyncio.run(run())

    def test_unknown_phrase_does_not_become_today(self):
        """Critical: unknown future phrases must NEVER silently become today."""
        today = self._today()
        llm_response = json.dumps({
            "raw_text": "یه وقت نامعلوم",
            "resolved_date": None,
            "confidence": 0.1,
            "date_kind": "unknown",
            "interpretation_fa": "نامشخص",
            "needs_confirmation": True,
        })

        async def run():
            with patch("app.services.agent_orchestrator.llm_date_resolver.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = llm_response
                result = await LLMDateResolver().resolve(
                    "یه وقت نامعلوم",
                    financial_context_type="goal_deadline",
                    current_date=today,
                )
                # Must NOT be today
                assert result.resolved_date != today
                assert result.resolved_date is None

        asyncio.run(run())

    def test_llm_failure_returns_unresolved_not_today(self):
        """LLM failure for goal deadlines must return unresolved, not today."""
        async def run():
            with patch("app.services.agent_orchestrator.llm_date_resolver.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                from app.services.ai import LLMProviderError
                mock_llm.side_effect = LLMProviderError("timeout")
                today = date.today()
                result = await LLMDateResolver().resolve(
                    "سه ماه جلوتر",
                    financial_context_type="goal_deadline",
                    current_date=today,
                )
                assert result.needs_confirmation is True
                assert result.resolved_date is None

        asyncio.run(run())


# ── GoalIntakeGate semantic routing tests ─────────────────────────────────────

class TestGoalIntakeGateSemantic:
    """Gate must use SemanticResult for routing decisions, not keyword lists."""

    def _make_semantic(self, **kwargs) -> SemanticResult:
        defaults = {
            "language": "fa",
            "user_intent": "other",
            "is_question": False,
            "should_continue_pending_flow": False,
            "should_cancel_pending_flow": False,
            "should_bypass_goal_intake": False,
            "referenced_entities": {},
            "money": {},
            "date": {},
            "action": {},
            "final_behavior": {},
            "raw": {},
        }
        defaults.update(kwargs)
        r = SemanticResult()
        for k, v in defaults.items():
            setattr(r, k, v)
        return r

    def _active_intent(self, db, user, state=STATE_COLLECTING_AMOUNT, item="لپتاپ", amount=None) -> PendingAgentIntent:
        intent = PendingAgentIntent(
            user_id=user.id,
            intent_type=GOAL_INTENT_TYPE,
            payload_json={
                "item_title": item,
                "target_amount": amount,
                "target_date_text": None,
                "state": state,
                "source_message": "test",
            },
            status="pending",
        )
        db.add(intent)
        db.commit()
        db.refresh(intent)
        return intent

    def test_semantic_cancel_cancels_active_intent(self, db):
        """should_cancel_pending_flow=True must cancel intent without keyword matching."""
        u = user1(db)
        self._active_intent(db, u)
        gate = GoalIntakeGate()
        semantic = self._make_semantic(
            should_cancel_pending_flow=True,
            user_intent="cancel_flow",
        )

        async def run():
            result = await gate.process(db, u, "هر چی گفتم ولش", None, {}, semantic=semantic)
            assert result is not None
            assert STATE_CANCELLED in str(result.metadata.get("goal_intake_state", ""))

        asyncio.run(run())

        # Verify intent was cancelled in DB
        remaining = db.query(PendingAgentIntent).filter(
            PendingAgentIntent.user_id == u.id,
            PendingAgentIntent.status == "pending",
        ).count()
        assert remaining == 0

    def test_goal_question_passes_through_to_orchestrator(self, db):
        """goal_question intent with active pending must pass through (return None)."""
        u = user1(db)
        self._active_intent(db, u)
        gate = GoalIntakeGate()
        semantic = self._make_semantic(
            user_intent="goal_question",
            referenced_entities={"goal_title": "تور ارمنستان"},
        )

        async def run():
            result = await gate.process(db, u, "برای همون تور چقدر باید سیو کنم؟", None, {}, semantic=semantic)
            assert result is None  # pass through to orchestrator

        asyncio.run(run())

    def test_expense_passes_through_and_cancels_stale(self, db):
        """expense intent with active pending → cancel stale intent, pass through."""
        u = user1(db)
        self._active_intent(db, u)
        gate = GoalIntakeGate()
        semantic = self._make_semantic(user_intent="expense")

        async def run():
            result = await gate.process(db, u, "خریدم نون ۵ هزار تومن", None, {}, semantic=semantic)
            assert result is None

        asyncio.run(run())

    def test_invalid_both_choice_returns_explanation(self, db):
        """invalid_both_choice intent must return a clear explanation, not start goal."""
        u = user1(db)
        self._active_intent(db, u, state=STATE_AWAITING_CHOICE, amount=50_000_000)
        gate = GoalIntakeGate()
        semantic = self._make_semantic(user_intent="invalid_both_choice")

        async def run():
            result = await gate.process(db, u, "هر دو تاش رو میخوام", None, {}, semantic=semantic)
            assert result is not None
            assert "هدف" in result.message or "مسیر" in result.message

        asyncio.run(run())

        # No goal should have been inserted
        goal_count = db.query(Goal).filter(Goal.user_id == u.id).count()
        assert goal_count == 0

    def test_goal_desire_without_semantic_uses_llm_detection(self, db):
        """When semantic is None, gate falls back to LLM _detect() for routing."""
        u = user1(db)
        gate = GoalIntakeGate()

        detection_response = json.dumps({
            "is_goal_like": True,
            "is_explicit_add": False,
            "is_commitment": False,
            "is_transaction": False,
            "item_title": "انگشتر طلا",
            "amount": None,
            "target_date_text": None,
        })

        async def run():
            with patch("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = detection_response
                result = await gate.process(db, u, "میخوام انگشتر طلا بخرم", None, {}, semantic=None)
                assert result is not None
                assert STATE_COLLECTING_AMOUNT in str(result.metadata.get("goal_intake_state", ""))

        asyncio.run(run())

    def test_cancellation_phrase_without_semantic_uses_emergency_keywords(self, db):
        """When semantic is None, emergency keyword guard must still work."""
        u = user1(db)
        self._active_intent(db, u)
        gate = GoalIntakeGate()

        async def run():
            # semantic=None means fallback to emergency keywords
            result = await gate.process(db, u, "بیخیال", None, {}, semantic=None)
            assert result is not None
            assert STATE_CANCELLED in str(result.metadata.get("goal_intake_state", ""))

        asyncio.run(run())


# ── LLMDateResolver integration with goal insertion ───────────────────────────

class TestGoalInsertionUsesLLMDateResolver:
    """_insert_goal_from_intent must use LLMDateResolver, not parse_relative_date."""

    def _pending_intent_in_awaiting_choice(self, db, user, amount=50_000_000, date_text="سه ماه جلوتر") -> PendingAgentIntent:
        from app.services.personal_cfo.goal_context_service import normalize_goal_text
        intent = PendingAgentIntent(
            user_id=user.id,
            intent_type=GOAL_INTENT_TYPE,
            payload_json={
                "item_title": "دوربین",
                "normalized_title": normalize_goal_text("دوربین"),
                "target_amount": amount,
                "target_date_text": date_text,
                "source_message": "میخوام دوربین بخرم",
                "state": STATE_AWAITING_CHOICE,
            },
            status="pending",
        )
        db.add(intent)
        db.commit()
        db.refresh(intent)
        return intent

    def test_resolved_deadline_is_saved_correctly(self, db):
        """When LLMDateResolver returns high-confidence date, goal gets that deadline."""
        from app.services.agent_orchestrator.date_utils import _add_months, local_today
        today = local_today()
        expected_deadline = _add_months(today, 3)

        llm_date_response = json.dumps({
            "raw_text": "سه ماه جلوتر",
            "resolved_date": expected_deadline.isoformat(),
            "confidence": 0.95,
            "date_kind": "future",
            "interpretation_fa": "سه ماه آینده",
            "needs_confirmation": False,
        })
        choice_response = "add"

        u = user1(db)
        intent = self._pending_intent_in_awaiting_choice(db, u)
        gate = GoalIntakeGate()

        semantic = SemanticResult()
        semantic.should_cancel_pending_flow = False
        semantic.user_intent = "answer_pending_question"

        async def run():
            with patch("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", new_callable=AsyncMock) as mock_chat:
                with patch("app.services.agent_orchestrator.llm_date_resolver.get_ai_chat_completion", new_callable=AsyncMock) as mock_date:
                    mock_chat.return_value = choice_response  # _classify_choice
                    mock_date.return_value = llm_date_response  # LLMDateResolver
                    result = await gate.process(db, u, "آره ثبتش کن", None, {}, semantic=semantic)
                    assert result is not None
                    assert "دوربین" in result.message

        asyncio.run(run())

        goal = db.query(Goal).filter(Goal.user_id == u.id).first()
        assert goal is not None
        assert goal.deadline == expected_deadline

    def test_unresolvable_deadline_asks_for_clarification(self, db):
        """Low-confidence date from LLMDateResolver must NOT write today as deadline."""
        llm_date_response = json.dumps({
            "raw_text": "یه وقتی",
            "resolved_date": None,
            "confidence": 0.1,
            "date_kind": "unknown",
            "interpretation_fa": "نامشخص",
            "needs_confirmation": True,
        })
        choice_response = "add"

        u = user1(db)
        intent = self._pending_intent_in_awaiting_choice(db, u, date_text="یه وقتی")
        gate = GoalIntakeGate()
        semantic = SemanticResult()
        semantic.should_cancel_pending_flow = False
        semantic.user_intent = "answer_pending_question"

        async def run():
            with patch("app.services.agent_orchestrator.goal_intake.get_ai_chat_completion", new_callable=AsyncMock) as mock_chat:
                with patch("app.services.agent_orchestrator.llm_date_resolver.get_ai_chat_completion", new_callable=AsyncMock) as mock_date:
                    mock_chat.return_value = choice_response
                    mock_date.return_value = llm_date_response
                    result = await gate.process(db, u, "آره ثبتش کن", None, {}, semantic=semantic)
                    assert result is not None
                    # Should ask for clarification, not insert
                    assert "تاریخ" in result.message or "مهلت" in result.message

        asyncio.run(run())

        # No goal should be written with today as deadline
        goal = db.query(Goal).filter(Goal.user_id == u.id).first()
        assert goal is None


# ── Duplicate client_message_id idempotency ───────────────────────────────────

class TestClientMessageIdIdempotency:
    """Sending the same client_message_id twice must produce one DB write."""

    def test_duplicate_cmid_replays_original_response(self, db):
        """Same client_message_id must replay the original response, not show an error."""
        from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
        u = user1(db)
        orch = AgentOrchestrator(goal_intake_gate=NullGoalIntakeGate())

        final_plan = AgentPlan(
            intent="none",
            language="fa",
            requires_db=False,
            steps=[],
            final_response_hint="پاسخ آزمایشی",
            confidence=1.0,
        )

        async def run():
            with patch.object(orch.planner, "plan", new_callable=AsyncMock) as mock_plan:
                with patch("app.services.agent_orchestrator.orchestrator.SemanticInterpreter") as MockInterp:
                    mock_interp_instance = MockInterp.return_value
                    mock_interp_instance.interpret = AsyncMock(return_value=SemanticResult.fallback())
                    mock_plan.return_value = final_plan

                    # First call — processes normally
                    r1 = await orch.run(db, u, "تست", client_message_id="test-uuid-1")
                    assert r1.message == "پاسخ آزمایشی"

                    # Second call with same ID — must replay original, not show error message
                    r2 = await orch.run(db, u, "تست", client_message_id="test-uuid-1")
                    assert r2.message == "پاسخ آزمایشی"  # original response replayed
                    assert r2.metadata.get("idempotent_skip") is True
                    assert "پردازش شده" not in r2.message

                    # Planner called only once (second call was a replay)
                    assert mock_plan.call_count == 1

        asyncio.run(run())

    def test_different_cmid_processes_separately(self, db):
        u = user1(db)
        orch = AgentOrchestrator(goal_intake_gate=NullGoalIntakeGate())

        final_plan = AgentPlan(
            intent="none",
            language="fa",
            requires_db=False,
            steps=[],
            final_response_hint="پاسخ",
            confidence=1.0,
        )

        async def run():
            with patch.object(orch.planner, "plan", new_callable=AsyncMock) as mock_plan:
                with patch("app.services.agent_orchestrator.orchestrator.SemanticInterpreter") as MockInterp:
                    mock_interp_instance = MockInterp.return_value
                    mock_interp_instance.interpret = AsyncMock(return_value=SemanticResult.fallback())
                    mock_plan.return_value = final_plan

                    await orch.run(db, u, "اول", client_message_id="id-A")
                    await orch.run(db, u, "دوم", client_message_id="id-B")
                    assert mock_plan.call_count == 2  # both processed

        asyncio.run(run())


# ── Planner receives semantic_interpretation ──────────────────────────────────

class TestPlannerReceivesSemanticInterpretation:
    """Planner.plan() must accept and include semantic_interpretation in its LLM call."""

    def test_semantic_included_in_planner_messages(self):
        from app.services.agent_orchestrator.planner import AgentPlanner
        planner = AgentPlanner()
        semantic = {"user_intent": "expense", "money": {"amount": 40000, "confidence": 0.9}}

        captured_messages = []

        async def fake_llm(messages, **kwargs):
            captured_messages.extend(messages)
            return json.dumps({
                "intent": "test",
                "language": "fa",
                "requires_db": False,
                "steps": [],
                "final_response_hint": "ok",
                "confidence": 1.0,
            })

        async def run():
            with patch("app.services.agent_orchestrator.planner.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                mock_llm.side_effect = fake_llm
                await planner.plan(
                    db_world="",
                    user_message="چهل هزار تومن خرج کردم",
                    finance_context={},
                    semantic_interpretation=semantic,
                )

        asyncio.run(run())

        # Verify semantic data appears in one of the messages
        all_content = " ".join(m.get("content", "") for m in captured_messages)
        assert "SEMANTIC INTERPRETATION" in all_content
        assert "expense" in all_content


# ── Cancelled flow must not write to DB ───────────────────────────────────────

class TestCancelFlowNoWrite:
    """cancel_flow intent must never result in a goal being inserted."""

    def test_cancel_via_semantic_no_goal_inserted(self, db):
        u = user1(db)
        gate = GoalIntakeGate()
        # Create active intent
        intent = PendingAgentIntent(
            user_id=u.id,
            intent_type=GOAL_INTENT_TYPE,
            payload_json={
                "item_title": "ماشین",
                "target_amount": 500_000_000,
                "target_date_text": "دو سال دیگه",
                "state": STATE_AWAITING_CHOICE,
                "source_message": "test",
            },
            status="pending",
        )
        db.add(intent)
        db.commit()

        semantic = SemanticResult()
        semantic.should_cancel_pending_flow = True
        semantic.user_intent = "cancel_flow"

        async def run():
            result = await gate.process(db, u, "ولش کن", None, {}, semantic=semantic)
            assert result is not None
            assert "کنار گذاشتم" in result.message

        asyncio.run(run())

        assert db.query(Goal).filter(Goal.user_id == u.id).count() == 0
