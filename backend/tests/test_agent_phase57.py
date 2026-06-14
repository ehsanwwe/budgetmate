"""Phase 5.7 — Idempotency, Current-Turn Guard & Goal-vs-Commitment tests."""
from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import AgentSqlAuditLog, Category, FutureCommitment, Goal, Transaction, User
from app.models.agent_idempotency import AgentOperationEvent
from app.models.transaction import TransactionType
from app.services.agent_orchestrator.date_utils import local_today
from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
from app.services.agent_orchestrator.sql_executor import SqlExecutor, _compute_fingerprint
from app.services.agent_orchestrator.sql_validator import SqlValidator
from app.services.agent_orchestrator.types import (
    AgentFinalResponse,
    AgentOperationType,
    AgentPlan,
    AgentPlanStep,
    SourceScope,
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


def current_user(db):
    return db.query(User).filter(User.id == 1).first()


# ── helpers ──────────────────────────────────────────────────────────────────

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
        # When exhausted, return a no-step plan preserving the last hint so the orchestrator
        # can compose a proper response from actual execution results.
        return AgentPlan(
            intent=self._last.intent if self._last else "final",
            final_response_hint=self._last.final_response_hint if self._last else "",
        )


def _insert_goal_step(title, amount, deadline=None) -> AgentPlanStep:
    params = {"title": title, "target_amount": amount, "status": "active"}
    cols = "title, target_amount, status"
    vals = ":title, :target_amount, :status"
    if deadline:
        params["deadline"] = deadline
        cols += ", deadline"
        vals += ", :deadline"
    return AgentPlanStep(
        step_id="g1",
        operation_type=AgentOperationType.insert,
        purpose="insert goal",
        table_name="goals",
        sql=f"INSERT INTO goals ({cols}) VALUES ({vals})",
        params=params,
        source_scope=SourceScope.current_message,
    )


def _insert_commitment_step(title, amount, due_month=None) -> AgentPlanStep:
    params = {"title": title, "amount": amount, "status": "pending", "source": "chat"}
    cols = "title, amount, status, source"
    vals = ":title, :amount, :status, :source"
    if due_month:
        params["due_month"] = due_month
        cols += ", due_month"
        vals += ", :due_month"
    return AgentPlanStep(
        step_id="c1",
        operation_type=AgentOperationType.insert,
        purpose="insert future commitment",
        table_name="future_commitments",
        sql=f"INSERT INTO future_commitments ({cols}) VALUES ({vals})",
        params=params,
        source_scope=SourceScope.current_message,
    )


# ── SECTION 1: Current-turn execution guard ───────────────────────────────────

def test_history_context_write_is_rejected_by_orchestrator(db):
    """An INSERT step tagged source_scope=history_context must be blocked."""
    plan = AgentPlan(
        intent="replay_from_history",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="bad",
                operation_type=AgentOperationType.insert,
                purpose="replay old washing machine from history",
                table_name="future_commitments",
                sql="INSERT INTO future_commitments (title, amount, status, source) VALUES (:title, :amount, :status, :source)",
                params={"title": "ماشین لباسشویی", "amount": 47_000_000, "status": "pending", "source": "chat"},
                source_scope=SourceScope.history_context,  # ← must be blocked
            )
        ],
    )
    final_plan = AgentPlan(intent="final", final_response_hint="پاسخ داده شد.")
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan, final_plan])).run(
        db, current_user(db), "سلام"
    ))
    # Nothing was inserted
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 0
    # Audit shows rejected
    rejected = db.query(AgentSqlAuditLog).filter(AgentSqlAuditLog.validation_status == "rejected").first()
    assert rejected is not None
    assert "history_context" in (rejected.rejected_reason or "")


def test_greeting_with_history_does_not_replay_old_goal(db):
    """Sending 'سلام' with a history of a prior goal creation must not re-create the goal."""
    plan = AgentPlan(
        intent="greeting",
        requires_db=False,
        final_response_hint="سلام! چطور می‌تونم کمکت کنم؟",
    )
    history = [
        {"role": "user", "content": "ماشین لباسشویی میخام بخرم تا آخر خرداد ۴۷ میلیون"},
        {"role": "assistant", "content": "هدف خرید ماشین لباسشویی با مبلغ ۴۷ میلیون ثبت شد."},
    ]
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, current_user(db), "سلام", history=history
    ))
    # No goal should be created from history
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 0
    assert "سلام" in result.message or "کمک" in result.message


def test_deadline_question_does_not_replay_prior_update(db):
    """Asking 'این هدف تا کی فعال هست؟' must never replay a prior update confirmation."""
    goal = Goal(user_id=1, title="خرید لپتاپ", target_amount=200_000_000, current_amount=2_500_000)
    db.add(goal)
    db.commit()

    # Plan: SELECT goals only — this is a question turn, no writes
    plan = AgentPlan(
        intent="goal_timing_question",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="goals",
                operation_type=AgentOperationType.select,
                purpose="read active goals to answer deadline question",
                table_name="goals",
                sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE is_active = :active",
                params={"active": True},
                source_scope=SourceScope.current_message,
            )
        ],
        # Hint with LEAKED old update confirmation at end (the live bug)
        final_response_hint="موعد این هدف تا ۱۶ خرداد ۱۴۰۵ فعال است.موعد خرید لپتاپ به یک ماه بعد منتقل شد",
    )
    final_plan = AgentPlan(intent="final", final_response_hint="پاسخ داده شد.")
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan, final_plan])).run(
        db, current_user(db), "این هدف تا کی فعال هست؟"
    ))
    # Must NOT contain the leaked update confirmation
    assert "منتقل شد" not in result.message
    # No UPDATE was created
    assert db.query(AgentSqlAuditLog).filter(AgentSqlAuditLog.operation_type == "update").count() == 0


# ── SECTION 2: Idempotency / deduplication ───────────────────────────────────

def test_fingerprint_computation_is_stable(db):
    """Same semantic params must always produce the same fingerprint."""
    fp1 = _compute_fingerprint(1, "insert", "goals", {"title": "لپتاپ", "target_amount": 80_000_000, "status": "active"})
    fp2 = _compute_fingerprint(1, "insert", "goals", {"title": "لپتاپ", "target_amount": 80_000_000, "status": "active"})
    assert fp1 == fp2


def test_fingerprint_differs_by_user(db):
    fp1 = _compute_fingerprint(1, "insert", "goals", {"title": "لپتاپ", "target_amount": 80_000_000})
    fp2 = _compute_fingerprint(2, "insert", "goals", {"title": "لپتاپ", "target_amount": 80_000_000})
    assert fp1 != fp2


def test_fingerprint_differs_by_amount():
    fp1 = _compute_fingerprint(1, "insert", "future_commitments", {"title": "چک", "amount": 50_000_000})
    fp2 = _compute_fingerprint(1, "insert", "future_commitments", {"title": "چک", "amount": 30_000_000})
    assert fp1 != fp2


def test_per_turn_duplicate_write_is_skipped(db):
    """Running the same INSERT step twice in one orchestrator.run() must insert only once."""
    step = AgentPlanStep(
        step_id="g1",
        operation_type=AgentOperationType.insert,
        purpose="insert goal",
        table_name="goals",
        sql="INSERT INTO goals (title, target_amount, status) VALUES (:title, :target_amount, :status)",
        params={"title": "لپتاپ", "target_amount": 80_000_000, "status": "active"},
        source_scope=SourceScope.current_message,
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    executor = SqlExecutor()
    seen: set[str] = set()
    r1 = executor.execute(db, current_user(db), step, validation, "goal_insert", seen)
    assert r1.executed
    assert not r1.skipped_duplicate
    seen.add(r1.operation_fingerprint)

    r2 = executor.execute(db, current_user(db), step, validation, "goal_insert", seen)
    assert not r2.executed
    assert r2.skipped_duplicate

    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1


def test_cross_turn_duplicate_is_skipped(db):
    """An INSERT with the same fingerprint within the dedup window must be skipped."""
    step = AgentPlanStep(
        step_id="g1",
        operation_type=AgentOperationType.insert,
        purpose="insert commitment",
        table_name="future_commitments",
        sql="INSERT INTO future_commitments (title, amount, status, source) VALUES (:title, :amount, :status, :source)",
        params={"title": "چک", "amount": 50_000_000, "status": "pending", "source": "chat"},
        source_scope=SourceScope.current_message,
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    executor = SqlExecutor()

    r1 = executor.execute(db, current_user(db), step, validation, "commitment_insert", set())
    assert r1.executed

    # Second call (simulating replay) — within the dedup window
    r2 = executor.execute(db, current_user(db), step, validation, "commitment_insert", set())
    assert not r2.executed
    assert r2.skipped_duplicate

    # Only one commitment in DB
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 1


def test_semantic_future_commitment_duplicate_with_different_metadata_is_skipped(db):
    """Same obligation with different description/source-like metadata must not insert twice."""
    executor = SqlExecutor()
    validator = SqlValidator()
    seen: set[str] = set()

    first = AgentPlanStep(
        step_id="rent1",
        operation_type=AgentOperationType.insert,
        purpose="insert rent commitment",
        table_name="future_commitments",
        sql="INSERT INTO future_commitments (title, amount, due_date, description, status, source) VALUES (:title, :amount, :due_date, :description, :status, :source)",
        params={
            "title": "کرایه خانه",
            "amount": 25_000_000,
            "due_date": "دو هفته بعد",
            "description": "پرداخت کرایه خانه",
            "status": "pending",
            "source": "chat",
        },
        source_scope=SourceScope.current_message,
    )
    second = AgentPlanStep(
        step_id="rent2",
        operation_type=AgentOperationType.insert,
        purpose="insert duplicated rent commitment",
        table_name="future_commitments",
        sql="INSERT INTO future_commitments (title, amount, due_date, description, status, source) VALUES (:title, :amount, :due_date, :description, :status, :source)",
        params={
            "title": "پرداخت کرایه خانه",
            "amount": "۲۵ ملیون",
            "due_date": "دو هفته بعد",
            "description": "یادآوری کرایه",
            "status": "pending",
            "source": "chat",
        },
        source_scope=SourceScope.current_message,
    )

    r1 = executor.execute(db, current_user(db), first, validator.validate(first.operation_type, first.table_name, first.sql, first.params), "rent", seen)
    assert r1.executed
    if r1.operation_fingerprint:
        seen.add(r1.operation_fingerprint)

    r2 = executor.execute(db, current_user(db), second, validator.validate(second.operation_type, second.table_name, second.sql, second.params), "rent", seen)
    assert not r2.executed
    assert r2.skipped_duplicate
    assert r2.existing_record_id == r1.inserted_id
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 1


def test_orchestrator_duplicate_future_commitment_steps_create_one_row(db):
    """A planner response containing duplicate rent commitments must create only one row."""
    plan = AgentPlan(
        intent="rent_future_commitment",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="c1",
                operation_type=AgentOperationType.insert,
                purpose="insert rent commitment",
                table_name="future_commitments",
                sql="INSERT INTO future_commitments (title, amount, due_date, status, source) VALUES (:title, :amount, :due_date, :status, :source)",
                params={"title": "کرایه خانه", "amount": 25_000_000, "due_date": "دو هفته بعد", "status": "pending", "source": "chat"},
                source_scope=SourceScope.current_message,
            ),
            AgentPlanStep(
                step_id="c2",
                operation_type=AgentOperationType.insert,
                purpose="duplicate rent commitment from same plan",
                table_name="future_commitments",
                sql="INSERT INTO future_commitments (title, amount, due_date, description, status, source) VALUES (:title, :amount, :due_date, :description, :status, :source)",
                params={"title": "پرداخت کرایه خانه", "amount": 25_000_000, "due_date": "دو هفته بعد", "description": "تعهد کرایه", "status": "pending", "source": "chat"},
                source_scope=SourceScope.current_message,
            ),
        ],
        final_response_hint="تعهد کرایه خانه ثبت شد.",
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, current_user(db), "دو هفته دیگه باید کرایه خونه بدم"
    ))
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 1
    skipped = db.query(AgentSqlAuditLog).filter(AgentSqlAuditLog.validation_status == "skipped_duplicate").first()
    assert skipped is not None


def test_legitimate_different_date_transactions_are_not_deduplicated(db):
    """Daily bus fares on different dates must each be allowed (different fingerprints)."""
    step_today = AgentPlanStep(
        step_id="t1",
        operation_type=AgentOperationType.insert,
        purpose="bus fare today",
        table_name="transactions",
        sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
        params={"amount": 40_000, "type": "expense", "description": "bus", "date": local_today().isoformat()},
        source_scope=SourceScope.current_message,
    )
    step_yesterday = step_today.model_copy(
        update={"params": {**step_today.params, "date": (local_today() - timedelta(days=1)).isoformat()}}
    )
    v = SqlValidator()
    executor = SqlExecutor()
    r1 = executor.execute(db, current_user(db), step_today, v.validate(step_today.operation_type, step_today.table_name, step_today.sql, step_today.params), "bus", set())
    r2 = executor.execute(db, current_user(db), step_yesterday, v.validate(step_yesterday.operation_type, step_yesterday.table_name, step_yesterday.sql, step_yesterday.params), "bus", set())
    assert r1.executed
    assert r2.executed
    assert not r2.skipped_duplicate
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 2


def test_operation_event_is_recorded_on_insert(db):
    """AgentOperationEvent must be created for successful INSERT."""
    step = AgentPlanStep(
        step_id="g1",
        operation_type=AgentOperationType.insert,
        purpose="insert goal",
        table_name="goals",
        sql="INSERT INTO goals (title, target_amount, status) VALUES (:title, :target_amount, :status)",
        params={"title": "خرید خانه", "target_amount": 1_000_000_000, "status": "active"},
        source_scope=SourceScope.current_message,
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    SqlExecutor().execute(db, current_user(db), step, validation, "goal_insert", set())
    event = db.query(AgentOperationEvent).filter(AgentOperationEvent.user_id == 1).first()
    assert event is not None
    assert event.operation_type == "insert"
    assert event.table_name == "goals"
    assert event.status == "executed"


# ── SECTION 3: Goal vs future commitment classification ───────────────────────

def test_washing_machine_creates_goal_not_commitment(db):
    """'میخام بخرم' wording → goal, not future commitment."""
    plan = AgentPlan(
        intent="goal_creation_washing_machine",
        requires_db=True,
        steps=[_insert_goal_step("خرید ماشین لباسشویی", 47_000_000, "آخر خرداد")],
        final_response_hint="هدف خرید ماشین لباسشویی با مبلغ ۴۷ میلیون تومان ثبت شد.",
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, current_user(db), "میخام تا آخر خرداد یک ماشین لباسشویی بخرم به مبلغ ۴۷ ملیون"
    ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 0
    goal = db.query(Goal).filter(Goal.user_id == 1).first()
    assert goal.target_amount == 47_000_000
    assert goal.status == "active"


def test_sport_ring_creates_goal_not_commitment(db):
    """'میخام بخرم' for car ring → goal, not future commitment."""
    plan = AgentPlan(
        intent="goal_creation_ring",
        requires_db=True,
        steps=[_insert_goal_step("رینگ اسپورت", 200_000_000, "ماه آینده")],
        final_response_hint="هدف خرید رینگ اسپورت با مبلغ ۲۰۰ میلیون تومان ثبت شد.",
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, current_user(db), "رینگ اسپورت میخام بخرم ماه آینده ۲۰۰ میلیون"
    ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 0


def test_check_creates_future_commitment_not_goal(db):
    """'چک دارم' wording → future commitment, not goal."""
    plan = AgentPlan(
        intent="future_commitment_check",
        requires_db=True,
        steps=[_insert_commitment_step("چک ماه بعد", 50_000_000, "ماه بعد")],
        final_response_hint="تعهد چک ماه بعد ۵۰ میلیون ثبت شد.",
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, current_user(db), "چک دارم ماه بعد ۵۰ میلیون"
    ))
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 1
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0


def test_rent_creates_future_commitment_not_goal(db):
    """'باید کرایه بدهم' → future commitment."""
    plan = AgentPlan(
        intent="future_commitment_rent",
        requires_db=True,
        steps=[_insert_commitment_step("کرایه خانه", 20_000_000, "ماه بعد")],
        final_response_hint="تعهد پرداخت کرایه خانه ماه بعد ۲۰ میلیون ثبت شد.",
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, current_user(db), "باید کرایه خونه بدم ماه بعد ۲۰ میلیون"
    ))
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 1
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0


def test_tour_split_creates_transaction_and_commitment(db):
    """'تور ثبت نام کردم، ۲۰ میلیون دادم، ۴۰ میلیون ماه بعد' → tx + commitment."""
    plans = [
        AgentPlan(
            intent="tour_split_payment",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="tx",
                    operation_type=AgentOperationType.insert,
                    purpose="record current payment",
                    table_name="transactions",
                    sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
                    params={"amount": 20_000_000, "type": "expense", "description": "پرداخت اول تور", "date": local_today().isoformat()},
                    source_scope=SourceScope.current_message,
                ),
                _insert_commitment_step("باقی‌مانده تور", 40_000_000, "ماه بعد"),
            ],
            final_response_hint="۲۰ میلیون تومان پرداخت شد و ۴۰ میلیون تعهد ماه بعد ثبت شد.",
        )
    ]
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner(plans)).run(
        db, current_user(db), "تور ثبت‌نام کردم، الان ۲۰ میلیون دادم، ۴۰ میلیونش می‌افته ماه بعد"
    ))
    assert db.query(Transaction).filter(Transaction.user_id == 1, Transaction.amount == 20_000_000).count() == 1
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1, FutureCommitment.amount == 40_000_000).count() == 1
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 0


# ── SECTION 4: Goal deadline update persistence and response ─────────────────

def test_goal_deadline_update_persists_and_response_uses_updated_row(db):
    """Deadline update must commit to DB and response must confirm updated state."""
    goal = Goal(user_id=1, title="خرید لپتاپ", target_amount=200_000_000, current_amount=2_500_000, is_active=True)
    db.add(goal)
    db.commit()
    from app.services.agent_orchestrator.date_utils import parse_relative_date
    new_deadline = parse_relative_date("یک ماه بعد")

    plans = [
        AgentPlan(
            intent="update_goal_deadline",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="goals",
                    operation_type=AgentOperationType.select,
                    purpose="read goals before matching laptop",
                    table_name="goals",
                    sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE is_active = :active",
                    params={"active": True},
                    source_scope=SourceScope.current_message,
                )
            ],
        ),
        AgentPlan(
            intent="update_goal_deadline",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="update",
                    operation_type=AgentOperationType.update,
                    purpose="update matched laptop goal deadline",
                    table_name="goals",
                    sql="UPDATE goals SET deadline = :deadline WHERE id = :id",
                    params={"deadline": "یک ماه بعد", "id": goal.id},
                    source_scope=SourceScope.current_message,
                )
            ],
            final_response_hint="موعد خرید لپتاپ به یک ماه دیرتر منتقل شد.",
        ),
        AgentPlan(intent="final", final_response_hint="موعد خرید لپتاپ به یک ماه دیرتر منتقل شد."),
    ]
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner(plans)).run(
        db, current_user(db), "خرید لپتاپ را به یک ماه دیرتر تغییر بده"
    ))
    db.refresh(goal)
    # DB row must be updated
    assert goal.deadline == new_deadline, f"Expected {new_deadline}, got {goal.deadline}"
    # Response must mention the successful update (not claim nothing happened)
    assert "منتقل شد" in result.message or "به‌روزرسانی شد" in result.message or "تغییر" in result.message


def test_deadline_question_after_update_does_not_replay_update(db):
    """Asking about a deadline after a prior update must SELECT only, no new UPDATE."""
    goal = Goal(user_id=1, title="خرید لپتاپ", target_amount=200_000_000, current_amount=0, is_active=True)
    db.add(goal)
    db.commit()

    select_plan = AgentPlan(
        intent="goal_timing_question",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="goals",
                operation_type=AgentOperationType.select,
                purpose="read goal to answer deadline question",
                table_name="goals",
                sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE is_active = :active",
                params={"active": True},
                source_scope=SourceScope.current_message,
            )
        ],
        final_response_hint="موعد این هدف تا ۱۶ خرداد ۱۴۰۵ فعال است.",
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([select_plan])).run(
        db, current_user(db), "این هدف تا کی فعال هست؟",
        history=[
            {"role": "user", "content": "خرید لپتاپ را به یک ماه دیرتر تغییر بده"},
            {"role": "assistant", "content": "موعد خرید لپتاپ به یک ماه دیرتر منتقل شد."},
        ]
    ))
    # Must NOT have created an UPDATE
    assert db.query(AgentSqlAuditLog).filter(AgentSqlAuditLog.operation_type == "update").count() == 0
    # Must NOT replay old update confirmation in the answer
    assert "منتقل شد" not in result.message


# ── SECTION 5: Response leakage prevention ───────────────────────────────────

def test_leaked_op_confirmation_stripped_from_select_hint(db):
    """Leaked operation suffix in SELECT hint must be stripped before returning."""
    goal = Goal(user_id=1, title="هدف تست", target_amount=50_000_000, current_amount=0, is_active=True)
    db.add(goal)
    db.commit()

    # Simulate hint with leaked old-turn operation appended
    plan = AgentPlan(
        intent="goal_timing_question",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="goals",
                operation_type=AgentOperationType.select,
                purpose="read goals",
                table_name="goals",
                sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE is_active = :active",
                params={"active": True},
                source_scope=SourceScope.current_message,
            )
        ],
        final_response_hint="هدف شما تا خرداد ۱۴۰۵ فعال است.موعد خرید لپتاپ به یک ماه بعد منتقل شد",
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, current_user(db), "این هدف تا کی فعال هست؟"
    ))
    assert "منتقل شد" not in result.message
    # The actual answer part must still be present
    assert "خرداد" in result.message or "هدف" in result.message


# ── SECTION 6: Source scope enforcement ──────────────────────────────────────

def test_source_scope_field_defaults_to_current_message():
    step = AgentPlanStep(
        step_id="s1",
        operation_type=AgentOperationType.insert,
        purpose="test",
        table_name="goals",
    )
    assert step.source_scope == SourceScope.current_message


def test_history_context_select_is_allowed(db):
    """SELECT with source_scope=history_context must be allowed (context reads are fine)."""
    plan = AgentPlan(
        intent="context_read",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="s1",
                operation_type=AgentOperationType.select,
                purpose="read user context",
                table_name="goals",
                sql="SELECT id, title FROM goals WHERE is_active = :active",
                params={"active": True},
                source_scope=SourceScope.history_context,  # SELECT is fine
            )
        ],
        final_response_hint="بر اساس تاریخچه، اهداف شما بررسی شد.",
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, current_user(db), "تاریخچه اهداف من"
    ))
    # SELECT was allowed
    assert db.query(AgentSqlAuditLog).filter(AgentSqlAuditLog.operation_type == "select").count() == 1


def test_history_context_update_is_blocked(db):
    """UPDATE with source_scope=history_context must be rejected."""
    goal = Goal(user_id=1, title="هدف", target_amount=10_000_000, current_amount=0)
    db.add(goal)
    db.commit()
    original_deadline = goal.deadline

    plan = AgentPlan(
        intent="replay_update",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="u1",
                operation_type=AgentOperationType.update,
                purpose="replay deadline update from history",
                table_name="goals",
                sql="UPDATE goals SET deadline = :deadline WHERE id = :id",
                params={"deadline": "یک سال بعد", "id": goal.id},
                source_scope=SourceScope.history_context,  # ← must be blocked
            )
        ],
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, current_user(db), "سلام"
    ))
    db.refresh(goal)
    # Deadline must NOT have changed
    assert goal.deadline == original_deadline
    # Audit shows rejected
    rejected_audit = db.query(AgentSqlAuditLog).filter(AgentSqlAuditLog.validation_status == "rejected").first()
    assert rejected_audit is not None


# ── SECTION 7: Security regression tests ─────────────────────────────────────

def test_drop_table_is_still_rejected(db):
    """DROP TABLE must be rejected even after Phase 5.7 changes."""
    plan = AgentPlan(
        intent="drop_table",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="bad",
                operation_type=AgentOperationType.select,
                purpose="drop users",
                table_name="users",
                sql="DROP TABLE users",
                params={},
            )
        ],
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, current_user(db), "DROP TABLE users"
    ))
    assert "امن" in result.message
    audit = db.query(AgentSqlAuditLog).filter(AgentSqlAuditLog.validation_status == "rejected").first()
    assert audit is not None


def test_user_id_in_params_is_rejected(db):
    """LLM-provided user_id in params must still be rejected."""
    from app.services.agent_orchestrator.sql_validator import SqlValidator
    result = SqlValidator().validate(
        AgentOperationType.insert,
        "transactions",
        "INSERT INTO transactions (user_id, amount, type) VALUES (:user_id, :amount, :type)",
        {"user_id": 99, "amount": 10_000, "type": "expense"},
    )
    assert not result.allowed
    assert "user_id" in (result.rejected_reason or "")


# ── SECTION 8: Planner history format ────────────────────────────────────────

def test_planner_receives_history_as_context_block(monkeypatch, db):
    """History must be passed as labeled system context, not bare conversation turns."""
    received_messages = []

    async def fake_completion(messages, **kwargs):
        received_messages.extend(messages)
        import json
        from app.services.agent_orchestrator.types import AgentPlan
        plan = AgentPlan(intent="test", final_response_hint="ok.")
        return json.dumps(plan.model_dump(mode="json"))

    monkeypatch.setattr("app.services.agent_orchestrator.planner.get_ai_chat_completion", fake_completion)

    history = [
        {"role": "user", "content": "ماشین لباسشویی میخام بخرم"},
        {"role": "assistant", "content": "مبلغ چقدر؟"},
    ]
    from app.services.agent_orchestrator.planner import AgentPlanner
    from app.services.agent_orchestrator.db_world import render_db_world

    asyncio.run(
        AgentPlanner().plan(
            render_db_world(db.get_bind()),
            "۴۷ میلیون",
            {},
            history=history,
        )
    )

    # History must appear as a single system message containing CONVERSATION HISTORY label
    system_contents = [m["content"] for m in received_messages if m.get("role") == "system"]
    history_block = next((c for c in system_contents if "CONVERSATION HISTORY" in c), None)
    assert history_block is not None, "history must be passed as labeled system context"
    assert "CONVERSATION HISTORY" in history_block
    assert "ماشین لباسشویی" in history_block

    # The current message must be marked explicitly as CURRENT USER MESSAGE
    user_messages = [m for m in received_messages if m.get("role") == "user"]
    assert any("CURRENT USER MESSAGE" in m["content"] for m in user_messages), (
        "current message must be marked as CURRENT USER MESSAGE"
    )

    # History items must NOT appear as individual user/assistant conversation turns
    # (they should only appear in the system context block)
    user_contents = [m["content"] for m in received_messages if m.get("role") == "user"]
    for content in user_contents:
        if "CURRENT USER MESSAGE" not in content:
            assert "ماشین لباسشویی" not in content, (
                "history must NOT appear as bare user messages"
            )
