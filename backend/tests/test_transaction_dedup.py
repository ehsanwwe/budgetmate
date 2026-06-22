"""Tests for chat-created transaction semantic dedup.

Root cause: the planner creates two INSERT INTO transactions steps — one without
category_id (unclassified) and one with category_id (after SELECT categories). They
produce different fingerprints so the fingerprint dedup misses them. The semantic
dedup added to SqlExecutor catches them via description token comparison.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Category, User
from app.models.agent_idempotency import AgentOperationEvent
from app.models.transaction import Transaction, TransactionType
from app.services.agent_orchestrator.date_utils import local_today
from app.services.agent_orchestrator.goal_intake import NullGoalIntakeGate
from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
from app.services.agent_orchestrator.sql_executor import SqlExecutor, normalize_transaction_description
from app.services.agent_orchestrator.sql_validator import SqlValidator
from app.services.agent_orchestrator.types import AgentOperationType, AgentPlan, AgentPlanStep


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
    session.add_all([
        User(id=1, phone="09120000001", name="Test", language="fa", chat_mode="normal"),
        Category(id=1, name="Food", icon="f", color="#111", is_default=True),
        Category(id=2, name="Transport", icon="t", color="#222", is_default=True),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _user(db):
    return db.query(User).filter(User.id == 1).first()


def _expense_step(description: str, category_id=None, amount: int = 200_000) -> AgentPlanStep:
    params: dict = {
        "amount": amount,
        "type": "expense",
        "description": description,
        "date": local_today().isoformat(),
    }
    if category_id is not None:
        params["category_id"] = category_id
        sql = (
            "INSERT INTO transactions (category_id, amount, type, description, date) "
            "VALUES (:category_id, :amount, :type, :description, :date)"
        )
    else:
        sql = "INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)"
    return AgentPlanStep(
        step_id="tx",
        operation_type=AgentOperationType.insert,
        table_name="transactions",
        sql=sql,
        params=params,
        purpose="record expense",
    )


class SequencePlanner:
    def __init__(self, plans):
        self.plans = list(plans)

    async def plan(self, *args, **kwargs):
        if self.plans:
            return self.plans.pop(0)
        return AgentPlan(intent="final", final_response_hint="ثبت شد.")


# ---------------------------------------------------------------------------
# Unit tests for normalize_transaction_description
# ---------------------------------------------------------------------------

def test_normalize_removes_generic_word_هزینه():
    assert normalize_transaction_description("هزینه اسنپ") == frozenset({"اسنپ"})


def test_normalize_bare_merchant():
    assert normalize_transaction_description("اسنپ") == frozenset({"اسنپ"})


def test_normalize_پول_دادم():
    assert normalize_transaction_description("پول تاکسی دادم") == frozenset({"تاکسی"})


def test_normalize_درآمد_stripped():
    result = normalize_transaction_description("درآمد فروش طلا")
    assert "درآمد" not in result
    assert "فروش" in result
    assert "طلا" in result


def test_normalize_empty_returns_empty():
    assert normalize_transaction_description("") == frozenset()
    assert normalize_transaction_description("   ") == frozenset()


def test_normalize_only_generic_words():
    assert normalize_transaction_description("هزینه پول پرداخت") == frozenset()


# ---------------------------------------------------------------------------
# Semantic dedup unit tests (SqlExecutor._check_semantic_transaction_duplicate)
# ---------------------------------------------------------------------------

def test_semantic_dedup_snap_variants_match(db):
    """'اسنپ' and 'هزینه اسنپ' are the same merchant — second should be duplicate."""
    today = local_today()
    db.add(Transaction(user_id=1, amount=200_000, type=TransactionType.expense,
                       description="اسنپ", date=today))
    db.commit()

    executor = SqlExecutor()
    result = executor._check_semantic_transaction_duplicate(db, _user(db), {
        "amount": 200_000, "type": "expense",
        "description": "هزینه اسنپ", "date": today.isoformat(),
    })
    assert result is not None


def test_semantic_dedup_different_merchant_not_duplicate(db):
    """'اسنپ' and 'تاکسی' are different merchants — must NOT be treated as duplicate."""
    today = local_today()
    db.add(Transaction(user_id=1, amount=200_000, type=TransactionType.expense,
                       description="اسنپ", date=today))
    db.commit()

    executor = SqlExecutor()
    result = executor._check_semantic_transaction_duplicate(db, _user(db), {
        "amount": 200_000, "type": "expense",
        "description": "تاکسی", "date": today.isoformat(),
    })
    assert result is None


def test_semantic_dedup_different_amount_not_duplicate(db):
    today = local_today()
    db.add(Transaction(user_id=1, amount=200_000, type=TransactionType.expense,
                       description="اسنپ", date=today))
    db.commit()

    executor = SqlExecutor()
    result = executor._check_semantic_transaction_duplicate(db, _user(db), {
        "amount": 300_000, "type": "expense",
        "description": "اسنپ", "date": today.isoformat(),
    })
    assert result is None


def test_semantic_dedup_different_date_not_duplicate(db):
    from datetime import timedelta
    yesterday = local_today() - timedelta(days=1)
    db.add(Transaction(user_id=1, amount=200_000, type=TransactionType.expense,
                       description="اسنپ", date=yesterday))
    db.commit()

    executor = SqlExecutor()
    result = executor._check_semantic_transaction_duplicate(db, _user(db), {
        "amount": 200_000, "type": "expense",
        "description": "اسنپ", "date": local_today().isoformat(),
    })
    assert result is None


def test_semantic_dedup_income_not_confused_with_expense(db):
    today = local_today()
    db.add(Transaction(user_id=1, amount=200_000, type=TransactionType.income,
                       description="درآمد اسنپ", date=today))
    db.commit()

    executor = SqlExecutor()
    result = executor._check_semantic_transaction_duplicate(db, _user(db), {
        "amount": 200_000, "type": "expense",
        "description": "اسنپ", "date": today.isoformat(),
    })
    assert result is None


# ---------------------------------------------------------------------------
# Integration tests via SqlExecutor.execute
# ---------------------------------------------------------------------------

def test_two_inserts_same_turn_one_transaction(db):
    """Two INSERT steps in the same plan with same merchant: only one should execute."""
    validator = SqlValidator()
    executor = SqlExecutor()
    u = _user(db)
    seen: set[str] = set()

    s1 = _expense_step("اسنپ")
    v1 = validator.validate(s1.operation_type, s1.table_name, s1.sql, s1.params)
    r1 = executor.execute(db, u, s1, v1, "dedup_test", seen)
    if r1.operation_fingerprint:
        seen.add(r1.operation_fingerprint)

    s2 = _expense_step("هزینه اسنپ")
    v2 = validator.validate(s2.operation_type, s2.table_name, s2.sql, s2.params)
    r2 = executor.execute(db, u, s2, v2, "dedup_test", seen)

    assert r1.executed is True
    assert r2.skipped_duplicate is True
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 1


def test_two_inserts_different_category_across_iterations_one_transaction(db):
    """First INSERT without category, second with category_id — semantic dedup catches it."""
    validator = SqlValidator()
    executor = SqlExecutor()
    u = _user(db)

    s1 = _expense_step("اسنپ")           # no category_id → FP1
    v1 = validator.validate(s1.operation_type, s1.table_name, s1.sql, s1.params)
    r1 = executor.execute(db, u, s1, v1, "dedup_test_iter1", set())

    s2 = _expense_step("هزینه اسنپ", category_id=2)   # category_id=2 → FP2 ≠ FP1
    v2 = validator.validate(s2.operation_type, s2.table_name, s2.sql, s2.params)
    r2 = executor.execute(db, u, s2, v2, "dedup_test_iter2", set())

    assert r1.executed is True
    assert r2.skipped_duplicate is True
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 1


# ---------------------------------------------------------------------------
# Orchestrator-level integration tests
# ---------------------------------------------------------------------------

def test_orchestrator_snap_expense_one_transaction(db):
    """Simple snap expense from chat creates exactly one transaction."""
    plan = AgentPlan(
        intent="expense_registration",
        requires_db=True,
        steps=[_expense_step("هزینه اسنپ", category_id=2)],
    )
    final = AgentPlan(intent="final", final_response_hint="هزینه اسنپ ثبت شد.")
    asyncio.run(
        AgentOrchestrator(goal_intake_gate=NullGoalIntakeGate(), planner=SequencePlanner([plan, final])).run(
            db, _user(db), "دیروز ۲۰۰ پول اسنپ دادم"
        )
    )
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 1


def test_orchestrator_two_plan_iterations_one_transaction(db):
    """Planner emits uncategorized insert then categorized insert — only one row."""
    plan1 = AgentPlan(
        intent="expense_registration",
        requires_db=True,
        steps=[_expense_step("اسنپ")],
    )
    plan2 = AgentPlan(
        intent="expense_registration",
        requires_db=True,
        steps=[_expense_step("هزینه اسنپ", category_id=2)],
    )
    final = AgentPlan(intent="final", final_response_hint="ثبت شد.")
    asyncio.run(
        AgentOrchestrator(goal_intake_gate=NullGoalIntakeGate(), planner=SequencePlanner([plan1, plan2, final])).run(
            db, _user(db), "دیروز ۲۰۰ پول اسنپ دادم"
        )
    )
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 1


def test_income_still_creates_one_record(db):
    """Income from chat creates exactly one transaction (dedup must not over-block)."""
    plan = AgentPlan(
        intent="income_registration",
        requires_db=True,
        steps=[AgentPlanStep(
            step_id="tx",
            operation_type=AgentOperationType.insert,
            table_name="transactions",
            sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
            params={"amount": 4_000_000, "type": "income", "description": "درآمد فروش طلا", "date": local_today().isoformat()},
            purpose="record income",
        )],
    )
    final = AgentPlan(intent="final", final_response_hint="ثبت شد.")
    asyncio.run(
        AgentOrchestrator(goal_intake_gate=NullGoalIntakeGate(), planner=SequencePlanner([plan, final])).run(
            db, _user(db), "امروز ۴ میلیون تومان از فروش طلا به دست آوردم"
        )
    )
    assert db.query(Transaction).filter(
        Transaction.user_id == 1, Transaction.type == TransactionType.income
    ).count() == 1


def test_client_message_id_prevents_double_submit(db):
    """Same client_message_id sent twice does not create two transactions."""
    plan = AgentPlan(
        intent="expense_registration",
        requires_db=True,
        steps=[_expense_step("اسنپ")],
    )
    final = AgentPlan(intent="final", final_response_hint="ثبت شد.")
    client_id = "test-cmid-snap-dedup-001"

    asyncio.run(
        AgentOrchestrator(goal_intake_gate=NullGoalIntakeGate(), planner=SequencePlanner([plan, final])).run(
            db, _user(db), "دیروز ۲۰۰ پول اسنپ دادم", client_message_id=client_id
        )
    )
    # Second request with the same client_message_id — should be a no-op
    plan2 = AgentPlan(
        intent="expense_registration",
        requires_db=True,
        steps=[_expense_step("اسنپ")],
    )
    final2 = AgentPlan(intent="final", final_response_hint="ثبت شد.")
    asyncio.run(
        AgentOrchestrator(goal_intake_gate=NullGoalIntakeGate(), planner=SequencePlanner([plan2, final2])).run(
            db, _user(db), "دیروز ۲۰۰ پول اسنپ دادم", client_message_id=client_id
        )
    )
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 1


def test_semantic_dedup_different_merchant_cross_turn_not_blocked(db):
    """Semantic dedup must NOT flag snap vs taxi as duplicates (different merchants).

    Note: the fingerprint-based cross-turn dedup (AgentOperationEvent) uses a hash
    that excludes `description`, so two same-amount expenses on the same day will share
    a fingerprint regardless of merchant. That pre-existing broad fingerprint behaviour
    is separate from the semantic dedup introduced here. This test verifies only the
    semantic layer, which is the one responsible for the 'اسنپ'/'هزینه اسنپ' bug.
    """
    today = local_today()
    db.add(Transaction(user_id=1, amount=200_000, type=TransactionType.expense,
                       description="اسنپ", date=today))
    db.commit()

    executor = SqlExecutor()
    # Semantic dedup should return None for a different merchant
    result = executor._check_semantic_transaction_duplicate(db, _user(db), {
        "amount": 200_000, "type": "expense",
        "description": "تاکسی", "date": today.isoformat(),
    })
    assert result is None, "semantic dedup must NOT block a different merchant"
