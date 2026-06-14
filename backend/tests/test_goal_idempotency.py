"""Goal creation idempotency tests — prevents duplicate goals from chat.

Covers:
- Duplicate INSERT steps in one plan
- Planner loop repeating same INSERT across iterations
- Semantic title variants (with/without prefixes)
- Existing active goal blocks new insert
- Different goals are NOT falsely deduped
- User-scoping (two users can create same-named goal)
- Normalized fingerprint for goal titles
- Clean response when duplicate is detected
- Expense/commitment regression (still works)
- Stream and message endpoints both protected
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.db import Base, get_db
from app.main import app
from app.models import Category, FutureCommitment, Goal, Transaction, User
from app.models.transaction import TransactionType
from app.routers import chat as chat_router
from app.services.agent_orchestrator.date_utils import local_today
from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
from app.services.agent_orchestrator.sql_executor import SqlExecutor, _compute_fingerprint
from app.services.agent_orchestrator.sql_validator import SqlValidator
from app.services.agent_orchestrator.types import AgentFinalResponse, AgentOperationType, AgentPlan, AgentPlanStep, SourceScope
from app.services.personal_cfo.goal_context_service import normalize_goal_text


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
        User(id=2, phone="09120000002", name="Other", language="fa"),
        Category(id=1, name="Food", icon="f", color="#111", is_default=True),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()


def u1(db):
    return db.query(User).filter(User.id == 1).first()


def u2(db):
    return db.query(User).filter(User.id == 2).first()


def _goal_step(title: str, amount: int, step_id: str = "g1", deadline: str | None = None) -> AgentPlanStep:
    params: dict = {"title": title, "target_amount": amount, "status": "active"}
    cols = "title, target_amount, status"
    vals = ":title, :target_amount, :status"
    if deadline:
        params["deadline"] = deadline
        cols += ", deadline"
        vals += ", :deadline"
    return AgentPlanStep(
        step_id=step_id,
        operation_type=AgentOperationType.insert,
        purpose="create goal",
        table_name="goals",
        sql=f"INSERT INTO goals ({cols}) VALUES ({vals})",
        params=params,
        source_scope=SourceScope.current_message,
    )


class SequencePlanner:
    def __init__(self, plans):
        self.plans = list(plans)
        self._last: AgentPlan | None = None

    async def plan(self, *args, **kwargs):
        if self.plans:
            self._last = self.plans.pop(0)
            return self._last
        return AgentPlan(
            intent=self._last.intent if self._last else "final",
            final_response_hint=self._last.final_response_hint if self._last else "",
        )


# ── Section 1: normalize_goal_text prefix stripping ──────────────────────────

def test_normalize_strips_khrid_prefix():
    assert normalize_goal_text("خرید انگشتر طلا") == "انگشتر طلا"

def test_normalize_strips_hadaf_prefix():
    assert normalize_goal_text("هدف انگشتر طلا") == "انگشتر طلا"

def test_normalize_strips_hadaf_khrid_prefix():
    assert normalize_goal_text("هدف خرید انگشتر طلا") == "انگشتر طلا"

def test_normalize_bare_title_unchanged():
    assert normalize_goal_text("انگشتر طلا") == "انگشتر طلا"

def test_normalize_does_not_affect_laptop_synonym():
    assert normalize_goal_text("لپ تاب") == "لپتاپ"

def test_normalize_different_goals_stay_different():
    assert normalize_goal_text("انگشتر طلا") != normalize_goal_text("سکه طلا")


# ── Section 2: Fingerprint normalizes goal title ──────────────────────────────

def test_fingerprint_goal_title_normalized_bare_vs_prefix():
    fp1 = _compute_fingerprint(1, "insert", "goals", {"title": "انگشتر طلا", "target_amount": 100_000_000})
    fp2 = _compute_fingerprint(1, "insert", "goals", {"title": "خرید انگشتر طلا", "target_amount": 100_000_000})
    assert fp1 == fp2, "fingerprint must be identical after title prefix normalization"

def test_fingerprint_goal_title_hadaf_prefix_normalized():
    fp1 = _compute_fingerprint(1, "insert", "goals", {"title": "انگشتر طلا", "target_amount": 100_000_000})
    fp2 = _compute_fingerprint(1, "insert", "goals", {"title": "هدف خرید انگشتر طلا", "target_amount": 100_000_000})
    assert fp1 == fp2

def test_fingerprint_different_goals_differ():
    fp1 = _compute_fingerprint(1, "insert", "goals", {"title": "انگشتر طلا", "target_amount": 100_000_000})
    fp2 = _compute_fingerprint(1, "insert", "goals", {"title": "سکه طلا", "target_amount": 100_000_000})
    assert fp1 != fp2

def test_fingerprint_goal_user_scoped():
    fp1 = _compute_fingerprint(1, "insert", "goals", {"title": "انگشتر طلا", "target_amount": 100_000_000})
    fp2 = _compute_fingerprint(2, "insert", "goals", {"title": "انگشتر طلا", "target_amount": 100_000_000})
    assert fp1 != fp2


# ── Section 3: Per-turn duplicate steps create only one row ──────────────────

def test_duplicate_goal_steps_in_one_plan_creates_one_row(db):
    """Two identical INSERT goal steps in a single plan must yield exactly one DB row."""
    plan = AgentPlan(
        intent="goal_create",
        requires_db=True,
        steps=[
            _goal_step("انگشتر طلا", 100_000_000, step_id="g1"),
            _goal_step("انگشتر طلا", 100_000_000, step_id="g2"),
        ],
        final_response_hint="هدف ثبت شد.",
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, u1(db), "میخوام هدف انگشتر طلا بسازم"
    ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1

def test_duplicate_goal_steps_with_prefix_variant_creates_one_row(db):
    """Steps with 'خرید ' prefix vs without must deduplicate via normalized fingerprint."""
    plan = AgentPlan(
        intent="goal_create",
        requires_db=True,
        steps=[
            _goal_step("انگشتر طلا", 100_000_000, step_id="g1"),
            _goal_step("خرید انگشتر طلا", 100_000_000, step_id="g2"),
        ],
        final_response_hint="هدف ثبت شد.",
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, u1(db), "میخوام هدف انگشتر طلا بسازم"
    ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1


# ── Section 4: Planner loop repeating INSERT ─────────────────────────────────

def test_planner_loop_repeats_goal_insert_creates_one_row(db):
    """If the planner generates the same INSERT in iteration 2, it must be skipped."""
    plan1 = AgentPlan(
        intent="goal_create",
        requires_db=True,
        steps=[_goal_step("انگشتر طلا", 100_000_000)],
        final_response_hint="هدف ثبت شد.",
    )
    # Second iteration with same title creates duplicate — must be blocked
    plan2 = AgentPlan(
        intent="goal_create",
        requires_db=True,
        steps=[_goal_step("انگشتر طلا", 100_000_000)],
        final_response_hint="هدف ثبت شد.",
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan1, plan2])).run(
        db, u1(db), "میخوام هدف انگشتر طلا بسازم"
    ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1

def test_planner_loop_title_prefix_variant_creates_one_row(db):
    """Iteration 1 inserts 'انگشتر طلا', iteration 2 tries 'خرید انگشتر طلا' — same goal."""
    plan1 = AgentPlan(
        intent="goal_create",
        requires_db=True,
        steps=[_goal_step("انگشتر طلا", 100_000_000)],
        final_response_hint="هدف ثبت شد.",
    )
    plan2 = AgentPlan(
        intent="goal_create",
        requires_db=True,
        steps=[_goal_step("خرید انگشتر طلا", 100_000_000)],
        final_response_hint="هدف ثبت شد.",
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan1, plan2])).run(
        db, u1(db), "میخوام هدف انگشتر طلا بسازم"
    ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1


# ── Section 5: Existing active goal prevents duplicate ───────────────────────

def test_existing_active_goal_prevents_duplicate_insert(db):
    """If an active goal with same normalized title+amount already exists, skip insert."""
    db.add(Goal(user_id=1, title="انگشتر طلا", target_amount=100_000_000,
                current_amount=0, is_active=True, status="active"))
    db.commit()
    plan = AgentPlan(
        intent="goal_create",
        requires_db=True,
        steps=[_goal_step("انگشتر طلا", 100_000_000)],
        final_response_hint="هدف ثبت شد.",
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, u1(db), "میخوام هدف انگشتر طلا بسازم"
    ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1

def test_existing_active_goal_with_prefix_variant_prevents_duplicate(db):
    """Active goal 'انگشتر طلا' blocks insert of 'خرید انگشتر طلا' with same amount."""
    db.add(Goal(user_id=1, title="انگشتر طلا", target_amount=100_000_000,
                current_amount=0, is_active=True, status="active"))
    db.commit()
    plan = AgentPlan(
        intent="goal_create",
        requires_db=True,
        steps=[_goal_step("خرید انگشتر طلا", 100_000_000)],
        final_response_hint="هدف ثبت شد.",
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, u1(db), "میخوام هدف انگشتر طلا بسازم"
    ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1

def test_existing_active_goal_response_mentions_already_exists(db):
    """When a duplicate goal is blocked, the response must say it already exists."""
    db.add(Goal(user_id=1, title="انگشتر طلا", target_amount=100_000_000,
                current_amount=0, is_active=True, status="active"))
    db.commit()
    plan = AgentPlan(
        intent="goal_create",
        requires_db=True,
        steps=[_goal_step("انگشتر طلا", 100_000_000)],
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, u1(db), "میخوام هدف انگشتر طلا بسازم"
    ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1
    # Response must not claim success — must say already exists
    assert "قبلاً" in result.message or "وجود دارد" in result.message


# ── Section 6: Different goals are NOT falsely deduped ───────────────────────

def test_different_goals_not_falsely_deduped(db):
    """'انگشتر طلا' and 'سکه طلا' are different goals — both must be inserted."""
    db.add(Goal(user_id=1, title="انگشتر طلا", target_amount=100_000_000,
                current_amount=0, is_active=True, status="active"))
    db.commit()
    plan = AgentPlan(
        intent="goal_create",
        requires_db=True,
        steps=[_goal_step("سکه طلا", 80_000_000)],
        final_response_hint="هدف ثبت شد.",
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, u1(db), "میخوام هدف سکه طلا بسازم"
    ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 2

def test_same_title_different_amount_allowed(db):
    """Same normalized title but different target_amount should NOT be deduped."""
    db.add(Goal(user_id=1, title="انگشتر طلا", target_amount=100_000_000,
                current_amount=0, is_active=True, status="active"))
    db.commit()
    # Different amount — this is a new goal
    plan = AgentPlan(
        intent="goal_create",
        requires_db=True,
        steps=[_goal_step("انگشتر طلا", 50_000_000)],
        final_response_hint="هدف ثبت شد.",
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, u1(db), "میخوام هدف انگشتر طلا بسازم ۵۰ میلیون"
    ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 2


# ── Section 7: User-scoping ───────────────────────────────────────────────────

def test_two_users_can_create_same_goal_independently(db):
    """Different users must be able to create goals with the same title independently."""
    step = _goal_step("انگشتر طلا", 100_000_000)
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    executor = SqlExecutor()
    r1 = executor.execute(db, u1(db), step, validation, "goal", set())
    r2 = executor.execute(db, u2(db), step, validation, "goal", set())
    assert r1.executed
    assert r2.executed
    assert not r2.skipped_duplicate
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1
    assert db.query(Goal).filter(Goal.user_id == 2).count() == 1


# ── Section 8: Executor-level semantic dedup ─────────────────────────────────

def test_executor_skips_goal_insert_when_active_goal_exists(db):
    """SqlExecutor._check_semantic_goal_duplicate must block the insert."""
    db.add(Goal(user_id=1, title="لپتاپ", target_amount=80_000_000,
                current_amount=0, is_active=True, status="active"))
    db.commit()
    step = _goal_step("خرید لپتاپ", 80_000_000)
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, u1(db), step, validation, "goal", set())
    assert not result.executed
    assert result.skipped_duplicate
    assert result.existing_record_id is not None
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1

def test_executor_allows_goal_insert_when_no_active_goal_exists(db):
    step = _goal_step("انگشتر طلا", 100_000_000)
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, u1(db), step, validation, "goal", set())
    assert result.executed
    assert not result.skipped_duplicate
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1


# ── Section 9: Goal vs commitment regression ─────────────────────────────────

def test_goal_vs_commitment_chat_message_creates_goal_only(db):
    """'میخوام بخرم' must create a goal, not a future commitment, and only one row."""
    plan = AgentPlan(
        intent="goal_creation",
        requires_db=True,
        steps=[_goal_step("انگشتر طلا", 100_000_000, deadline="آخر سال")],
        final_response_hint="هدف خرید انگشتر طلا با مبلغ ۱۰۰ میلیون ثبت شد.",
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, u1(db), "میخوام یک هدف برای خرید انگشتر طلا بسازم به مبلغ ۱۰۰ میلیون تا آخر سال"
    ))
    assert db.query(Goal).filter(Goal.user_id == 1).count() == 1
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 0
    goal = db.query(Goal).filter(Goal.user_id == 1).first()
    assert goal.target_amount == 100_000_000
    assert goal.status == "active"


# ── Section 10: Expense and commitment inserts still work ────────────────────

def test_expense_insert_still_works_after_idempotency_fix(db):
    plan = AgentPlan(
        intent="expense",
        requires_db=True,
        steps=[AgentPlanStep(
            step_id="t1",
            operation_type=AgentOperationType.insert,
            purpose="record expense",
            table_name="transactions",
            sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
            params={"amount": 50_000, "type": "expense", "description": "taxi", "date": local_today().isoformat()},
            source_scope=SourceScope.current_message,
        )],
        final_response_hint="ثبت شد.",
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, u1(db), "50 هزار تومان تاکسی"
    ))
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 1

def test_future_commitment_insert_still_works(db):
    plan = AgentPlan(
        intent="commitment",
        requires_db=True,
        steps=[AgentPlanStep(
            step_id="c1",
            operation_type=AgentOperationType.insert,
            purpose="record commitment",
            table_name="future_commitments",
            sql="INSERT INTO future_commitments (title, amount, status, source) VALUES (:title, :amount, :status, :source)",
            params={"title": "چک ماه بعد", "amount": 50_000_000, "status": "pending", "source": "chat"},
            source_scope=SourceScope.current_message,
        )],
        final_response_hint="تعهد ثبت شد.",
    )
    asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, u1(db), "چک دارم ماه بعد ۵۰ میلیون"
    ))
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1).count() == 1


# ── Section 11: Chat and stream endpoints ────────────────────────────────────

def test_chat_message_endpoint_does_not_double_create_goal(db, monkeypatch):
    """Each call to /chat/message must invoke orchestrator exactly once."""
    call_count = 0

    class CountingOrchestrator:
        async def run(self, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return AgentFinalResponse(message="هدف ثبت شد.", metadata={})

    monkeypatch.setattr(chat_router, "orchestrator", CountingOrchestrator())

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: u1(db)
    client = TestClient(app)
    try:
        response = client.post("/api/v1/chat/message", json={"content": "هدف انگشتر طلا"})
        assert response.status_code == 200
        assert call_count == 1, "orchestrator must be called exactly once per /chat/message"
    finally:
        app.dependency_overrides.clear()

def test_chat_stream_endpoint_does_not_double_create_goal(db, monkeypatch):
    """Each call to /chat/stream must invoke orchestrator exactly once."""
    call_count = 0

    class CountingOrchestrator:
        async def run(self, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return AgentFinalResponse(message="هدف ثبت شد.", metadata={})

    monkeypatch.setattr(chat_router, "orchestrator", CountingOrchestrator())

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: u1(db)
    client = TestClient(app)
    try:
        response = client.get("/api/v1/chat/stream", params={"content": "هدف انگشتر طلا"})
        assert response.status_code == 200
        assert call_count == 1, "orchestrator must be called exactly once per /chat/stream"
    finally:
        app.dependency_overrides.clear()


# ── Section 12: Security regression ─────────────────────────────────────────

def test_drop_table_still_rejected_after_idempotency_fix(db):
    plan = AgentPlan(
        intent="unsafe",
        requires_db=True,
        steps=[AgentPlanStep(
            step_id="bad",
            operation_type=AgentOperationType.select,
            purpose="drop",
            table_name="users",
            sql="DROP TABLE users",
            params={},
        )],
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, u1(db), "DROP TABLE users"
    ))
    assert "امن" in result.message

def test_no_sql_json_leak_in_duplicate_blocked_response(db):
    """When a goal duplicate is blocked, the response must not contain SQL or JSON."""
    db.add(Goal(user_id=1, title="انگشتر طلا", target_amount=100_000_000,
                current_amount=0, is_active=True, status="active"))
    db.commit()
    plan = AgentPlan(
        intent="goal_create",
        requires_db=True,
        steps=[_goal_step("انگشتر طلا", 100_000_000)],
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(
        db, u1(db), "میخوام هدف انگشتر طلا بسازم"
    ))
    assert "SELECT" not in result.message
    assert "INSERT" not in result.message
    assert "{" not in result.message
