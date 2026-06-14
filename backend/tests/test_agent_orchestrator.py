from __future__ import annotations

import asyncio
import inspect
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import AdminUser, AgentSqlAuditLog, BehaviorInsight, Budget, Category, FinancialFact, FinancialMemory, FutureCommitment, Goal, Transaction, User
from app.models.transaction import TransactionType
from app.routers import chat as chat_router
from app.services.agent_orchestrator.db_world import build_db_world
from app.services.agent_orchestrator.date_utils import local_month_range, local_today, parse_relative_date
from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
from app.services.agent_orchestrator.planner import AgentPlanner
from app.services.agent_orchestrator.sql_executor import SqlExecutor
from app.services.agent_orchestrator.sql_validator import SqlValidator
from app.services.agent_orchestrator.types import AgentFinalResponse, AgentOperationType, AgentPlan, AgentPlanStep
from app.services.agent_orchestrator.value_normalizer import normalize_amount
from app.services.ai import LLMProviderConfigError, OllamaProvider, OpenAIProvider, get_llm_provider, resolve_ai_provider


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
            AdminUser(username="admin", hashed_password="secret"),
            Category(id=1, name="Food", icon="f", color="#111", is_default=True),
            Category(id=2, name="Transport", icon="t", color="#222", is_default=True),
            Category(id=3, name="Private", icon="p", color="#333", is_default=False, user_id=2),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def user(db):
    return db.query(User).filter(User.id == 1).first()


class SequencePlanner:
    def __init__(self, plans):
        self.plans = list(plans)
        self.calls = 0

    async def plan(self, *args, **kwargs):
        self.calls += 1
        if self.plans:
            return self.plans.pop(0)
        return AgentPlan(intent="final", final_response_hint="ثبت شد.")


class RecordingPlanner(SequencePlanner):
    def __init__(self, plans):
        super().__init__(plans)
        self.kwargs = []

    async def plan(self, *args, **kwargs):
        self.kwargs.append(kwargs)
        return await super().plan(*args, **kwargs)


def test_db_world_exposes_only_allowed_tables_and_columns(db):
    world = build_db_world(db.bind)
    tables = {table.table_name: table for table in world.tables}
    assert {"categories", "transactions", "budgets", "goals", "users"}.issubset(tables)
    assert "admin_users" not in tables
    assert "agent_sql_audit_logs" not in tables
    assert {"financial_memories", "financial_facts", "behavior_insights"}.issubset(tables)
    assert "persona_update_logs" not in tables
    user_columns = {col.name for col in tables["users"].columns}
    assert "phone" not in user_columns
    assert "is_blocked" not in user_columns
    goal_ops = {op.value for op in tables["goals"].allowed_operations}
    assert {"select", "insert", "update"}.issubset(goal_ops)
    assert "status" in {col.name for col in tables["goals"].columns}
    assert "future_commitments" in tables
    commitment_ops = {op.value for op in tables["future_commitments"].allowed_operations}
    assert {"select", "insert", "update"}.issubset(commitment_ops)
    fact_ops = {op.value for op in tables["financial_facts"].allowed_operations}
    memory_ops = {op.value for op in tables["financial_memories"].allowed_operations}
    assert {"select", "insert", "update"}.issubset(fact_ops)
    assert {"select", "insert", "update"}.issubset(memory_ops)


def test_ai_provider_openai_with_api_key_selects_openai(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-test")
    provider = get_llm_provider()
    assert isinstance(provider, OpenAIProvider)
    assert resolve_ai_provider() == ("openai", "gpt-test")


def test_ai_provider_openai_without_api_key_fails_clearly(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-test")
    with pytest.raises(LLMProviderConfigError, match="OPENAI_API_KEY"):
        get_llm_provider()


def test_ai_provider_ollama_selects_ollama(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "gpt-oss:20b")
    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)
    assert resolve_ai_provider() == ("ollama", "gpt-oss:20b")


def test_missing_ai_provider_with_openai_api_key_selects_openai(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-test")
    provider = get_llm_provider()
    assert isinstance(provider, OpenAIProvider)
    assert resolve_ai_provider() == ("openai", "gpt-test")


def test_missing_ai_provider_without_openai_api_key_selects_default_ollama(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "")
    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://localhost:11434"
    assert provider.model == "gpt-oss:20b"


def test_openai_key_alias_is_ignored(monkeypatch):
    monkeypatch.setenv("OPENAI" + "_KEY", "sk-ignored")
    monkeypatch.setattr(settings, "AI_PROVIDER", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "gpt-oss:20b")
    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)


def test_legacy_provider_is_never_selected(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "open" + "claw")
    with pytest.raises(LLMProviderConfigError, match="AI_PROVIDER"):
        get_llm_provider()


def test_no_legacy_provider_runtime_symbols_in_ai_service():
    import app.services.ai as ai

    source = inspect.getsource(ai).lower()
    legacy_provider = "open" + "claw"
    assert legacy_provider not in source
    assert "agents/main/chat" not in source


def _plan_json(intent: str = "mocked_provider") -> str:
    return json.dumps(
        {
            "intent": intent,
            "language": "fa",
            "reasoning_summary_for_backend_only": "mock",
            "requires_db": False,
            "steps": [],
            "final_response_hint": "پاسخ تست",
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )


def test_planner_can_use_mocked_openai_provider(monkeypatch):
    async def fake_completion(messages, require_json=False):
        assert require_json is True
        assert any("Safe DB World" in message["content"] for message in messages)
        return _plan_json("mocked_openai")

    import app.services.agent_orchestrator.planner as planner_module

    monkeypatch.setattr(planner_module, "get_ai_chat_completion", fake_completion)
    plan = asyncio.run(AgentPlanner().plan("tables", "لیست اهداف من و بده", {"user": {"id": 1}}))
    assert plan.intent == "mocked_openai"
    assert plan.final_response_hint == "پاسخ تست"


def test_planner_can_use_mocked_ollama_provider_with_json_extraction(monkeypatch):
    async def fake_completion(messages, require_json=False):
        assert require_json is True
        return "متن اضافه قبل از JSON\n" + _plan_json("mocked_ollama") + "\nمتن اضافه بعد از JSON"

    import app.services.agent_orchestrator.planner as planner_module

    monkeypatch.setattr(planner_module, "get_ai_chat_completion", fake_completion)
    plan = asyncio.run(AgentPlanner().plan("tables", "لیست اهداف من و بده", {"user": {"id": 1}}))
    assert plan.intent == "mocked_ollama"
    assert plan.final_response_hint == "پاسخ تست"


def test_invalid_ollama_json_triggers_repair(monkeypatch):
    calls = []

    async def fake_completion(messages, require_json=False):
        calls.append(messages)
        if len(calls) == 1:
            return "not json"
        assert messages[-1]["content"] == "Repair your previous answer. Return valid AgentPlan JSON only."
        return _plan_json("repaired_ollama")

    import app.services.agent_orchestrator.planner as planner_module

    monkeypatch.setattr(planner_module, "get_ai_chat_completion", fake_completion)
    plan = asyncio.run(AgentPlanner().plan("tables", "لیست اهداف من و بده", {"user": {"id": 1}}))
    assert plan.intent == "repaired_ollama"
    assert len(calls) == 2


def test_active_orchestrator_uses_selected_provider_through_planner(db, monkeypatch):
    async def fake_completion(messages, require_json=False):
        return _plan_json("selected_provider_path")

    import app.services.agent_orchestrator.planner as planner_module

    monkeypatch.setattr(planner_module, "get_ai_chat_completion", fake_completion)
    result = asyncio.run(AgentOrchestrator().run(db, user(db), "لیست اهداف من و بده"))
    assert result.message == "پاسخ تست"


def test_orchestrator_uses_planner_for_income_registration(db):
    plan = AgentPlan(
        intent="income_registration",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="i1",
                operation_type=AgentOperationType.insert,
                purpose="record income planned by LLM",
                table_name="transactions",
                sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
                params={"amount": 5_000_000, "type": "income", "description": "درآمد پروژه", "date": "2026-06-14"},
            )
        ],
    )
    planner = SequencePlanner([plan])
    result = asyncio.run(AgentOrchestrator(planner=planner).run(db, user(db), "امروز 5 میلیون درآمد پروژه گرفتم"))
    assert planner.calls >= 1
    assert "ثبت شد" in result.message
    txn = db.query(Transaction).filter(Transaction.user_id == 1, Transaction.type == TransactionType.income).first()
    assert txn is not None
    assert txn.amount == 5_000_000


def test_orchestrator_uses_planner_for_expense_registration(db):
    plans = [
        AgentPlan(
            intent="expense_registration",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="s1",
                    operation_type=AgentOperationType.select,
                    purpose="load categories",
                    table_name="categories",
                    sql="SELECT id, name FROM categories",
                    params={},
                )
            ],
        ),
        AgentPlan(
            intent="expense_registration",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="i1",
                    operation_type=AgentOperationType.insert,
                    purpose="record snap expense",
                    table_name="transactions",
                    sql="INSERT INTO transactions (category_id, amount, type, description, date) VALUES (:category_id, :amount, :type, :description, :date)",
                    params={"category_id": 2, "amount": 300_000, "type": "expense", "description": "اسنپ", "date": "2026-06-14"},
                )
            ],
        ),
    ]
    planner = SequencePlanner(plans)
    result = asyncio.run(AgentOrchestrator(planner=planner).run(db, user(db), "300 هزار پول اسنپ دادم"))
    assert planner.calls >= 2
    assert "ثبت شد" in result.message
    assert db.query(Transaction).filter(Transaction.user_id == 1, Transaction.type == TransactionType.expense).count() == 1


def test_multi_intent_income_and_expense_selects_are_composed(db):
    today = local_today()
    db.add_all(
        [
            Transaction(user_id=1, amount=900_000, type=TransactionType.expense, description="food", date=today),
            Transaction(user_id=1, amount=5_000_000, type=TransactionType.income, description="project", date=today),
        ]
    )
    db.commit()
    select_plan = AgentPlan(
        intent="monthly_income_and_expense",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="expense_total",
                operation_type=AgentOperationType.select,
                purpose="sum expense",
                table_name="transactions",
                sql="SELECT sum(amount) as total FROM transactions WHERE type = :type",
                params={"type": "expense"},
            ),
            AgentPlanStep(
                step_id="income_total",
                operation_type=AgentOperationType.select,
                purpose="sum income",
                table_name="transactions",
                sql="SELECT sum(amount) as total FROM transactions WHERE type = :type",
                params={"type": "income"},
            ),
        ],
    )
    final_plan = AgentPlan(intent="final", final_response_hint="[expense_total] [income_total]")
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([select_plan, final_plan])).run(db, user(db), "این ماه چقدر خرج کردم چقدر در آوردم"))
    assert "900,000" in result.message
    assert "5,000,000" in result.message
    assert "[" not in result.message


def test_top_category_select_uses_real_rows_not_placeholders(db):
    start, _ = local_month_range(previous=True)
    db.add(Transaction(user_id=1, category_id=1, amount=200_000, type=TransactionType.expense, description="food", date=start))
    db.commit()
    select_plan = AgentPlan(
        intent="top_expense_category",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="top",
                operation_type=AgentOperationType.select,
                purpose="top expense category",
                table_name="transactions",
                sql="SELECT category_id, sum(amount) as total FROM transactions WHERE type = :type GROUP BY category_id ORDER BY total DESC LIMIT 1",
                params={"type": "expense"},
            )
        ],
    )
    final_plan = AgentPlan(intent="final", final_response_hint="[name] [total_amount]")
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([select_plan, final_plan])).run(db, user(db), "بیشترین خرج ماه گذشته مربوط به چی بوده"))
    assert "Food" in result.message
    assert "200,000" in result.message
    assert "[" not in result.message


def test_income_visibility_and_totals_use_transaction_type(db):
    current_user = user(db)
    insert_step = AgentPlanStep(
        step_id="i1",
        operation_type=AgentOperationType.insert,
        purpose="record income",
        table_name="transactions",
        sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
        params={"amount": 5_000_000, "type": "income", "description": "project", "date": local_today().isoformat()},
    )
    validation = SqlValidator().validate(insert_step.operation_type, insert_step.table_name, insert_step.sql, insert_step.params)
    result = SqlExecutor().execute(db, current_user, insert_step, validation, "income_registration")
    assert result.executed
    visible = db.query(Transaction).filter(Transaction.user_id == 1, Transaction.type == TransactionType.income).all()
    assert len(visible) == 1
    assert visible[0].amount == 5_000_000
    total = db.query(func.sum(Transaction.amount)).filter(Transaction.user_id == 1, Transaction.type == TransactionType.income).scalar()
    assert total == 5_000_000


def test_persian_written_amount_and_relative_date_are_normalized(db):
    assert normalize_amount("چهل هزار تومن") == 40_000
    assert normalize_amount("چهارده میلیون تومان") == 14_000_000
    step = AgentPlanStep(
        step_id="i1",
        operation_type=AgentOperationType.insert,
        purpose="record project income with Persian values extracted by planner",
        table_name="transactions",
        sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
        params={"amount": "چهارده ملیون تومان", "type": "income", "description": "درآمد پروژه", "date": "سه روز پیش"},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "project_income")
    assert result.executed
    txn = db.query(Transaction).filter(Transaction.id == result.inserted_id).first()
    assert txn.amount == 14_000_000
    assert txn.type == TransactionType.income
    assert txn.date < local_today()


def test_category_select_is_scoped_to_default_and_current_user(db):
    step = AgentPlanStep(
        step_id="s1",
        operation_type=AgentOperationType.select,
        purpose="load visible categories",
        table_name="categories",
        sql="SELECT id, name, user_id FROM categories",
        params={},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "category_scope")
    names = {row["name"] for row in result.rows}
    assert "Private" not in names
    assert {"Food", "Transport"}.issubset(names)


def test_financial_fact_insert_is_user_scoped(db):
    step = AgentPlanStep(
        step_id="f1",
        operation_type=AgentOperationType.insert,
        purpose="store finance-relevant project income fact",
        table_name="financial_facts",
        sql="INSERT INTO financial_facts (fact_type, subject, value_json, confidence, valid_from) VALUES (:fact_type, :subject, :value_json, :confidence, :valid_from)",
        params={
            "fact_type": "project_income",
            "subject": "project payment",
            "value_json": {"amount": 14_000_000, "received": "سه روز پیش"},
            "confidence": 0.8,
            "valid_from": "سه روز پیش",
        },
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "project_income_memory")
    assert result.executed
    fact = db.query(FinancialFact).filter(FinancialFact.id == result.inserted_id).first()
    assert fact.user_id == 1
    assert fact.fact_type == "project_income"


def test_goal_insert_update_and_archive_are_policy_controlled(db):
    create_step = AgentPlanStep(
        step_id="g1",
        operation_type=AgentOperationType.insert,
        purpose="create home purchase goal",
        table_name="goals",
        sql="INSERT INTO goals (title, target_amount, current_amount, deadline, status) VALUES (:title, :target_amount, :current_amount, :deadline, :status)",
        params={"title": "home purchase", "target_amount": "12 میلیارد تومان", "current_amount": 0, "deadline": "یک سال بعد", "status": "active"},
    )
    validation = SqlValidator().validate(create_step.operation_type, create_step.table_name, create_step.sql, create_step.params)
    result = SqlExecutor().execute(db, user(db), create_step, validation, "goal_create")
    assert result.executed
    goal = db.query(Goal).filter(Goal.id == result.inserted_id).first()
    assert goal.user_id == 1
    assert goal.target_amount == 12_000_000_000
    assert goal.is_active is True

    update_step = AgentPlanStep(
        step_id="g2",
        operation_type=AgentOperationType.update,
        purpose="archive selected goal",
        table_name="goals",
        sql="UPDATE goals SET status = :status, is_active = :is_active WHERE id = :id",
        params={"status": "archived", "is_active": False, "id": goal.id},
    )
    update_validation = SqlValidator().validate(update_step.operation_type, update_step.table_name, update_step.sql, update_step.params)
    update_result = SqlExecutor().execute(db, user(db), update_step, update_validation, "goal_archive")
    assert update_result.executed
    db.refresh(goal)
    assert goal.status == "archived"
    assert goal.is_active is False


def test_goal_update_cannot_touch_another_user_goal(db):
    other_goal = Goal(user_id=2, title="other laptop", target_amount=10_000_000, current_amount=0)
    db.add(other_goal)
    db.commit()
    step = AgentPlanStep(
        step_id="g1",
        operation_type=AgentOperationType.update,
        purpose="update matched goal",
        table_name="goals",
        sql="UPDATE goals SET deadline = :deadline WHERE id = :id",
        params={"deadline": "یک سال بعد", "id": other_goal.id},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "goal_update_scope")
    assert result.executed is False
    assert "current user" in result.error


def test_tour_split_payment_creates_transaction_and_future_commitment(db):
    plans = [
        AgentPlan(
            intent="tour_split_payment",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="cats",
                    operation_type=AgentOperationType.select,
                    purpose="load real categories before choosing travel category",
                    table_name="categories",
                    sql="SELECT id, name FROM categories",
                    params={},
                )
            ],
        ),
        AgentPlan(
            intent="tour_split_payment",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="tx",
                    operation_type=AgentOperationType.insert,
                    purpose="record current paid part of tour",
                    table_name="transactions",
                    sql="INSERT INTO transactions (category_id, amount, type, description, date) VALUES (:category_id, :amount, :type, :description, :date)",
                    params={"category_id": 1, "amount": 30_000_000, "type": "expense", "description": "first tour payment", "date": local_today().isoformat()},
                ),
                AgentPlanStep(
                    step_id="commit",
                    operation_type=AgentOperationType.insert,
                    purpose="record next month unpaid tour balance",
                    table_name="future_commitments",
                    sql="INSERT INTO future_commitments (title, amount, due_date, description, status, source) VALUES (:title, :amount, :due_date, :description, :status, :source)",
                    params={"title": "remaining tour payment", "amount": 50_000_000, "due_date": "ماه بعد", "description": "tour balance due next month", "status": "pending", "source": "chat"},
                ),
            ],
        ),
        AgentPlan(intent="final", final_response_hint="ثبت شد. 30,000,000 تومان پرداخت فعلی تور ذخیره شد و 50,000,000 تومان تعهد ماه بعد ثبت شد."),
    ]
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner(plans)).run(db, user(db), "tour split payment"))
    assert "50,000,000" in result.message
    txn = db.query(Transaction).filter(Transaction.user_id == 1, Transaction.amount == 30_000_000).first()
    commitment = db.query(FutureCommitment).filter(FutureCommitment.user_id == 1, FutureCommitment.amount == 50_000_000).first()
    assert txn is not None
    assert commitment is not None
    assert commitment.status == "pending"


def test_emotional_spending_plan_queries_context_and_stores_insight(db):
    db.add(Budget(user_id=1, month=1, year=1405, amount=80_000_000))
    db.commit()
    plan = AgentPlan(
        intent="emotional_spending_advice",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="budget",
                operation_type=AgentOperationType.select,
                purpose="read current budget before recommending discretionary cap",
                table_name="budgets",
                sql="SELECT id, amount FROM budgets",
                params={},
            ),
            AgentPlanStep(
                step_id="goals",
                operation_type=AgentOperationType.select,
                purpose="read active goals before spending advice",
                table_name="goals",
                sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE is_active = :active",
                params={"active": True},
            ),
            AgentPlanStep(
                step_id="insight",
                operation_type=AgentOperationType.insert,
                purpose="store emotional spending signal",
                table_name="behavior_insights",
                sql="INSERT INTO behavior_insights (insight_type, evidence_json, confidence) VALUES (:insight_type, :evidence_json, :confidence)",
                params={"insight_type": "emotional_spending", "evidence_json": {"trigger": "sadness"}, "confidence": 0.8},
            ),
        ],
    )
    final_plan = AgentPlan(
        intent="final",
        final_response_hint="بهتر است برای خرج احساسی سقف کوچک و قابل کنترل بگذاری و خریدهای غیرضروری را 24 ساعت عقب بیندازی.",
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan, final_plan])).run(db, user(db), "emotional spending advice"))
    assert "چقدر میخواهی" not in result.message
    assert "24" in result.message
    insight = db.query(BehaviorInsight).filter(BehaviorInsight.user_id == 1, BehaviorInsight.insight_type == "emotional_spending").first()
    assert insight is not None


def test_laptop_goal_deadline_update_is_planner_driven(db):
    goal = Goal(user_id=1, title="laptop purchase", target_amount=80_000_000, current_amount=20_000_000)
    db.add(goal)
    db.commit()
    plans = [
        AgentPlan(
            intent="update_goal_deadline",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="goals",
                    operation_type=AgentOperationType.select,
                    purpose="load goals before fuzzy matching laptop",
                    table_name="goals",
                    sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE is_active = :active",
                    params={"active": True},
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
                    params={"deadline": "یک سال بعد", "id": goal.id},
                )
            ],
        ),
        AgentPlan(intent="final", final_response_hint="مهلت هدف خرید لپتاپ به یک سال بعد تغییر کرد."),
    ]
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner(plans)).run(db, user(db), "update laptop goal"))
    db.refresh(goal)
    assert goal.deadline == parse_relative_date("یک سال بعد")
    assert "یک سال" in result.message


def test_future_commitments_are_in_agent_context(db):
    db.add(FutureCommitment(user_id=1, title="next month tour balance", amount=50_000_000, status="pending"))
    db.commit()
    from app.services.agent_orchestrator.context_builder import build_agent_context

    context = build_agent_context(user(db), db)
    assert context["future_commitments"][0]["amount"] == 50_000_000
    assert context["personal_cfo"]["future_commitments"][0]["amount"] == 50_000_000
    assert "commitments_until_next_year" in context["personal_cfo"]


def test_future_plan_question_can_select_goals_commitments_facts_and_memories(db):
    db.add_all(
        [
            Goal(user_id=1, title="laptop", target_amount=80_000_000, current_amount=20_000_000, is_active=True),
            FutureCommitment(user_id=1, title="tour balance", amount=40_000_000, status="pending"),
            FinancialFact(user_id=1, fact_type="planned_purchase", subject="ring", value_json={"amount": 12_000_000}),
            FinancialMemory(user_id=1, memory_type="planned_purchase", title="car ring", content_json={"period": "next_month"}),
        ]
    )
    db.commit()
    plan = AgentPlan(
        intent="future_plans_question",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="goals",
                operation_type=AgentOperationType.select,
                purpose="read active goals for future plan answer",
                table_name="goals",
                sql="SELECT id, title, target_amount, current_amount, deadline, status, is_active FROM goals WHERE is_active = :active",
                params={"active": True},
            ),
            AgentPlanStep(
                step_id="commitments",
                operation_type=AgentOperationType.select,
                purpose="read pending future commitments",
                table_name="future_commitments",
                sql="SELECT id, title, amount, due_date, due_month, status FROM future_commitments WHERE status = :status",
                params={"status": "pending"},
            ),
            AgentPlanStep(
                step_id="facts",
                operation_type=AgentOperationType.select,
                purpose="read planned-purchase facts",
                table_name="financial_facts",
                sql="SELECT id, fact_type, subject, value_json, confidence, valid_from, valid_to, is_active FROM financial_facts WHERE is_active = :active",
                params={"active": True},
            ),
            AgentPlanStep(
                step_id="memories",
                operation_type=AgentOperationType.select,
                purpose="read planned-purchase memories",
                table_name="financial_memories",
                sql="SELECT id, memory_type, title, content_json, confidence, is_active FROM financial_memories WHERE is_active = :active",
                params={"active": True},
            ),
        ],
    )
    final_plan = AgentPlan(intent="final", final_response_hint="یک هدف لپتاپ، تعهد تور، و برنامه خرید رینگ در داده‌های شما ثبت شده است.")
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan, final_plan])).run(db, user(db), "future plans"))
    assert "لپتاپ" in result.message
    assert "تور" in result.message
    assert db.query(AgentSqlAuditLog).filter(AgentSqlAuditLog.operation_type == "select").count() == 4


def test_planned_purchase_followup_creates_future_commitment_not_transaction(db):
    first_plan = AgentPlan(
        intent="planned_purchase_missing_amount",
        requires_db=False,
        clarification_question="برای این خرید آینده چه مبلغی در نظر داری؟",
    )
    first = asyncio.run(AgentOrchestrator(planner=SequencePlanner([first_plan])).run(db, user(db), "planned purchase next month"))
    assert "چه مبلغ" in first.message

    insert_plan = AgentPlan(
        intent="planned_purchase_amount_followup",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="commit",
                operation_type=AgentOperationType.insert,
                purpose="create future commitment from follow-up amount and prior planned purchase context",
                table_name="future_commitments",
                sql="INSERT INTO future_commitments (title, amount, due_date, description, status, source) VALUES (:title, :amount, :due_date, :description, :status, :source)",
                params={"title": "car ring planned purchase", "amount": 15_000_000, "due_date": "ماه بعد", "description": "planned purchase from chat follow-up", "status": "pending", "source": "chat"},
            )
        ],
    )
    planner = RecordingPlanner([insert_plan, AgentPlan(intent="final", final_response_hint="تعهد آینده خرید رینگ برای ماه بعد ثبت شد.")])
    history = [
        {"role": "user", "content": "I want to buy car rings next month"},
        {"role": "assistant", "content": "What amount do you plan for it?"},
    ]
    result = asyncio.run(AgentOrchestrator(planner=planner).run(db, user(db), "15 million toman", history=history))
    assert "تعهد آینده" in result.message
    assert db.query(FutureCommitment).filter(FutureCommitment.user_id == 1, FutureCommitment.amount == 15_000_000).count() == 1
    assert db.query(Transaction).filter(Transaction.user_id == 1).count() == 0
    assert planner.kwargs[0]["history"] == history


def test_mixed_pen_purchase_and_incomplete_transfer_records_only_pen(db):
    plan = AgentPlan(
        intent="mixed_purchase_and_transfer_context",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="tx",
                operation_type=AgentOperationType.insert,
                purpose="record completed pen expense only",
                table_name="transactions",
                sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
                params={"amount": 50_000, "type": "expense", "description": "pen", "date": local_today().isoformat()},
            ),
            AgentPlanStep(
                step_id="fact",
                operation_type=AgentOperationType.insert,
                purpose="store incomplete friend transfer context for clarification",
                table_name="financial_facts",
                sql="INSERT INTO financial_facts (fact_type, subject, value_json, confidence) VALUES (:fact_type, :subject, :value_json, :confidence)",
                params={"fact_type": "friend_transfer_context", "subject": "friend transfer", "value_json": {"needs_amount": True, "needs_type": True}, "confidence": 0.7},
            ),
        ],
    )
    final_plan = AgentPlan(intent="final", final_response_hint="هزینه خودکار ثبت شد. برای واریز به دوستت هنوز مبلغ و نوع آن مشخص نیست؛ هدیه، قرض یا بازپرداخت است؟")
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan, final_plan])).run(db, user(db), "mixed event"))
    assert "خودکار" in result.message
    assert "هدیه" in result.message
    assert db.query(Transaction).filter(Transaction.user_id == 1, Transaction.amount == 50_000).count() == 1
    assert db.query(FinancialFact).filter(FinancialFact.user_id == 1, FinancialFact.fact_type == "friend_transfer_context").count() == 1


def test_personal_cfo_followup_can_answer_without_generic_failure(db):
    plan = AgentPlan(
        intent="financial_status_followup",
        requires_db=False,
        final_response_hint="اوضاع نیاز به کنترل دارد، اما قابل مدیریت است. چون بودجه منفی شده، فعلا خرج‌های اختیاری را کم کن و تعهدات ماه بعد را نگه دار.",
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(db, user(db), "status follow-up"))
    assert "قابل مدیریت" in result.message
    assert "نتوانستم" not in result.message


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE users",
        "DELETE FROM transactions",
        "ALTER TABLE users ADD COLUMN x int",
        "SELECT id FROM categories; SELECT id FROM users",
        "PRAGMA table_info(users)",
        "ATTACH DATABASE 'x' AS x",
        "VACUUM",
    ],
)
def test_validator_rejects_unsafe_sql(sql):
    result = SqlValidator().validate(AgentOperationType.select, "categories", sql, {})
    assert not result.allowed


def test_validator_rejects_forbidden_access_and_llm_user_id():
    validator = SqlValidator()
    assert not validator.validate(AgentOperationType.select, "admin_users", "SELECT id FROM admin_users", {}).allowed
    assert not validator.validate(
        AgentOperationType.insert,
        "transactions",
        "INSERT INTO transactions (user_id, amount, type) VALUES (:user_id, :amount, :type)",
        {"user_id": 99, "amount": 1000, "type": "expense"},
    ).allowed


def test_executor_scopes_selects_to_authenticated_user(db):
    db.add(Transaction(user_id=2, category_id=1, amount=999_999, type=TransactionType.expense, description="other"))
    db.commit()
    step = AgentPlanStep(
        step_id="s1",
        operation_type=AgentOperationType.select,
        purpose="read transactions",
        table_name="transactions",
        sql="SELECT id, amount FROM transactions",
        params={},
    )
    validation = SqlValidator().validate(step.operation_type, step.table_name, step.sql, step.params)
    result = SqlExecutor().execute(db, user(db), step, validation, "scope_test")
    assert result.rows == []


def test_unsafe_planner_output_rejected_and_audited(db):
    plan = AgentPlan(
        intent="unsafe",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="bad",
                operation_type=AgentOperationType.select,
                purpose="bad",
                table_name="users",
                sql="DROP TABLE users",
                params={},
            )
        ],
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(db, user(db), "DROP TABLE users;"))
    assert "امن" in result.message
    audit = db.query(AgentSqlAuditLog).first()
    assert audit.validation_status == "rejected"
    assert audit.executed is False


def test_chat_endpoint_and_stream_return_clean_text(db, monkeypatch):
    class FakeOrchestrator:
        calls = 0

        async def run(self, *args, **kwargs):
            self.calls += 1
            return AgentFinalResponse(message="ثبت شد. هزینه تاکسی ذخیره شد.", metadata={})

    fake = FakeOrchestrator()
    monkeypatch.setattr(chat_router, "orchestrator", fake)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user(db)
    client = TestClient(app)
    try:
        response = client.post("/api/v1/chat/message", json={"content": "سلام"})
        assert response.status_code == 200
        assert response.json()["reply"] == "ثبت شد. هزینه تاکسی ذخیره شد."
        stream = client.get("/api/v1/chat/stream", params={"content": "سلام"})
        assert stream.status_code == 200
        body = stream.text
        assert "ثبت شد" in body
        assert "SELECT" not in body
        assert "```json" not in body
        assert "{" not in response.json()["reply"]
    finally:
        app.dependency_overrides.clear()


def test_no_deterministic_planners_in_active_orchestrator():
    import app.services.agent_orchestrator.orchestrator as orchestrator_module

    source = inspect.getsource(orchestrator_module)
    assert ("build_" + "aggregate_plan") not in source
    assert ("build_" + "transaction_plan") not in source
    assert ("deterministic_" + "plans") not in source
    assert "CATEGORY_HINTS" not in source
    assert "process_ai_reply" not in source


def test_timezone_relative_date_parsing(monkeypatch):
    monkeypatch.setattr(settings, "APP_TIMEZONE", "Asia/Tehran")
    assert parse_relative_date("امروز") == local_today()
    assert parse_relative_date("دیروز").isoformat() < parse_relative_date("امروز").isoformat()
