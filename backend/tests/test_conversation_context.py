"""Tests proving orchestration uses conversation context, not phrase schemas.

Tests verify:
1. Planner receives the full conversation history (not just last 8 messages).
2. Early financially relevant messages (expense lists) are included in planner context.
3. Semantic interpreter receives extended history.
4. Same text with a new client_message_id is processed normally.
5. Same client_message_id retry replays the original response.
6. Long conversations preserve financial facts in the history block.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Category, User
from app.services.agent_orchestrator.conversation_context import build_history_context
from app.services.agent_orchestrator.goal_intake import NullGoalIntakeGate
from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
from app.services.agent_orchestrator.planner import AgentPlanner
from app.services.agent_orchestrator.semantic_interpreter import SemanticInterpreter, SemanticResult
from app.services.agent_orchestrator.types import AgentPlan


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
        Category(id=1, name="Food", icon="f", color="#111", is_default=True),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()


def user1(db) -> User:
    return db.query(User).filter(User.id == 1).first()


def _ok_plan_json(hint: str = "ok") -> str:
    return json.dumps({
        "intent": "test",
        "language": "fa",
        "requires_db": False,
        "steps": [],
        "final_response_hint": hint,
        "confidence": 1.0,
    })


# ── build_history_context unit tests ─────────────────────────────────────────

class TestBuildHistoryContext:
    """build_history_context must split history into older + recent sections."""

    def _make_history(self, n: int) -> list[dict]:
        history = []
        for i in range(n):
            role = "user" if i % 2 == 0 else "assistant"
            history.append({"role": role, "content": f"Message {i}"})
        return history

    def test_short_history_goes_entirely_into_recent(self):
        history = self._make_history(6)
        result = build_history_context(history, recent_count=12)
        assert "RECENT EXCHANGE" in result
        assert "EARLIER CONVERSATION" not in result
        for i in range(6):
            assert f"Message {i}" in result

    def test_long_history_splits_into_older_and_recent(self):
        history = self._make_history(20)
        result = build_history_context(history, recent_count=12)
        assert "EARLIER CONVERSATION" in result
        assert "RECENT EXCHANGE" in result
        # Message 0 must appear in the older section
        assert "Message 0" in result
        # Message 19 must appear in the recent section
        assert "Message 19" in result

    def test_empty_history_returns_no_prior_context(self):
        assert "no prior context" in build_history_context([])

    def test_early_expense_message_preserved_in_older_section(self):
        history = [
            {"role": "user", "content": "باشگاه ۲۰ ملیون کلاس ۱۰ ملیون رفت‌وآمد ۱۰ ملیون"},
            {"role": "assistant", "content": "متوجه شدم، در نظر می‌گیرم."},
        ]
        # Pad to push the expense message into the 'older' section
        for i in range(14):
            history.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"Pad {i}"})
        result = build_history_context(history, recent_count=12)
        assert "EARLIER CONVERSATION" in result
        assert "باشگاه ۲۰ ملیون" in result

    def test_per_message_truncation_respected(self):
        history = [{"role": "user", "content": "x" * 2000}]
        result = build_history_context(history, recent_count=12, max_chars_recent=800)
        # Should be truncated — max 800 chars for recent message
        # Content after label "[USER]: " + 800 chars + newlines
        assert "x" * 801 not in result


# ── Planner receives full history ─────────────────────────────────────────────

class TestPlannerReceivesFullHistory:
    """AgentPlanner must include all conversation history, not just last 8 messages."""

    def test_planner_includes_early_expense_message(self):
        """Expense list from message 0 must appear in planner LLM call context."""
        expense_msg = "باشگاه ۲۰ ملیون کلاسم ۱۰ ملیون رفت‌وآمد ۱۰ ملیون خوراکی ۱۰ ملیون"

        history = [{"role": "user", "content": expense_msg}]
        for i in range(15):
            history.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"subsequent message {i}",
            })

        captured: list[list[dict]] = []

        async def fake_llm(messages, **kwargs):
            captured.append(list(messages))
            return _ok_plan_json()

        async def run():
            with patch("app.services.agent_orchestrator.planner.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                mock_llm.side_effect = fake_llm
                await AgentPlanner().plan(
                    db_world="",
                    user_message="با اون هزینه‌های بالا که گفتم حساب کن",
                    finance_context={},
                    history=history,
                )

        asyncio.run(run())

        assert captured, "LLM was not called"
        all_content = " ".join(m.get("content", "") for m in captured[0])
        assert expense_msg in all_content, "Early expense message must be in planner context"

    def test_planner_history_block_has_reference_resolution_instruction(self):
        """History block must include instruction to resolve 'همون هزینه‌های بالا' type references."""
        history = [{"role": "user", "content": "some context"}]

        captured: list[list[dict]] = []

        async def fake_llm(messages, **kwargs):
            captured.append(list(messages))
            return _ok_plan_json()

        async def run():
            with patch("app.services.agent_orchestrator.planner.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                mock_llm.side_effect = fake_llm
                await AgentPlanner().plan("", "test", {}, history=history)

        asyncio.run(run())

        all_content = " ".join(m.get("content", "") for m in captured[0])
        assert "CONVERSATION HISTORY" in all_content
        assert "resolve" in all_content.lower() or "قبلاً گفتم" in all_content

    def test_planner_receives_more_than_8_messages(self):
        """Regression: with 12 messages, all 12 must reach the planner (not just 8)."""
        history = [{"role": "user", "content": f"msg-{i}"} for i in range(12)]

        captured: list[list[dict]] = []

        async def fake_llm(messages, **kwargs):
            captured.append(list(messages))
            return _ok_plan_json()

        async def run():
            with patch("app.services.agent_orchestrator.planner.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                mock_llm.side_effect = fake_llm
                await AgentPlanner().plan("", "followup", {}, history=history)

        asyncio.run(run())

        all_content = " ".join(m.get("content", "") for m in captured[0])
        # msg-0 through msg-11 must all be present (previously only msg-4..msg-11 were passed)
        for i in range(12):
            assert f"msg-{i}" in all_content, f"msg-{i} missing from planner context"


# ── Semantic interpreter receives extended history ────────────────────────────

class TestSemanticInterpreterExtendedHistory:
    """SemanticInterpreter must receive more than 6 messages (up to 15)."""

    def test_semantic_receives_up_to_15_messages(self):
        """With 12 messages in history, interpreter must see all 12."""
        history = [
            {"role": "user", "content": f"history-item-{i}"}
            for i in range(12)
        ]

        captured_user_content: list[str] = []

        async def fake_llm(messages, **kwargs):
            for m in messages:
                if m.get("role") == "user":
                    captured_user_content.append(m.get("content", ""))
            return json.dumps({
                "language": "fa", "user_intent": "other", "is_question": False,
                "should_continue_pending_flow": False, "should_cancel_pending_flow": False,
                "should_bypass_goal_intake": False, "referenced_entities": {},
                "money": {}, "date": {}, "action": {}, "final_behavior": {},
            })

        async def run():
            with patch("app.services.agent_orchestrator.semantic_interpreter.get_ai_chat_completion", new_callable=AsyncMock) as mock_llm:
                mock_llm.side_effect = fake_llm
                await SemanticInterpreter().interpret(
                    user_message="با اون هزینه‌های بالا حساب کن",
                    history=history,
                    pending_intent_payload=None,
                    finance_context={},
                )

        asyncio.run(run())

        assert captured_user_content, "SemanticInterpreter made no LLM call"
        full = " ".join(captured_user_content)
        # All 12 history items must be in the user message
        for i in range(12):
            assert f"history-item-{i}" in full, f"history-item-{i} missing from semantic interpreter context"


# ── Idempotency: replay vs new message ───────────────────────────────────────

class TestIdempotencyReplayBehavior:
    """client_message_id idempotency must replay original response, not return error."""

    def test_same_cmid_replays_original_response(self, db):
        """Test 4: retry same client_message_id → replay original response, no writes."""
        u = user1(db)
        orch = AgentOrchestrator(goal_intake_gate=NullGoalIntakeGate())

        plan = AgentPlan(
            intent="test", language="fa", requires_db=False, steps=[],
            final_response_hint="هزینه‌ها ثبت شدند", confidence=1.0,
        )

        async def run():
            with patch.object(orch.planner, "plan", new_callable=AsyncMock) as mock_plan:
                with patch("app.services.agent_orchestrator.orchestrator.SemanticInterpreter") as MockSem:
                    MockSem.return_value.interpret = AsyncMock(return_value=SemanticResult.fallback())
                    mock_plan.return_value = plan

                    r1 = await orch.run(db, u, "سلام", client_message_id="cmid-retry-test")
                    assert r1.message == "هزینه‌ها ثبت شدند"

                    r2 = await orch.run(db, u, "سلام", client_message_id="cmid-retry-test")
                    # Must replay the ORIGINAL response, not show "already processed"
                    assert r2.message == "هزینه‌ها ثبت شدند"
                    assert r2.metadata.get("idempotent_skip") is True
                    assert "پردازش شده" not in r2.message
                    assert "این درخواست" not in r2.message

                    # Planner called only once — second was a replay
                    assert mock_plan.call_count == 1

        asyncio.run(run())

    def test_new_cmid_same_text_processes_normally(self, db):
        """Test 3: same message text with a NEW client_message_id must be processed fresh."""
        u = user1(db)
        orch = AgentOrchestrator(goal_intake_gate=NullGoalIntakeGate())

        call_count = 0

        async def counting_plan(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return AgentPlan(
                intent="test", language="fa", requires_db=False, steps=[],
                final_response_hint=f"پاسخ {call_count}", confidence=1.0,
            )

        async def run():
            with patch.object(orch.planner, "plan", side_effect=counting_plan):
                with patch("app.services.agent_orchestrator.orchestrator.SemanticInterpreter") as MockSem:
                    MockSem.return_value.interpret = AsyncMock(return_value=SemanticResult.fallback())

                    r1 = await orch.run(db, u, "سلام", client_message_id="cmid-A")
                    r2 = await orch.run(db, u, "سلام", client_message_id="cmid-B")  # different cmid

                    # Both must be processed normally
                    assert r1.metadata.get("idempotent_skip") is not True
                    assert r2.metadata.get("idempotent_skip") is not True
                    assert call_count == 2  # planner called twice

        asyncio.run(run())

    def test_no_cmid_always_processes(self, db):
        """Without client_message_id, every call is processed fresh."""
        u = user1(db)
        orch = AgentOrchestrator(goal_intake_gate=NullGoalIntakeGate())

        call_count = 0

        async def counting_plan(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return AgentPlan(
                intent="test", language="fa", requires_db=False, steps=[],
                final_response_hint="پاسخ", confidence=1.0,
            )

        async def run():
            with patch.object(orch.planner, "plan", side_effect=counting_plan):
                with patch("app.services.agent_orchestrator.orchestrator.SemanticInterpreter") as MockSem:
                    MockSem.return_value.interpret = AsyncMock(return_value=SemanticResult.fallback())
                    await orch.run(db, u, "تست")
                    await orch.run(db, u, "تست")
                    assert call_count == 2

        asyncio.run(run())


# ── Conversation context resolves references (orchestration integration) ──────

class TestConversationContextOrchestration:
    """The orchestrator must pass full history so the LLM can resolve context references."""

    def test_orchestrator_passes_full_history_to_planner(self, db):
        """Test 1: expense list from early message must reach the planner."""
        u = user1(db)
        orch = AgentOrchestrator(goal_intake_gate=NullGoalIntakeGate())

        expense_message = "باشگاه ۲۰ ملیون کلاسم ۱۰ ملیون رفت‌وآمد ۱۰ ملیون"
        history = [{"role": "user", "content": expense_message}]
        for i in range(10):
            history.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"})

        planner_history_received: list[list[dict]] = []

        async def recording_plan(db_world, user_msg, finance_ctx, history=None, **kw):
            planner_history_received.append(history or [])
            return AgentPlan(
                intent="test", language="fa", requires_db=False, steps=[],
                final_response_hint="محاسبه شد", confidence=1.0,
            )

        async def run():
            with patch.object(orch.planner, "plan", side_effect=recording_plan):
                with patch("app.services.agent_orchestrator.orchestrator.SemanticInterpreter") as MockSem:
                    MockSem.return_value.interpret = AsyncMock(return_value=SemanticResult.fallback())
                    await orch.run(
                        db, u,
                        "با اون هزینه‌های بالا که گفتم حساب کن",
                        history=history,
                    )

        asyncio.run(run())

        assert planner_history_received, "Planner was not called"
        passed_history = planner_history_received[0]
        # The full history must be passed — including the early expense message
        contents = [m.get("content", "") for m in passed_history]
        assert any(expense_message in c for c in contents), (
            "Early expense message not passed to planner — references will fail"
        )

    def test_orchestrator_passes_all_history_messages_not_truncated(self, db):
        """Test 5: with 20 messages, all 20 must be passed to planner."""
        u = user1(db)
        orch = AgentOrchestrator(goal_intake_gate=NullGoalIntakeGate())

        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"}
            for i in range(20)
        ]

        planner_calls: list[list[dict]] = []

        async def recording_plan(db_world, user_msg, finance_ctx, history=None, **kw):
            planner_calls.append(history or [])
            return AgentPlan(
                intent="test", language="fa", requires_db=False, steps=[],
                final_response_hint="ok", confidence=1.0,
            )

        async def run():
            with patch.object(orch.planner, "plan", side_effect=recording_plan):
                with patch("app.services.agent_orchestrator.orchestrator.SemanticInterpreter") as MockSem:
                    MockSem.return_value.interpret = AsyncMock(return_value=SemanticResult.fallback())
                    await orch.run(db, u, "followup", history=history)

        asyncio.run(run())

        passed_history = planner_calls[0]
        assert len(passed_history) == 20, (
            f"Expected 20 history messages, got {len(passed_history)}"
        )
