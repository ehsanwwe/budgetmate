"""Tests for the new deletion tool and balance/liquidity reasoning surfaces.

These tests verify observable behavior at the tool/policy/context layer.
They do NOT enforce keyword routing, exact response strings, or specific
LLM prompt wording — the LLM orchestration layer must remain free.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Budget, Category, FutureCommitment, Transaction, User
from app.models.transaction import TransactionType
from app.services.agent_orchestrator.db_world import build_db_world
from app.services.agent_orchestrator.date_utils import local_today
from app.services.agent_orchestrator.goal_intake import NullGoalIntakeGate
from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
from app.services.agent_orchestrator.sql_executor import SqlExecutor
from app.services.agent_orchestrator.sql_validator import SqlValidator
from app.services.agent_orchestrator.types import (
    AgentOperationType,
    AgentPlan,
    AgentPlanStep,
    SourceScope,
)
from app.services.finance_context import build_finance_context

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


def user(db) -> User:
    return db.query(User).filter(User.id == 1).first()


class SequencePlanner:
    def __init__(self, plans):
        self.plans = list(plans)
        self.calls = 0

    async def plan(self, *args, **kwargs):
        self.calls += 1
        if self.plans:
            return self.plans.pop(0)
        return AgentPlan(intent="final", final_response_hint="")


# ── DB World exposure ────────────────────────────────────────────────────────

def test_db_world_exposes_delete_on_transactions(db):
    world = build_db_world(db.bind)
    tables = {t.table_name: t for t in world.tables}
    tx_ops = {op.value for op in tables["transactions"].allowed_operations}
    assert "delete" in tx_ops
    # And it must still support SELECT + INSERT
    assert {"select", "insert", "delete"}.issubset(tx_ops)


def test_db_world_instructions_document_delete_tool(db):
    world = build_db_world(db.bind)
    combined = " ".join(world.instructions).lower()
    assert "delete" in combined
    # Must remind planner to SELECT before delete for fuzzy criteria
    assert "select" in combined


# ── Validator: safe DELETE syntax ────────────────────────────────────────────

def test_validator_accepts_delete_by_id():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "transactions",
        "DELETE FROM transactions WHERE id = :id",
        {"id": 7},
    )
    assert r.allowed
    assert r.operation_type == AgentOperationType.delete


def test_validator_accepts_delete_by_id_list():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "transactions",
        "DELETE FROM transactions WHERE id IN (:i1, :i2, :i3)",
        {"i1": 1, "i2": 2, "i3": 3},
    )
    assert r.allowed


def test_validator_accepts_delete_by_date_and_type():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "transactions",
        "DELETE FROM transactions WHERE type = :t AND date = :d",
        {"t": "expense", "d": "2026-07-11"},
    )
    assert r.allowed


def test_validator_rejects_delete_without_where():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "transactions",
        "DELETE FROM transactions",
        {},
    )
    assert not r.allowed


def test_validator_rejects_delete_with_or():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "transactions",
        "DELETE FROM transactions WHERE id = :i OR id = :j",
        {"i": 1, "j": 2},
    )
    assert not r.allowed


def test_validator_rejects_delete_with_user_id_filter():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "transactions",
        "DELETE FROM transactions WHERE user_id = :u",
        {"u": 1},
    )
    assert not r.allowed


def test_validator_rejects_delete_with_subquery():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "transactions",
        "DELETE FROM transactions WHERE id IN (SELECT id FROM transactions)",
        {},
    )
    assert not r.allowed


def test_validator_rejects_delete_on_non_delete_table():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "goals",
        "DELETE FROM goals WHERE id = :id",
        {"id": 1},
    )
    # goals is not delete-enabled in the policy (archived via UPDATE status='archived')
    assert not r.allowed


# ── Executor: deletion is user-scoped ────────────────────────────────────────

def _insert_tx(db, user_id, amount, type_=TransactionType.expense, description=None):
    tx = Transaction(
        user_id=user_id,
        amount=amount,
        type=type_,
        description=description or "test",
        date=local_today(),
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def test_executor_deletes_own_transaction_by_id(db):
    tx = _insert_tx(db, 1, 300_000)
    tx_id = tx.id
    step = AgentPlanStep(
        step_id="d1",
        operation_type=AgentOperationType.delete,
        purpose="delete transaction",
        table_name="transactions",
        sql="DELETE FROM transactions WHERE id = :id",
        params={"id": tx_id},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "delete_test")
    assert result.executed
    assert result.deleted_row_count == 1
    assert result.deleted_ids == [tx_id]
    assert db.query(Transaction).filter(Transaction.id == tx_id).first() is None


def test_executor_cannot_delete_other_users_transaction(db):
    tx = _insert_tx(db, 2, 300_000)  # belongs to user 2
    tx_id = tx.id
    step = AgentPlanStep(
        step_id="d1",
        operation_type=AgentOperationType.delete,
        purpose="attempt cross-user delete",
        table_name="transactions",
        sql="DELETE FROM transactions WHERE id = :id",
        params={"id": tx_id},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "delete_test")
    assert result.executed
    assert result.deleted_row_count == 0
    # Row still exists in DB
    assert db.query(Transaction).filter(Transaction.id == tx_id).first() is not None


def test_executor_no_match_returns_empty_and_does_not_error(db):
    step = AgentPlanStep(
        step_id="d1",
        operation_type=AgentOperationType.delete,
        purpose="delete missing transaction",
        table_name="transactions",
        sql="DELETE FROM transactions WHERE id = :id",
        params={"id": 999_999},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "delete_test")
    assert result.executed
    assert result.deleted_row_count == 0
    assert result.error is None


def test_executor_deletes_multiple_by_id_list(db):
    a = _insert_tx(db, 1, 100_000)
    b = _insert_tx(db, 1, 200_000)
    c = _insert_tx(db, 1, 500_000)
    a_id, b_id, c_id = a.id, b.id, c.id
    step = AgentPlanStep(
        step_id="d1",
        operation_type=AgentOperationType.delete,
        purpose="bulk delete by id list",
        table_name="transactions",
        sql="DELETE FROM transactions WHERE id IN (:i1, :i2)",
        params={"i1": a_id, "i2": c_id},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "delete_test")
    assert result.executed
    assert set(result.deleted_ids) == {a_id, c_id}
    surviving = db.query(Transaction).filter(Transaction.user_id == 1).all()
    assert {t.id for t in surviving} == {b_id}


def test_executor_deletes_all_expenses_today_by_filter(db):
    e1 = _insert_tx(db, 1, 100_000, TransactionType.expense, "food today")
    e2 = _insert_tx(db, 1, 500_000, TransactionType.expense, "snap today")
    inc = _insert_tx(db, 1, 5_000_000, TransactionType.income, "class income")
    e1_id, e2_id, inc_id = e1.id, e2.id, inc.id
    step = AgentPlanStep(
        step_id="d1",
        operation_type=AgentOperationType.delete,
        purpose="delete today's expenses",
        table_name="transactions",
        sql="DELETE FROM transactions WHERE type = :t AND date = :d",
        params={"t": "expense", "d": local_today().isoformat()},
        bulk_scope=True,  # explicit bulk delete; ambiguity guard is bypassed
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "delete_test")
    assert result.executed
    assert set(result.deleted_ids) == {e1_id, e2_id}
    # income survives
    assert db.query(Transaction).filter(Transaction.id == inc_id).first() is not None


# ── Orchestrator: end-to-end delete plan ─────────────────────────────────────

def test_orchestrator_executes_delete_plan(db):
    tx = _insert_tx(db, 1, 1_000_000, TransactionType.expense, "restaurant")
    tx_id = tx.id
    plans = [
        AgentPlan(
            intent="delete_last_transaction",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="find",
                    operation_type=AgentOperationType.select,
                    purpose="find most recent transaction",
                    table_name="transactions",
                    sql="SELECT id, amount FROM transactions ORDER BY id DESC LIMIT 1",
                    params={},
                )
            ],
        ),
        AgentPlan(
            intent="delete_last_transaction",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="del",
                    operation_type=AgentOperationType.delete,
                    purpose="delete matched transaction by id",
                    table_name="transactions",
                    sql="DELETE FROM transactions WHERE id = :id",
                    params={"id": tx_id},
                )
            ],
        ),
        AgentPlan(intent="final", final_response_hint="تراکنش حذف شد."),
    ]
    result = asyncio.run(
        AgentOrchestrator(goal_intake_gate=_NULL_GATE, planner=SequencePlanner(plans)).run(
            db, user(db), "تراکنش آخرم را حذف کن"
        )
    )
    # Row is gone
    assert db.query(Transaction).filter(Transaction.id == tx_id).first() is None


def test_orchestrator_delete_no_match_produces_honest_answer(db):
    plans = [
        AgentPlan(
            intent="delete_missing",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="del",
                    operation_type=AgentOperationType.delete,
                    purpose="try to delete nonexistent",
                    table_name="transactions",
                    sql="DELETE FROM transactions WHERE id = :id",
                    params={"id": 42_000},
                )
            ],
        ),
        AgentPlan(intent="final", final_response_hint=""),  # empty hint → composer fallback
    ]
    result = asyncio.run(
        AgentOrchestrator(goal_intake_gate=_NULL_GATE, planner=SequencePlanner(plans)).run(
            db, user(db), "the receipt from earlier — delete it"
        )
    )
    # Composer fallback string comes from i18n composer.delete_no_match
    assert "پیدا" in result.message or "پیدا نکردم" in result.message or "no matching" in result.message.lower()


def test_orchestrator_blocks_delete_from_history_scope(db):
    tx = _insert_tx(db, 1, 300_000)
    tx_id = tx.id
    plans = [
        AgentPlan(
            intent="delete_from_history",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="del",
                    operation_type=AgentOperationType.delete,
                    purpose="delete inferred from prior history",
                    table_name="transactions",
                    sql="DELETE FROM transactions WHERE id = :id",
                    params={"id": tx_id},
                    source_scope=SourceScope.history_context,
                )
            ],
        ),
        AgentPlan(intent="final", final_response_hint=""),
    ]
    asyncio.run(
        AgentOrchestrator(goal_intake_gate=_NULL_GATE, planner=SequencePlanner(plans)).run(
            db, user(db), "hello"
        )
    )
    # History-scoped writes (delete included) must be rejected → row survives
    assert db.query(Transaction).filter(Transaction.id == tx_id).first() is not None


# ── Finance context: balance vs budget distinction ───────────────────────────

def test_finance_context_marks_actual_cash_balance_untracked(db):
    ctx = build_finance_context(user(db), db)
    fa = ctx["financial_availability"]
    assert fa["actual_cash_balance_tracked"] is False
    assert fa["actual_cash_balance_amount"] is None
    assert "actual_cash_balance_note" in fa


def test_finance_context_uses_recorded_prefix_for_flow(db):
    _insert_tx(db, 1, 300_000, TransactionType.expense, "coffee")
    _insert_tx(db, 1, 5_000_000, TransactionType.income, "class")
    ctx = build_finance_context(user(db), db)
    fa = ctx["financial_availability"]
    assert fa["recorded_total_spent_this_month"] >= 300_000
    assert fa["recorded_total_income_this_month"] >= 5_000_000
    assert fa["recorded_net_flow_this_month"] == (
        fa["recorded_total_income_this_month"] - fa["recorded_total_spent_this_month"]
    )
    # Budget-remaining must NOT be presented as an actual cash balance value
    assert fa["apparent_remaining_budget"] != fa["actual_cash_balance_amount"]


def test_finance_context_budget_remaining_not_confused_with_balance(db):
    from app.core.jalali import current_jalali_month
    jm, jy = current_jalali_month()
    db.add(Budget(user_id=1, month=jm, year=jy, amount=8_500_000))
    db.commit()
    ctx = build_finance_context(user(db), db)
    fa = ctx["financial_availability"]
    # Even when budget is defined and no spending has occurred, the balance
    # remains untracked — remaining budget is a budget concept, not liquidity.
    assert fa["apparent_remaining_budget"] == 8_500_000
    assert fa["actual_cash_balance_tracked"] is False
    assert fa["actual_cash_balance_amount"] is None


# ── Validator: DELETE not treated as clearly malicious ───────────────────────

def test_delete_wrapped_reason_is_not_clearly_malicious():
    """Rejected delete with WHERE issue is repairable, not clearly malicious."""
    from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
    from app.services.agent_orchestrator.types import AgentExecutionResult

    orch = AgentOrchestrator()
    r = AgentExecutionResult(
        step_id="x",
        operation_type=AgentOperationType.delete,
        allowed=False,
        executed=False,
        rejected_reason="DELETE requires a WHERE clause",
    )
    assert orch._is_clearly_malicious(r) is False


def test_drop_is_still_clearly_malicious():
    from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
    from app.services.agent_orchestrator.types import AgentExecutionResult

    orch = AgentOrchestrator()
    r = AgentExecutionResult(
        step_id="x",
        operation_type=AgentOperationType.select,
        allowed=False,
        executed=False,
        rejected_reason="destructive or administrative SQL is not allowed",
    )
    assert orch._is_clearly_malicious(r) is True
