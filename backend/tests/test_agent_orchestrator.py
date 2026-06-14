from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.main import app
from app.models import (
    AdminUser,
    AgentSqlAuditLog,
    Category,
    Transaction,
    User,
)
from app.models.transaction import TransactionType
from app.models.billing import TokenPurchase, TokenUsageLog, TokenWallet, UserSubscription
from app.core.auth import get_current_user
from app.db import get_db
from app.routers import chat as chat_router
from app.services.agent_orchestrator.db_world import build_db_world
from app.services.agent_orchestrator.date_utils import local_month_range, local_today, parse_relative_date
from app.services.agent_orchestrator.orchestrator import AgentOrchestrator
from app.services.agent_orchestrator.sql_executor import SqlExecutor
from app.services.agent_orchestrator.sql_validator import SqlValidator
from app.services.agent_orchestrator.types import AgentFinalResponse, AgentOperationType, AgentPlan, AgentPlanStep
from app.services.ai import resolve_ai_provider
from app.core.config import settings
from app.models.personal_cfo import BehaviorInsight, FinancialMemory, FinancialPersona
from app.services.personal_cfo.behavior_service import detect_basic_behavior_signals
from app.services.personal_cfo.memory_service import create_memory
from app.services.personal_cfo.persona_service import get_or_create_persona


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
    user = User(id=1, phone="09120000001", name="Test", language="fa", chat_mode="normal")
    other = User(id=2, phone="09120000002", name="Other", language="fa")
    session.add_all(
        [
            user,
            other,
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


def test_db_world_exposes_only_allowed_tables_and_columns(db):
    world = build_db_world(db.bind)
    tables = {table.table_name: table for table in world.tables}
    assert {"categories", "transactions", "budgets", "goals", "users"}.issubset(tables)
    assert "admin_users" not in tables
    assert "activity_logs" not in tables
    assert "agent_sql_audit_logs" not in tables
    user_columns = {col.name for col in tables["users"].columns}
    assert "hashed_password" not in user_columns
    assert "phone" not in user_columns
    assert "is_blocked" not in user_columns


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


def test_validator_rejects_read_only_and_forbidden_access():
    validator = SqlValidator()
    category_insert = validator.validate(
        AgentOperationType.insert,
        "categories",
        "INSERT INTO categories (name) VALUES (:name)",
        {"name": "Bad"},
    )
    assert not category_insert.allowed

    admin_select = validator.validate(
        AgentOperationType.select,
        "admin_users",
        "SELECT id FROM admin_users",
        {},
    )
    assert not admin_select.allowed

    user_id_insert = validator.validate(
        AgentOperationType.insert,
        "transactions",
        "INSERT INTO transactions (user_id, amount, type) VALUES (:user_id, :amount, :type)",
        {"user_id": 99, "amount": 1000, "type": "expense"},
    )
    assert not user_id_insert.allowed


def test_executor_injects_user_id_and_scopes_selects(db):
    validator = SqlValidator()
    executor = SqlExecutor()
    current_user = user(db)
    db.add(Transaction(user_id=2, category_id=1, amount=999999, type=TransactionType.expense, description="other"))
    db.commit()

    insert_step = AgentPlanStep(
        step_id="i1",
        operation_type=AgentOperationType.insert,
        purpose="insert expense",
        table_name="transactions",
        sql="INSERT INTO transactions (category_id, amount, type, description, date) VALUES (:category_id, :amount, :type, :description, :date)",
        params={"category_id": 2, "amount": 120000, "type": "expense", "description": "taxi", "date": "2026-06-14"},
    )
    validation = validator.validate(insert_step.operation_type, insert_step.table_name, insert_step.sql, insert_step.params)
    result = executor.execute(db, current_user, insert_step, validation, "expense_registration")
    assert result.executed
    txn = db.query(Transaction).filter(Transaction.id == result.inserted_id).first()
    assert txn.user_id == 1

    select_step = AgentPlanStep(
        step_id="s1",
        operation_type=AgentOperationType.select,
        purpose="read transactions",
        table_name="transactions",
        sql="SELECT id, amount FROM transactions",
        params={},
    )
    validation = validator.validate(select_step.operation_type, select_step.table_name, select_step.sql, select_step.params)
    result = executor.execute(db, current_user, select_step, validation, "spending_question")
    assert {row["amount"] for row in result.rows} == {120000}


class SequencePlanner:
    def __init__(self, plans):
        self.plans = list(plans)

    async def plan(self, *args, **kwargs):
        return self.plans.pop(0)


def test_mocked_expense_select_categories_then_insert(db):
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
                    confidence=0.9,
                )
            ],
            confidence=0.9,
        ),
        AgentPlan(
            intent="expense_registration",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="i1",
                    operation_type=AgentOperationType.insert,
                    purpose="record taxi",
                    table_name="transactions",
                    sql="INSERT INTO transactions (category_id, amount, type, description, date) VALUES (:category_id, :amount, :type, :description, :date)",
                    params={"category_id": 2, "amount": 100000, "type": "expense", "description": "taxi", "date": "2026-06-14"},
                    confidence=0.92,
                )
            ],
            confidence=0.92,
        ),
    ]
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner(plans)).run(db, user(db), "امروز هزار تومان تاکسی دادم"))
    assert "ثبت شد" in result.message
    assert db.query(Transaction).filter(Transaction.user_id == 1, Transaction.amount == 100000).count() == 1


def test_mocked_income_registration(db):
    plan = AgentPlan(
        intent="income_registration",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="i1",
                operation_type=AgentOperationType.insert,
                purpose="record income",
                table_name="transactions",
                sql="INSERT INTO transactions (amount, type, description, date) VALUES (:amount, :type, :description, :date)",
                params={"amount": 1000000, "type": "income", "description": "project", "date": "2026-06-14"},
            )
        ],
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(db, user(db), "امروز میلیون درآمد پروژه گرفتم"))
    assert "درآمد" in result.message
    assert db.query(Transaction).filter(Transaction.type == TransactionType.income, Transaction.user_id == 1).count() == 1


def test_finance_select_question_works(db):
    db.add(Transaction(user_id=1, category_id=1, amount=25000, type=TransactionType.expense, description="food"))
    db.commit()
    plan = AgentPlan(
        intent="monthly_spending",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="s1",
                operation_type=AgentOperationType.select,
                purpose="sum expenses",
                table_name="transactions",
                sql="SELECT sum(amount) as total FROM transactions WHERE type = :type",
                params={"type": "expense"},
            )
        ],
        final_response_hint="این ماه 25,000 تومان خرج کرده ای.",
    )
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan, plan])).run(db, user(db), "این ماه چقدر خرج کردم"))
    assert "25,000" in result.message


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
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([plan])).run(db, user(db), "unsafe"))
    assert "امن" in result.message
    audit = db.query(AgentSqlAuditLog).first()
    assert audit.validation_status == "rejected"
    assert audit.executed is False


def test_chat_endpoint_and_stream_return_clean_text(db, monkeypatch):
    class FakeOrchestrator:
        async def run(self, *args, **kwargs):
            return AgentFinalResponse(message="ثبت شد. هزینه تاکسی ذخیره شد.", metadata={})

    monkeypatch.setattr(chat_router, "orchestrator", FakeOrchestrator())

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user(db)
    client = TestClient(app)
    try:
        response = client.post("/api/v1/chat/message", json={"content": "سلام"})
        assert response.status_code == 200
        assert response.json()["reply"] == "ثبت شد. هزینه تاکسی ذخیره شد."
        assert "{" not in response.json()["reply"]
        assert "SELECT" not in response.json()["reply"]

        stream = client.get("/api/v1/chat/stream", params={"content": "سلام"})
        assert stream.status_code == 200
        body = stream.text
        assert "ثبت شد" in body
        assert "SELECT" not in body
        assert "```json" not in body
    finally:
        app.dependency_overrides.clear()


def test_provider_selection_prefers_openai_api_key(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "gpt-test")
    provider, model = resolve_ai_provider()
    assert provider == "openai"
    assert model == "gpt-test"


def test_provider_selection_ignores_openai_key_alias(monkeypatch):
    legacy_alias = "OPENAI" + "_KEY"
    monkeypatch.setenv(legacy_alias, "sk-ignored")
    monkeypatch.setattr(settings, "AI_PROVIDER", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "")
    monkeypatch.setattr(settings, "PRIMARY_MODEL", "plain-model")
    provider, _ = resolve_ai_provider()
    assert provider == "openclaw"


def test_provider_selection_allows_explicit_openclaw(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openclaw")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    provider, _ = resolve_ai_provider("plain-model")
    assert provider == "openclaw"


def test_deterministic_income_chat_creates_visible_income(db):
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([])).run(db, user(db), "امروز 5 میلیون پول پروژه گرفتم"))
    assert "ثبت شد" in result.message
    txn = db.query(Transaction).filter(Transaction.user_id == 1, Transaction.type == TransactionType.income).first()
    assert txn is not None
    assert txn.amount == 5_000_000
    assert txn.description == "درآمد پروژه"
    visible = db.query(Transaction).filter(Transaction.user_id == 1, Transaction.type == TransactionType.income).all()
    assert [row.id for row in visible] == [txn.id]


def test_weekly_income_response_is_deterministic_and_has_no_placeholder(db):
    db.add(Transaction(user_id=1, amount=5_000_000, type=TransactionType.income, description="project", date=local_today()))
    db.commit()
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([])).run(db, user(db), "این هفته چقدر درآمد داشتم"))
    assert "5,000,000" in result.message
    assert "[total_amount]" not in result.message
    assert "[" not in result.message


def test_previous_month_top_category_uses_real_rows(db):
    start, _ = local_month_range(previous=True)
    db.add(Transaction(user_id=1, category_id=1, amount=200_000, type=TransactionType.expense, description="food", date=start))
    db.commit()
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([])).run(db, user(db), "بیشترین خرج تو ماه گذشته مربوط به چی بوده"))
    assert "Food" in result.message
    assert "200,000" in result.message
    assert "[name]" not in result.message
    assert "[total_amount]" not in result.message


def test_no_data_top_category_has_clean_fallback(db):
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([])).run(db, user(db), "بیشترین خرج تو ماه گذشته مربوط به چی بوده"))
    assert "ثبت نشده" in result.message
    assert "[" not in result.message


def test_timezone_relative_date_parsing(monkeypatch):
    monkeypatch.setattr(settings, "APP_TIMEZONE", "Asia/Tehran")
    assert parse_relative_date("امروز") == local_today()
    assert parse_relative_date("دیروز").isoformat() < parse_relative_date("امروز").isoformat()


def test_user_scope_for_deterministic_totals(db):
    db.add(Transaction(user_id=2, amount=9_999_999, type=TransactionType.expense, description="other", date=local_today()))
    db.commit()
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([])).run(db, user(db), "این ماه چقدر خرج کردم"))
    assert "9,999,999" not in result.message
    assert "ثبت نشده" in result.message or "0" in result.message


def test_get_or_create_persona_is_one_per_user(db):
    first = get_or_create_persona(db, 1)
    second = get_or_create_persona(db, 1)
    assert first.id == second.id
    assert db.query(FinancialPersona).filter(FinancialPersona.user_id == 1).count() == 1


def test_memory_creation_is_user_scoped(db):
    memory = create_memory(db, 1, "preference", "test", {"value": "x"})
    assert memory.user_id == 1
    assert db.query(FinancialMemory).filter(FinancialMemory.user_id == 2).count() == 0


def test_stress_spending_phrase_creates_insight(db):
    detect_basic_behavior_signals(db, 1, "وقتی استرس دارم خرید میکنم", [])
    insight = db.query(BehaviorInsight).filter(BehaviorInsight.user_id == 1, BehaviorInsight.insight_type == "stress_spending").first()
    assert insight is not None
    memory = db.query(FinancialMemory).filter(FinancialMemory.user_id == 1, FinancialMemory.memory_type == "behavioral_trigger").first()
    assert memory is not None


def test_debt_fear_updates_persona_and_insight(db):
    detect_basic_behavior_signals(db, 1, "من از بدهی خیلی میترسم", [])
    persona = get_or_create_persona(db, 1)
    assert persona.debt_sensitivity == "high"
    assert db.query(BehaviorInsight).filter(BehaviorInsight.user_id == 1, BehaviorInsight.insight_type == "debt_anxiety").count() == 1


def test_end_of_month_shortage_creates_memory_or_insight(db):
    result = asyncio.run(AgentOrchestrator(planner=SequencePlanner([])).run(db, user(db), "من آخر ماه همیشه پول کم میارم"))
    assert "آخر ماه" in result.message
    assert db.query(BehaviorInsight).filter(BehaviorInsight.user_id == 1, BehaviorInsight.insight_type == "liquidity_pressure").count() == 1
    assert db.query(FinancialMemory).filter(FinancialMemory.user_id == 1).count() >= 1


def test_orchestrator_includes_personal_cfo_context(db):
    create_memory(db, 1, "preference", "test preference", {"value": "cash"})

    class CapturingPlanner:
        def __init__(self):
            self.context = None

        async def plan(self, db_world, user_message, finance_context, **kwargs):
            self.context = finance_context
            return AgentPlan(intent="noop", requires_db=False, steps=[], final_response_hint="باشه")

    planner = CapturingPlanner()
    asyncio.run(AgentOrchestrator(planner=planner).run(db, user(db), "سلام"))
    assert "personal_cfo" in planner.context
    assert planner.context["personal_cfo"]["memories"]


def test_personal_cfo_endpoints_are_user_scoped(db):
    create_memory(db, 2, "preference", "other", {"secret": "hidden"})

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user(db)
    client = TestClient(app)
    try:
        persona = client.get("/api/v1/personal-cfo/persona")
        assert persona.status_code == 200
        memories = client.get("/api/v1/personal-cfo/memories")
        assert memories.status_code == 200
        assert all(item["user_id"] == 1 for item in memories.json())
        insights = client.get("/api/v1/personal-cfo/behavior-insights")
        assert insights.status_code == 200
        assert all(item["user_id"] == 1 for item in insights.json())
    finally:
        app.dependency_overrides.clear()
