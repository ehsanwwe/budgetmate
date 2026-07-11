"""End-to-end behavioral tests for the objectives in the finish-agent brief.

Covers:
  1. Zero-match delete never returns a success message (planner hint override).
  2. Partial delete is reported honestly.
  3. Chat provenance: transactions from the current chat can be deleted;
     other-chat and manual transactions survive.
  4. Cancel + delete in the same message is not treated as cancel_flow.
  5. Uncertain / future-dated income cannot be persisted as received.
  6. Conversational exclusion state persists across turns.
  7. Ambiguous singular delete does not delete anything.
  8. Explicit bulk delete removes all matching rows.
  9. Numeric consistency guard rejects a hint that over-allocates.
 10. Balance-before-allocation: finance context still exposes actual balance
     as untracked when the user has not stated it.
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    Category,
    ChatMessage,
    FinancialFact,
    FutureCommitment,
    Transaction,
    User,
)
from app.models.chat import MessageRole
from app.models.transaction import TransactionType
from app.services.agent_orchestrator.goal_intake import NullGoalIntakeGate
from app.services.agent_orchestrator.numeric_consistency import (
    check_response_consistency,
)
from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
from app.services.agent_orchestrator.semantic_interpreter import SemanticResult
from app.services.agent_orchestrator.sql_executor import SqlExecutor
from app.services.agent_orchestrator.sql_validator import SqlValidator
from app.services.agent_orchestrator.types import (
    AgentOperationType,
    AgentPlan,
    AgentPlanStep,
)
from app.services.chat_session_lifecycle import clear_chat_history_and_transient_state
from app.services.finance_context import build_finance_context
from app.services.personal_cfo.conversation_state import (
    CHAT_REASONING_FACT_TYPE,
    exclude_transactions,
    get_active_state,
    set_stated_balance,
)

_NULL_GATE = NullGoalIntakeGate()


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
            User(id=2, phone="09120000002", name="Other", language="fa"),
            Category(id=1, name="Food", icon="f", color="#111", is_default=True),
            Category(id=2, name="Transport", icon="t", color="#222", is_default=True),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def user(db, uid: int = 1) -> User:
    return db.query(User).filter(User.id == uid).first()


class SequencePlanner:
    def __init__(self, plans):
        self.plans = list(plans)
        self.calls = 0

    async def plan(self, *args, **kwargs):
        self.calls += 1
        if self.plans:
            return self.plans.pop(0)
        return AgentPlan(intent="final", final_response_hint="")


def _mk_user_msg(db, user_id: int, text: str) -> ChatMessage:
    msg = ChatMessage(user_id=user_id, role=MessageRole.user, content=text)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


# ── Objective 1: false success on zero-match ──────────────────────────────────

def test_zero_match_delete_never_returns_success_message(db):
    """Even if the planner writes 'تراکنش حذف شد', a 0-match delete overrides it."""
    plans = [
        AgentPlan(
            intent="delete_missing",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="del",
                    operation_type=AgentOperationType.delete,
                    purpose="try to delete non-existent transaction",
                    table_name="transactions",
                    sql="DELETE FROM transactions WHERE id = :id",
                    params={"id": 999_999},
                )
            ],
        ),
        # Planner-provided FALSE success sentence — composer MUST override it
        AgentPlan(intent="final", final_response_hint="تراکنش حذف شد."),
    ]
    result = asyncio.run(
        AgentOrchestrator(goal_intake_gate=_NULL_GATE, planner=SequencePlanner(plans)).run(
            db, user(db), "delete that one"
        )
    )
    # Never claim deletion succeeded
    assert "حذف شد" not in result.message or "پیدا نکردم" in result.message
    # Metadata reports 0 deleted
    assert result.metadata.get("deleted_count", 0) == 0


def test_partial_delete_reports_honestly(db):
    """Some delete steps hit rows, some miss → we do not blanket-say 'deleted'."""
    tx = Transaction(user_id=1, amount=100_000, type=TransactionType.expense, description="x", date=date.today())
    db.add(tx)
    db.commit()
    db.refresh(tx)
    tx_id = tx.id
    plans = [
        AgentPlan(
            intent="delete_multi",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="d1",
                    operation_type=AgentOperationType.delete,
                    purpose="delete existing",
                    table_name="transactions",
                    sql="DELETE FROM transactions WHERE id = :id",
                    params={"id": tx_id},
                ),
                AgentPlanStep(
                    step_id="d2",
                    operation_type=AgentOperationType.delete,
                    purpose="delete non-existent",
                    table_name="transactions",
                    sql="DELETE FROM transactions WHERE id = :id",
                    params={"id": 424_242},
                ),
            ],
        ),
        AgentPlan(intent="final", final_response_hint=""),
    ]
    result = asyncio.run(
        AgentOrchestrator(goal_intake_gate=_NULL_GATE, planner=SequencePlanner(plans)).run(
            db, user(db), "delete these"
        )
    )
    md = result.metadata
    assert md.get("partial_deletion") is True
    assert md.get("deleted_count") == 1
    assert md.get("missed_count") == 1


def test_multi_row_delete_success_reports_correct_count(db):
    ids = []
    for i in range(3):
        tx = Transaction(user_id=1, amount=100_000 + i, type=TransactionType.expense, description=str(i), date=date.today())
        db.add(tx)
        db.commit()
        db.refresh(tx)
        ids.append(tx.id)
    plans = [
        AgentPlan(
            intent="delete_multi",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="d1",
                    operation_type=AgentOperationType.delete,
                    purpose="delete all three by id list",
                    table_name="transactions",
                    sql="DELETE FROM transactions WHERE id IN (:i1, :i2, :i3)",
                    params={"i1": ids[0], "i2": ids[1], "i3": ids[2]},
                )
            ],
        ),
        AgentPlan(intent="final", final_response_hint=""),
    ]
    result = asyncio.run(
        AgentOrchestrator(goal_intake_gate=_NULL_GATE, planner=SequencePlanner(plans)).run(
            db, user(db), "delete these three"
        )
    )
    assert result.metadata.get("deleted_count") == 3


def test_planner_incorrect_success_is_overridden_by_zero_match(db):
    """Direct proof: planner says success, tool says 0 → tool wins."""
    plans = [
        AgentPlan(
            intent="delete_missing",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="d",
                    operation_type=AgentOperationType.delete,
                    purpose="mistaken delete",
                    table_name="transactions",
                    sql="DELETE FROM transactions WHERE id = :id",
                    params={"id": 999},
                )
            ],
        ),
        # Deliberately-wrong planner hint
        AgentPlan(intent="final", final_response_hint="با موفقیت حذف شد!"),
    ]
    result = asyncio.run(
        AgentOrchestrator(goal_intake_gate=_NULL_GATE, planner=SequencePlanner(plans)).run(
            db, user(db), "delete"
        )
    )
    assert "با موفقیت" not in result.message
    assert result.metadata.get("deleted_count", 0) == 0


# ── Objective 2: chat provenance ──────────────────────────────────────────────

def test_transaction_created_via_chat_has_source_message_id(db):
    msg = _mk_user_msg(db, 1, "خرید ۲۰۰ هزار")
    step = AgentPlanStep(
        step_id="i",
        operation_type=AgentOperationType.insert,
        purpose="record expense",
        table_name="transactions",
        sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
        params={"amount": 200_000, "type": "expense", "description": "coffee", "date": date.today().isoformat()},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(
        db, user(db), step, validation, "expense", source_message_id=msg.id
    )
    tx = db.query(Transaction).filter(Transaction.id == result.inserted_id).first()
    assert tx.source_message_id == msg.id


def test_current_chat_delete_scope_via_source_message_id(db):
    # Two chat conversations for user 1: msg_a is "current", msg_b was
    # created in a prior conversation. Prior conversation is simulated by
    # explicitly setting source_message_id=NULL, matching what
    # clear_chat_history_and_transient_state does.
    msg_a = _mk_user_msg(db, 1, "current chat message")
    tx_from_current = Transaction(
        user_id=1, amount=300_000, type=TransactionType.expense,
        description="in-chat", date=date.today(), source_message_id=msg_a.id,
    )
    tx_from_prior_chat = Transaction(
        user_id=1, amount=500_000, type=TransactionType.expense,
        description="prior chat (cleared)", date=date.today(),
        source_message_id=None,
    )
    tx_manual = Transaction(
        user_id=1, amount=1_000_000, type=TransactionType.expense,
        description="manual UI entry", date=date.today(),
        source_message_id=None,
    )
    db.add_all([tx_from_current, tx_from_prior_chat, tx_manual])
    db.commit()
    ids = (tx_from_current.id, tx_from_prior_chat.id, tx_manual.id)

    step = AgentPlanStep(
        step_id="d",
        operation_type=AgentOperationType.delete,
        purpose="delete everything created in this chat",
        table_name="transactions",
        sql="DELETE FROM transactions WHERE source_message_id IS NOT NULL",
        params={},
        bulk_scope=True,
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    assert validation.allowed, validation.rejected_reason
    result = SqlExecutor().execute(db, user(db), step, validation, "delete_this_chat")
    assert result.deleted_row_count == 1
    surviving_ids = {t.id for t in db.query(Transaction).filter(Transaction.user_id == 1).all()}
    assert ids[0] not in surviving_ids
    assert ids[1] in surviving_ids
    assert ids[2] in surviving_ids


def test_other_user_conversation_transactions_are_not_touched(db):
    # user2 creates a chat message + transaction; user1 asks to clear own chat.
    msg2 = _mk_user_msg(db, 2, "user 2 message")
    tx2 = Transaction(
        user_id=2, amount=999_999, type=TransactionType.expense,
        description="user 2's", date=date.today(), source_message_id=msg2.id,
    )
    db.add(tx2)
    db.commit()

    step = AgentPlanStep(
        step_id="d",
        operation_type=AgentOperationType.delete,
        purpose="delete this chat's records",
        table_name="transactions",
        sql="DELETE FROM transactions WHERE source_message_id IS NOT NULL",
        params={},
        bulk_scope=True,
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    SqlExecutor().execute(db, user(db, 1), step, validation, "delete_this_chat")

    # user 2's transaction is untouched
    assert db.query(Transaction).filter(Transaction.user_id == 2, Transaction.id == tx2.id).first() is not None


def test_chat_clear_detaches_provenance_from_prior_transactions(db):
    msg = _mk_user_msg(db, 1, "hello")
    tx = Transaction(
        user_id=1, amount=100_000, type=TransactionType.expense,
        description="in chat", date=date.today(), source_message_id=msg.id,
    )
    db.add(tx)
    db.commit()
    clear_chat_history_and_transient_state(db, 1)
    db.expire_all()
    tx_reloaded = db.query(Transaction).filter(Transaction.user_id == 1).first()
    assert tx_reloaded.source_message_id is None


# ── Objective 3: cancel + delete (semantic guidance test) ─────────────────────

def test_mixed_cancel_and_delete_can_still_delete(db):
    """When semantic result flags cancel_flow=false + bypass=true, the planner runs."""
    tx = Transaction(user_id=1, amount=100_000, type=TransactionType.expense, description="x", date=date.today())
    db.add(tx)
    db.commit()
    tx_id = tx.id
    plans = [
        AgentPlan(
            intent="delete_after_cancel_word",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="d",
                    operation_type=AgentOperationType.delete,
                    purpose="delete despite cancel language",
                    table_name="transactions",
                    sql="DELETE FROM transactions WHERE id = :id",
                    params={"id": tx_id},
                )
            ],
        ),
        AgentPlan(intent="final", final_response_hint=""),
    ]
    orch = AgentOrchestrator(goal_intake_gate=_NULL_GATE, planner=SequencePlanner(plans))
    # SemanticInterpreter is patched to return "other" (NOT cancel_flow) with
    # bypass=true, matching the prompt guidance for mixed messages.
    with patch(
        "app.services.agent_orchestrator.orchestrator.SemanticInterpreter"
    ) as SemMock:
        instance = SemMock.return_value
        semantic = SemanticResult()
        semantic.user_intent = "other"
        semantic.should_cancel_pending_flow = False
        semantic.should_bypass_goal_intake = True
        instance.interpret = AsyncMock(return_value=semantic)
        result = asyncio.run(orch.run(db, user(db), "ولش کن، این تراکنش رو پاک کن"))

    assert db.query(Transaction).filter(Transaction.id == tx_id).first() is None


# ── Objective 4: uncertain / future-dated income guard ────────────────────────

def test_executor_rejects_future_dated_income(db):
    future = (date.today() + timedelta(days=7)).isoformat()
    step = AgentPlanStep(
        step_id="i",
        operation_type=AgentOperationType.insert,
        purpose="record uncertain future income",
        table_name="transactions",
        sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
        params={
            "amount": 5_000_000,
            "type": "income",
            "description": "احتمالاً بعداً",
            "date": future,
        },
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "uncertain_income_test")
    assert result.executed is False
    assert result.error and "future-dated income" in result.error.lower()
    assert db.query(Transaction).filter(Transaction.user_id == 1, Transaction.type == TransactionType.income).count() == 0


def test_executor_accepts_received_income_today(db):
    step = AgentPlanStep(
        step_id="i",
        operation_type=AgentOperationType.insert,
        purpose="record actually received income",
        table_name="transactions",
        sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
        params={
            "amount": 5_000_000,
            "type": "income",
            "description": "کلاس خصوصی امروز",
            "date": date.today().isoformat(),
        },
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "income_test")
    assert result.executed is True


def test_future_dated_expense_still_allowed(db):
    """Future-dated expense is odd but not blocked (may be a scheduled payment log)."""
    future = (date.today() + timedelta(days=3)).isoformat()
    step = AgentPlanStep(
        step_id="i",
        operation_type=AgentOperationType.insert,
        purpose="record future-dated expense",
        table_name="transactions",
        sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
        params={
            "amount": 100_000,
            "type": "expense",
            "description": "scheduled",
            "date": future,
        },
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "future_expense_test")
    assert result.executed is True


# ── Objective 5: conversational exclusion state ───────────────────────────────

def test_exclusion_persists_across_turns_and_adjusts_totals(db):
    from app.core.jalali import current_jalali_month
    jm, jy = current_jalali_month()
    from app.models.budget import Budget as B
    db.add(B(user_id=1, month=jm, year=jy, amount=20_000_000))
    e1 = Transaction(user_id=1, amount=1_000_000, type=TransactionType.expense, description="a", date=date.today())
    e2 = Transaction(user_id=1, amount=2_000_000, type=TransactionType.expense, description="b", date=date.today())
    db.add_all([e1, e2])
    db.commit()
    e1_id = e1.id
    # exclude e1 conversationally
    exclude_transactions(db, 1, [e1_id])

    # Turn 1 finance context
    ctx1 = build_finance_context(user(db), db)
    st1 = ctx1["conversation_reasoning_state"]
    assert e1_id in st1["excluded_transaction_ids"]
    assert st1["adjusted_total_spent_this_month"] == 2_000_000
    # Raw totals unchanged
    assert ctx1["financial_availability"]["recorded_total_spent_this_month"] == 3_000_000

    # Turn 2 (new session load): exclusion survives
    ctx2 = build_finance_context(user(db), db)
    assert e1_id in ctx2["conversation_reasoning_state"]["excluded_transaction_ids"]


def test_exclusion_does_not_delete_persistent_records(db):
    e1 = Transaction(user_id=1, amount=1_000_000, type=TransactionType.expense, description="a", date=date.today())
    db.add(e1)
    db.commit()
    e1_id = e1.id
    exclude_transactions(db, 1, [e1_id])
    # Row still exists
    assert db.query(Transaction).filter(Transaction.id == e1_id).first() is not None


def test_stated_balance_survives_across_turns(db):
    set_stated_balance(db, 1, 7_000_000)
    ctx = build_finance_context(user(db), db)
    st = ctx["conversation_reasoning_state"]
    assert st["user_stated_available_balance"] == 7_000_000
    # Second load — still there
    ctx2 = build_finance_context(user(db), db)
    assert ctx2["conversation_reasoning_state"]["user_stated_available_balance"] == 7_000_000


def test_chat_clear_resets_reasoning_state(db):
    msg = _mk_user_msg(db, 1, "hi")
    _ = msg  # not deleted, just present so chat_messages table has rows
    exclude_transactions(db, 1, [42])
    set_stated_balance(db, 1, 5_000_000)
    assert get_active_state(db, 1).stated_balance == 5_000_000
    clear_chat_history_and_transient_state(db, 1)
    assert get_active_state(db, 1).stated_balance is None
    assert get_active_state(db, 1).excluded_transaction_ids == []


# ── Objective 6: ambiguity guard ──────────────────────────────────────────────

def test_filter_delete_without_bulk_scope_is_refused_when_ambiguous(db):
    # Two matching restaurant expenses; user says "delete the restaurant expense"
    a = Transaction(user_id=1, amount=500_000, type=TransactionType.expense, description="رستوران", date=date.today())
    b = Transaction(user_id=1, amount=500_000, type=TransactionType.expense, description="رستوران", date=date.today())
    db.add_all([a, b])
    db.commit()
    step = AgentPlanStep(
        step_id="d",
        operation_type=AgentOperationType.delete,
        purpose="singular delete without bulk_scope",
        table_name="transactions",
        sql="DELETE FROM transactions WHERE amount = :amount AND date = :d",
        params={"amount": 500_000, "d": date.today().isoformat()},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "ambiguous")
    # Not executed; not rejected as malicious; candidates surfaced
    assert result.executed is False
    assert result.rejected_reason == "ambiguous_delete_requires_clarification"
    assert len(result.ambiguous_candidates) == 2
    # Rows survive
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 2


def test_filter_delete_with_single_match_allowed(db):
    Transaction  # noqa — for readability
    a = Transaction(user_id=1, amount=500_000, type=TransactionType.expense, description="رستوران", date=date.today())
    db.add(a)
    db.commit()
    a_id = a.id
    step = AgentPlanStep(
        step_id="d",
        operation_type=AgentOperationType.delete,
        purpose="singular delete with single match",
        table_name="transactions",
        sql="DELETE FROM transactions WHERE amount = :amount",
        params={"amount": 500_000},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "single")
    assert result.executed is True
    assert result.deleted_row_count == 1
    assert db.query(Transaction).filter(Transaction.id == a_id).first() is None


def test_bulk_scope_true_allows_multi_row_filter_delete(db):
    a = Transaction(user_id=1, amount=500_000, type=TransactionType.expense, description="a", date=date.today())
    b = Transaction(user_id=1, amount=500_000, type=TransactionType.expense, description="b", date=date.today())
    db.add_all([a, b])
    db.commit()
    step = AgentPlanStep(
        step_id="d",
        operation_type=AgentOperationType.delete,
        purpose="explicit bulk delete",
        table_name="transactions",
        sql="DELETE FROM transactions WHERE amount = :amount",
        params={"amount": 500_000},
        bulk_scope=True,
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "bulk")
    assert result.executed is True
    assert result.deleted_row_count == 2


def test_ambiguous_candidates_do_not_leak_other_user_data(db):
    other = Transaction(user_id=2, amount=500_000, type=TransactionType.expense, description="other", date=date.today())
    a = Transaction(user_id=1, amount=500_000, type=TransactionType.expense, description="a", date=date.today())
    b = Transaction(user_id=1, amount=500_000, type=TransactionType.expense, description="b", date=date.today())
    db.add_all([other, a, b])
    db.commit()
    step = AgentPlanStep(
        step_id="d",
        operation_type=AgentOperationType.delete,
        purpose="ambiguous",
        table_name="transactions",
        sql="DELETE FROM transactions WHERE amount = :amount",
        params={"amount": 500_000},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db, 1), step, validation, "amb")
    assert result.executed is False
    for c in result.ambiguous_candidates:
        assert c.get("description") in {"a", "b"}
        assert c.get("description") != "other"


# ── Objective 7: numeric consistency ──────────────────────────────────────────

def test_consistency_check_passes_when_allocation_matches_available():
    r = check_response_consistency(
        "۷ میلیون تومان در دسترس داری. ۴ میلیون تومان پس‌انداز کن و ۳ میلیون تومان خرج کن."
    )
    assert r.ok is True


def test_consistency_check_flags_over_allocation():
    r = check_response_consistency(
        "۳ میلیون تومان باقی مانده. ۵ میلیون تومان پس‌انداز کن."
    )
    assert r.ok is False
    assert r.declared_available == 3_000_000
    assert r.total_allocated == 5_000_000


def test_composer_replaces_over_allocated_hint(db):
    plans = [
        AgentPlan(
            intent="allocate",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="s",
                    operation_type=AgentOperationType.select,
                    purpose="context",
                    table_name="transactions",
                    sql="SELECT id FROM transactions",
                    params={},
                )
            ],
        ),
        # Second iteration returns the over-allocated hint the composer must catch
        AgentPlan(
            intent="allocate",
            requires_db=False,
            final_response_hint=(
                "۳ میلیون تومان باقی مانده. ۵ میلیون تومان پس‌انداز کن."
            ),
            steps=[],
        ),
    ]
    result = asyncio.run(
        AgentOrchestrator(goal_intake_gate=_NULL_GATE, planner=SequencePlanner(plans)).run(
            db, user(db), "چطور تقسیم کنم"
        )
    )
    assert result.metadata.get("numeric_inconsistency") is True
    assert "پس‌انداز کن" not in result.message  # inconsistent allocation dropped
    assert result.metadata.get("declared_available") == 3_000_000


# ── Objective 8: balance-before-allocation surface ────────────────────────────

def test_finance_context_marks_actual_balance_untracked_by_default(db):
    ctx = build_finance_context(user(db), db)
    fa = ctx["financial_availability"]
    assert fa["actual_cash_balance_tracked"] is False
    assert fa["actual_cash_balance_amount"] is None
    st = ctx["conversation_reasoning_state"]
    assert st["user_stated_available_balance"] is None


def test_stated_balance_overrides_untracked_in_reasoning_state(db):
    set_stated_balance(db, 1, 7_000_000)
    ctx = build_finance_context(user(db), db)
    st = ctx["conversation_reasoning_state"]
    assert st["user_stated_available_balance"] == 7_000_000


# ── Delete provenance survives normal chat lifecycle ─────────────────────────

def test_provenance_survives_across_turns_until_clear(db):
    msg1 = _mk_user_msg(db, 1, "turn 1")
    step = AgentPlanStep(
        step_id="i",
        operation_type=AgentOperationType.insert,
        purpose="turn 1 expense",
        table_name="transactions",
        sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
        params={"amount": 100_000, "type": "expense", "description": "coffee", "date": date.today().isoformat()},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    SqlExecutor().execute(db, user(db), step, validation, "e", source_message_id=msg1.id)
    # Later turn — provenance still present
    _ = _mk_user_msg(db, 1, "turn 2")
    tx = db.query(Transaction).filter(Transaction.user_id == 1).first()
    assert tx.source_message_id == msg1.id
    # Clear chat — provenance drops
    clear_chat_history_and_transient_state(db, 1)
    db.expire_all()
    tx2 = db.query(Transaction).filter(Transaction.user_id == 1).first()
    assert tx2.source_message_id is None
