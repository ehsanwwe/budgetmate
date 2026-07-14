"""Tests for chat-surface deletion policy and balance/liquidity reasoning.

Transaction DELETE via LLM chat has been removed — the LLM cannot plan or
execute a DELETE against the transactions table. The manual UI still
deletes transactions through the REST endpoint, and the future_commitments
table still supports LLM-driven DELETE. This file exercises those
contracts at the policy/validator/executor/orchestrator layer without
enforcing keyword routing or specific LLM wording.
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

def test_db_world_hides_delete_on_transactions(db):
    world = build_db_world(db.bind)
    tables = {t.table_name: t for t in world.tables}
    tx_ops = {op.value for op in tables["transactions"].allowed_operations}
    # DELETE is intentionally not exposed for transactions — the LLM must
    # answer deletion requests by directing the user to the transaction
    # management menu.
    assert "delete" not in tx_ops
    # SELECT and INSERT remain
    assert {"select", "insert"}.issubset(tx_ops)


def test_db_world_still_exposes_delete_on_future_commitments(db):
    world = build_db_world(db.bind)
    tables = {t.table_name: t for t in world.tables}
    fc_ops = {op.value for op in tables["future_commitments"].allowed_operations}
    assert "delete" in fc_ops


def test_db_world_instructions_document_transaction_delete_disabled(db):
    world = build_db_world(db.bind)
    combined = " ".join(world.instructions).lower()
    assert "transaction" in combined
    # Must contain guidance that transaction deletion is not available
    # in chat and users are pointed to a management surface.
    assert "management" in combined or "menu" in combined or "منو" in " ".join(world.instructions)


# ── Validator: DELETE on transactions is rejected ─────────────────────────────

def test_validator_rejects_delete_on_transactions_by_id():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "transactions",
        "DELETE FROM transactions WHERE id = :id",
        {"id": 7},
    )
    assert not r.allowed


def test_validator_rejects_delete_on_transactions_by_id_list():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "transactions",
        "DELETE FROM transactions WHERE id IN (:i1, :i2, :i3)",
        {"i1": 1, "i2": 2, "i3": 3},
    )
    assert not r.allowed


def test_validator_rejects_delete_on_transactions_by_filter():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "transactions",
        "DELETE FROM transactions WHERE type = :t AND date = :d",
        {"t": "expense", "d": "2026-07-11"},
    )
    assert not r.allowed


def test_validator_still_accepts_delete_on_future_commitments_by_id():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "future_commitments",
        "DELETE FROM future_commitments WHERE id = :id",
        {"id": 5},
    )
    assert r.allowed


def test_validator_rejects_delete_without_where():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "future_commitments",
        "DELETE FROM future_commitments",
        {},
    )
    assert not r.allowed


def test_validator_rejects_delete_with_or():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "future_commitments",
        "DELETE FROM future_commitments WHERE id = :i OR id = :j",
        {"i": 1, "j": 2},
    )
    assert not r.allowed


def test_validator_rejects_delete_with_user_id_filter():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "future_commitments",
        "DELETE FROM future_commitments WHERE user_id = :u",
        {"u": 1},
    )
    assert not r.allowed


def test_validator_rejects_delete_with_subquery():
    v = SqlValidator()
    r = v.validate(
        AgentOperationType.delete,
        "future_commitments",
        "DELETE FROM future_commitments WHERE id IN (SELECT id FROM future_commitments)",
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
    assert not r.allowed


# ── Executor: chat DELETE cannot remove a transaction ─────────────────────────

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


def test_executor_blocks_llm_delete_of_transaction(db):
    tx = _insert_tx(db, 1, 300_000)
    tx_id = tx.id
    step = AgentPlanStep(
        step_id="d1",
        operation_type=AgentOperationType.delete,
        purpose="delete transaction (should be rejected)",
        table_name="transactions",
        sql="DELETE FROM transactions WHERE id = :id",
        params={"id": tx_id},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "delete_test")
    assert not result.allowed
    # Row still exists — chat DELETE is a no-op for transactions.
    assert db.query(Transaction).filter(Transaction.id == tx_id).first() is not None


def test_executor_still_deletes_future_commitment_by_id(db):
    fc = FutureCommitment(
        user_id=1,
        title="chek 5m",
        amount=5_000_000,
        due_month="next-month",
    )
    db.add(fc)
    db.commit()
    db.refresh(fc)
    fc_id = fc.id
    step = AgentPlanStep(
        step_id="d1",
        operation_type=AgentOperationType.delete,
        purpose="delete commitment",
        table_name="future_commitments",
        sql="DELETE FROM future_commitments WHERE id = :id",
        params={"id": fc_id},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "delete_test")
    assert result.executed
    assert result.deleted_row_count == 1
    assert db.query(FutureCommitment).filter(FutureCommitment.id == fc_id).first() is None


def test_executor_cannot_delete_other_users_future_commitment(db):
    fc = FutureCommitment(
        user_id=2,
        title="chek foreign",
        amount=1_000_000,
    )
    db.add(fc)
    db.commit()
    db.refresh(fc)
    fc_id = fc.id
    step = AgentPlanStep(
        step_id="d1",
        operation_type=AgentOperationType.delete,
        purpose="attempt cross-user delete",
        table_name="future_commitments",
        sql="DELETE FROM future_commitments WHERE id = :id",
        params={"id": fc_id},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "delete_test")
    assert result.executed
    assert result.deleted_row_count == 0
    assert db.query(FutureCommitment).filter(FutureCommitment.id == fc_id).first() is not None


def test_executor_no_match_returns_empty_and_does_not_error(db):
    step = AgentPlanStep(
        step_id="d1",
        operation_type=AgentOperationType.delete,
        purpose="delete missing commitment",
        table_name="future_commitments",
        sql="DELETE FROM future_commitments WHERE id = :id",
        params={"id": 999_999},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "delete_test")
    assert result.executed
    assert result.deleted_row_count == 0
    assert result.error is None


# ── Orchestrator: end-to-end delete plan for transactions is a no-op ──────────

def test_orchestrator_transaction_delete_plan_does_not_delete(db):
    """Even if the planner returns a DELETE step for transactions, the
    validator rejects it and the row survives."""
    tx = _insert_tx(db, 1, 1_000_000, TransactionType.expense, "restaurant")
    tx_id = tx.id
    plans = [
        AgentPlan(
            intent="attempt_transaction_delete",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="del",
                    operation_type=AgentOperationType.delete,
                    purpose="attempt to delete the transaction",
                    table_name="transactions",
                    sql="DELETE FROM transactions WHERE id = :id",
                    params={"id": tx_id},
                )
            ],
        ),
        AgentPlan(intent="final", final_response_hint="از منوی مدیریت تراکنش‌ها حذف کن."),
    ]
    asyncio.run(
        AgentOrchestrator(goal_intake_gate=_NULL_GATE, planner=SequencePlanner(plans)).run(
            db, user(db), "تراکنش آخرم را حذف کن"
        )
    )
    # Row is still present — LLM DELETE against transactions is a no-op.
    assert db.query(Transaction).filter(Transaction.id == tx_id).first() is not None


def test_orchestrator_future_commitment_delete_still_works(db):
    fc = FutureCommitment(user_id=1, title="chek 5m", amount=5_000_000)
    db.add(fc)
    db.commit()
    db.refresh(fc)
    fc_id = fc.id
    plans = [
        AgentPlan(
            intent="delete_future_commitment",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="del",
                    operation_type=AgentOperationType.delete,
                    purpose="delete matched commitment by id",
                    table_name="future_commitments",
                    sql="DELETE FROM future_commitments WHERE id = :id",
                    params={"id": fc_id},
                )
            ],
        ),
        AgentPlan(intent="final", final_response_hint="تعهد حذف شد."),
    ]
    asyncio.run(
        AgentOrchestrator(goal_intake_gate=_NULL_GATE, planner=SequencePlanner(plans)).run(
            db, user(db), "این چک را حذف کن"
        )
    )
    assert db.query(FutureCommitment).filter(FutureCommitment.id == fc_id).first() is None


def test_orchestrator_blocks_delete_from_history_scope(db):
    fc = FutureCommitment(user_id=1, title="chek from history", amount=3_000_000)
    db.add(fc)
    db.commit()
    db.refresh(fc)
    fc_id = fc.id
    plans = [
        AgentPlan(
            intent="delete_from_history",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="del",
                    operation_type=AgentOperationType.delete,
                    purpose="delete inferred from prior history",
                    table_name="future_commitments",
                    sql="DELETE FROM future_commitments WHERE id = :id",
                    params={"id": fc_id},
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
    assert db.query(FutureCommitment).filter(FutureCommitment.id == fc_id).first() is not None


# ── Finance context: balance vs budget distinction (unchanged) ────────────────

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
    assert fa["apparent_remaining_budget"] != fa["actual_cash_balance_amount"]


def test_finance_context_budget_remaining_not_confused_with_balance(db):
    from app.core.jalali import current_jalali_month
    jm, jy = current_jalali_month()
    db.add(Budget(user_id=1, month=jm, year=jy, amount=8_500_000))
    db.commit()
    ctx = build_finance_context(user(db), db)
    fa = ctx["financial_availability"]
    assert fa["apparent_remaining_budget"] == 8_500_000
    assert fa["actual_cash_balance_tracked"] is False
    assert fa["actual_cash_balance_amount"] is None


def test_delete_wrapped_reason_is_not_clearly_malicious():
    """A DELETE rejected because it's disabled for transactions is not
    'clearly malicious'; the planner is allowed to try a different repair
    path (e.g. answer with a menu-guidance final_response_hint)."""
    from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
    from app.services.agent_orchestrator.types import AgentExecutionResult

    orch = AgentOrchestrator()
    r = AgentExecutionResult(
        step_id="x",
        operation_type=AgentOperationType.delete,
        allowed=False,
        executed=False,
        rejected_reason="DELETE from this table is forbidden",
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
