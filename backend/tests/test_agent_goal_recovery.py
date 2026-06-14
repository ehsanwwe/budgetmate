from __future__ import annotations

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import AgentSqlAuditLog, Category, FutureCommitment, Goal, Transaction, User
from app.models.transaction import TransactionType
from app.services.agent_orchestrator.date_utils import local_today, parse_relative_date
from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
from app.services.agent_orchestrator.sql_validator import SqlValidator
from app.services.agent_orchestrator.types import AgentOperationType, AgentPlan, AgentPlanStep
from app.services.personal_cfo.goal_context_service import find_goal_candidates, goal_match_score, normalize_goal_text


def make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    session.add_all(
        [
            User(id=1, phone="09120000001", name="Test", language="fa", chat_mode="normal"),
            User(id=2, phone="09120000002", name="Other", language="fa"),
            Category(id=1, name="Food", icon="f", color="#111", is_default=True),
        ]
    )
    session.commit()
    return session


def current_user(db):
    return db.query(User).filter(User.id == 1).first()


class SequencePlanner:
    def __init__(self, plans):
        self.plans = list(plans)
        self.calls = 0

    async def plan(self, *args, **kwargs):
        self.calls += 1
        if self.plans:
            return self.plans.pop(0)
        return AgentPlan(intent="final", final_response_hint="انجام شد.")


def test_goal_list_select_is_composed_from_real_rows_when_hint_is_generic():
    db = make_db()
    db.add(Goal(user_id=1, title="خرید لپ‌تاپ", target_amount=80_000_000, current_amount=20_000_000, is_active=True))
    db.commit()
    plan = AgentPlan(
        intent="goal_list",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="goals",
                operation_type=AgentOperationType.select,
                purpose="read active goals for goal list",
                table_name="goals",
                sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE is_active = :active",
                params={"active": True},
            )
        ],
    )
    final_plan = AgentPlan(intent="final", final_response_hint="نتوانستم این درخواست را به شکل امن انجام بدهم. لطفا درخواستت را ساده تر و دقیق تر بنویس.")
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan, final_plan])).run(db, current_user(db), "لیست اهداف من و بده"))
    assert "خرید لپ" in result.message
    assert "80,000,000" in result.message
    assert "60,000,000" in result.message
    assert "نتوانستم" not in result.message
    assert db.query(AgentSqlAuditLog).filter(AgentSqlAuditLog.table_name == "goals", AgentSqlAuditLog.operation_type == "select").count() == 1
    db.close()


def test_goal_timing_question_falls_back_to_goal_rows_not_generic_failure():
    db = make_db()
    db.add(Goal(user_id=1, title="خرید لپ‌تاپ", target_amount=100_000_000, current_amount=40_000_000, is_active=True))
    db.commit()
    plan = AgentPlan(
        intent="goal_timing",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="goals",
                operation_type=AgentOperationType.select,
                purpose="read goals before answering laptop goal timing",
                table_name="goals",
                sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE is_active = :active",
                params={"active": True},
            )
        ],
    )
    final_plan = AgentPlan(intent="final", final_response_hint="نتوانستم این درخواست را به شکل امن انجام بدهم. لطفا درخواستت را ساده تر و دقیق تر بنویس.")
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan, final_plan])).run(db, current_user(db), "لپتاپ باید کی بخرم؟"))
    assert "خرید لپ" in result.message
    assert "60,000,000" in result.message
    assert "نتوانستم" not in result.message
    db.close()


def test_goal_update_repairs_llm_user_id_scope_then_updates_deadline():
    db = make_db()
    goal = Goal(user_id=1, title="خرید لپ‌تاپ", target_amount=80_000_000, current_amount=20_000_000, is_active=True)
    db.add(goal)
    db.commit()
    invalid_plan = AgentPlan(
        intent="update_goal_deadline",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="bad_goals",
                operation_type=AgentOperationType.select,
                purpose="read goals before update but incorrectly includes user_id",
                table_name="goals",
                sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE user_id = :user_id",
                params={"user_id": 1},
            )
        ],
    )
    select_plan = AgentPlan(
        intent="update_goal_deadline",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="goals",
                operation_type=AgentOperationType.select,
                purpose="read goals before updating matched laptop goal",
                table_name="goals",
                sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE is_active = :active",
                params={"active": True},
            )
        ],
    )
    update_plan = AgentPlan(
        intent="update_goal_deadline",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="update",
                operation_type=AgentOperationType.update,
                purpose="update matched laptop goal deadline",
                table_name="goals",
                sql="UPDATE goals SET deadline = :deadline WHERE id = :id",
                params={"deadline": "یک سال بعد", "id": goal.id},
            )
        ],
    )
    final_plan = AgentPlan(intent="final", final_response_hint="نتوانستم این درخواست را به شکل امن انجام بدهم. لطفا درخواستت را ساده تر و دقیق تر بنویس.")
    planner = SequencePlanner([invalid_plan, select_plan, update_plan, final_plan])
    result = asyncio.run(AgentOrchestrator(planner=planner).run(db, current_user(db), "هدف لپتاپ من و بنداز یک سال دیر تر"))
    db.refresh(goal)
    assert planner.calls >= 4
    assert goal.deadline == parse_relative_date("یک سال بعد")
    assert "به‌روزرسانی شد" in result.message
    assert "نتوانستم" not in result.message
    rejected = db.query(AgentSqlAuditLog).filter(AgentSqlAuditLog.validation_status == "rejected").first()
    assert rejected is not None
    assert "user_id" in (rejected.rejected_reason or "")
    db.close()


def test_personal_cfo_advice_repairs_scoping_mistake_and_uses_clean_final():
    db = make_db()
    db.add(Transaction(user_id=1, category_id=1, amount=250_000, type=TransactionType.expense, description="snack", date=local_today()))
    db.add(FutureCommitment(user_id=1, title="tour", amount=5_000_000, status="pending"))
    db.commit()
    invalid_plan = AgentPlan(
        intent="reduce_discretionary_spending_advice",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="bad_expenses",
                operation_type=AgentOperationType.select,
                purpose="read spending categories but incorrectly includes user_id",
                table_name="transactions",
                sql="SELECT category_id, sum(amount) as total FROM transactions WHERE user_id = :user_id GROUP BY category_id",
                params={"user_id": 1},
            )
        ],
    )
    select_plan = AgentPlan(
        intent="reduce_discretionary_spending_advice",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="expenses",
                operation_type=AgentOperationType.select,
                purpose="read current spending by category for advice",
                table_name="transactions",
                sql="SELECT category_id, sum(amount) as total FROM transactions GROUP BY category_id",
                params={},
            ),
            AgentPlanStep(
                step_id="goals",
                operation_type=AgentOperationType.select,
                purpose="read active goals for spending advice",
                table_name="goals",
                sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE is_active = :active",
                params={"active": True},
            ),
            AgentPlanStep(
                step_id="commitments",
                operation_type=AgentOperationType.select,
                purpose="read future commitments for spending advice",
                table_name="future_commitments",
                sql="SELECT id, title, amount, due_date, due_month, status FROM future_commitments WHERE status = :status",
                params={"status": "pending"},
            ),
        ],
    )
    final_plan = AgentPlan(intent="final", final_response_hint="برای کم کردن هزینه‌های غیرضروری، اول خرج‌های اختیاری را سقف‌گذاری کن، خریدهای فوری را 24 ساعت عقب بینداز و هر هفته سه دسته پرخرج را مرور کن.")
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([invalid_plan, select_plan, final_plan])).run(db, current_user(db), "چطوری هزینه های غیر ضروری رو کم کنم؟"))
    assert "غیرضروری" in result.message
    assert "24" in result.message
    assert "نتوانستم" not in result.message
    db.close()


def test_goal_fuzzy_matching_supports_persian_laptop_variants():
    db = make_db()
    db.add_all(
        [
            Goal(user_id=1, title="خرید لپ‌تاپ", target_amount=80_000_000, current_amount=0, is_active=True),
            Goal(user_id=1, title="خرید خانه", target_amount=1_000_000_000, current_amount=0, is_active=True),
        ]
    )
    db.commit()
    assert normalize_goal_text("لپ تاب") == "لپتاپ"
    assert goal_match_score("هدف لپباپ من", "خرید لپ‌تاپ") > goal_match_score("هدف لپباپ من", "خرید خانه")
    candidates = find_goal_candidates(db, 1, "هدف لپتاب من")
    assert candidates
    assert candidates[0].title == "خرید لپ‌تاپ"
    db.close()


def test_goal_fuzzy_matching_does_not_match_unrelated_goal():
    db = make_db()
    db.add(Goal(user_id=1, title="خرید خانه", target_amount=1_000_000_000, current_amount=0, is_active=True))
    db.commit()
    assert find_goal_candidates(db, 1, "لپتاپ") == []
    db.close()


def test_controlled_goal_update_validation_rules():
    validator = SqlValidator()
    allowed = validator.validate(
        AgentOperationType.update,
        "goals",
        "UPDATE goals SET deadline = :deadline WHERE id = :id",
        {"deadline": "یک سال بعد", "id": 1},
    )
    assert allowed.allowed
    assert not validator.validate(
        AgentOperationType.update,
        "goals",
        "UPDATE goals SET user_id = :user_id WHERE id = :id",
        {"user_id": 2, "id": 1},
    ).allowed
    assert not validator.validate(
        AgentOperationType.update,
        "users",
        "UPDATE users SET name = :name WHERE id = :id",
        {"name": "bad", "id": 1},
    ).allowed
    assert not validator.validate(
        AgentOperationType.update,
        "goals",
        "UPDATE goals SET title = :title",
        {"title": "bad"},
    ).allowed
