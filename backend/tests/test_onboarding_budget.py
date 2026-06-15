from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.jalali import current_jalali_month
from app.db import Base, get_db
from app.main import app
from app.models import Category, User
from app.models.budget import Budget
from app.services.income_range import income_range_max_toman
from app.services.onboarding_budget import initialize_budget_from_income_range


def _session():
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
            User(id=1, phone="09120000001", name="Test", language="fa", income_range="40to80"),
            User(id=2, phone="09120000002", name="Other", language="fa", income_range="20to40"),
            Category(id=1, name="Transport", icon="t", color="#111", is_default=True),
        ]
    )
    session.commit()
    return session


def _user(db, user_id: int = 1) -> User:
    return db.query(User).filter(User.id == user_id).first()


def test_income_range_code_40_to_80_uses_maximum():
    assert income_range_max_toman("40to80") == 80_000_000


def test_income_range_persian_digits_uses_largest_number_as_millions():
    assert income_range_max_toman("۴۰ تا ۸۰ میلیون") == 80_000_000


def test_income_range_english_digits_uses_largest_number_as_millions():
    assert income_range_max_toman("40 تا 80 میلیون") == 80_000_000


def test_income_range_structured_max_wins():
    assert (
        income_range_max_toman(
            payload={"income_range_min": 40_000_000, "income_range_max": 80_000_000}
        )
        == 80_000_000
    )


def test_income_range_20_to_40_uses_40_million():
    assert income_range_max_toman("۲۰ تا ۴۰ میلیون") == 40_000_000


def test_complete_onboarding_creates_budget_from_income_range_max():
    db = _session()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: _user(db)
    client = TestClient(app)
    try:
        response = client.post("/api/v1/onboarding/complete")
        assert response.status_code == 200
        month, year = current_jalali_month()
        budget = db.query(Budget).filter(Budget.user_id == 1, Budget.month == month, Budget.year == year).one()
        assert budget.amount == 80_000_000
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_onboarding_complete_twice_does_not_create_duplicate_budget_rows():
    db = _session()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: _user(db)
    client = TestClient(app)
    try:
        assert client.post("/api/v1/onboarding/complete").status_code == 200
        assert client.post("/api/v1/onboarding/complete").status_code == 200
        month, year = current_jalali_month()
        budgets = db.query(Budget).filter(Budget.user_id == 1, Budget.month == month, Budget.year == year).all()
        assert len(budgets) == 1
        assert budgets[0].amount == 80_000_000
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_completed_user_existing_custom_budget_is_not_overwritten():
    db = _session()
    user = _user(db)
    user.onboarding_completed = True
    month, year = current_jalali_month()
    db.add(Budget(user_id=1, month=month, year=year, amount=12_345_678))
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: _user(db)
    client = TestClient(app)
    try:
        response = client.post("/api/v1/onboarding/complete")
        assert response.status_code == 200
        budget = db.query(Budget).filter(Budget.user_id == 1, Budget.month == month, Budget.year == year).one()
        assert budget.amount == 12_345_678
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_first_onboarding_completion_updates_existing_zero_budget():
    db = _session()
    month, year = current_jalali_month()
    db.add(Budget(user_id=1, month=month, year=year, amount=0))
    db.commit()

    initialize_budget_from_income_range(db, _user(db))
    db.commit()

    budgets = db.query(Budget).filter(Budget.user_id == 1, Budget.month == month, Budget.year == year).all()
    assert len(budgets) == 1
    assert budgets[0].amount == 80_000_000
    db.close()


def test_budget_initialization_is_user_scoped():
    db = _session()
    initialize_budget_from_income_range(db, _user(db, 2))
    db.commit()
    month, year = current_jalali_month()

    assert db.query(Budget).filter(Budget.user_id == 1, Budget.month == month, Budget.year == year).count() == 0
    budget = db.query(Budget).filter(Budget.user_id == 2, Budget.month == month, Budget.year == year).one()
    assert budget.amount == 40_000_000
    db.close()
