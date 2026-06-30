from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.db import Base, get_db
from app.main import app
from app.models.user import User
from app.schemas.user import ProfileUpdate


def test_legacy_scalar_payload_is_normalized_to_array():
    payload = ProfileUpdate(current_financial_status="overspending")
    assert payload.current_financial_status == ["overspending"]


def test_onboarding_saves_and_returns_multiple_financial_statuses():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    user = User(phone="09120000999", current_financial_status=[])
    db.add(user)
    db.commit()
    db.refresh(user)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        values = ["irregular_income", "in_debt"]
        response = client.post(
            "/api/v1/onboarding/profile",
            json={"current_financial_status": values},
        )
        assert response.status_code == 200
        status = client.get("/api/v1/onboarding/status")
        assert status.status_code == 200
        assert status.json()["current_financial_status"] == values
    finally:
        app.dependency_overrides.clear()
        db.close()
