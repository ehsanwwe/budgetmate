"""Tests for the i18n service and user preference endpoints."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.i18n.service import I18nService
from app.i18n.config import SUPPORTED_LOCALES, SUPPORTED_CURRENCIES, is_valid_locale, is_valid_currency


# ── i18n service unit tests ──────────────────────────────────────────────────

def test_service_loads_fa_dict():
    svc = I18nService()
    val = svc.t("common.save", "fa")
    assert val == "ذخیره"


def test_service_loads_en_dict():
    svc = I18nService()
    val = svc.t("common.save", "en")
    assert val == "Save"


def test_service_loads_de_dict():
    svc = I18nService()
    val = svc.t("common.save", "de")
    assert val == "Speichern"


def test_service_loads_zh_dict():
    svc = I18nService()
    val = svc.t("common.save", "zh")
    assert val == "保存"


def test_service_loads_ar_dict():
    svc = I18nService()
    val = svc.t("common.save", "ar")
    assert val == "حفظ"


def test_service_fallback_to_fa_for_unknown_locale():
    svc = I18nService()
    val = svc.t("common.save", "xx_invalid")
    assert val == "ذخیره"


def test_service_missing_key_returns_key():
    svc = I18nService()
    val = svc.t("nonexistent.key.path", "fa")
    assert val == "nonexistent.key.path"


def test_service_db_override_wins():
    svc = I18nService()
    svc.load_db_overrides([
        {"locale": "fa", "namespace": "common", "key": "save", "value": "ثبت", "is_active": True}
    ])
    val = svc.t("common.save", "fa")
    assert val == "ثبت"


def test_service_inactive_override_falls_back():
    svc = I18nService()
    svc.load_db_overrides([
        {"locale": "fa", "namespace": "common", "key": "save", "value": "ثبت", "is_active": False}
    ])
    # After loading override, reset it so this test is isolated
    fresh = I18nService()
    fresh.load_db_overrides([
        {"locale": "fa", "namespace": "common", "key": "save", "value": "ثبت", "is_active": False}
    ])
    val = fresh.t("common.save", "fa")
    assert val == "ذخیره"  # falls back to file dict


def test_service_interpolation():
    svc = I18nService()
    svc.load_db_overrides([
        {"locale": "en", "namespace": "test", "key": "hello", "value": "Hello {name}!", "is_active": True}
    ])
    val = svc.t("test.hello", "en", {"name": "World"})
    assert val == "Hello World!"


# ── locale/currency config tests ─────────────────────────────────────────────

def test_all_supported_locales_valid():
    for locale in ["fa", "ar", "en", "de", "zh"]:
        assert is_valid_locale(locale)


def test_invalid_locale():
    assert not is_valid_locale("xx")
    assert not is_valid_locale("")
    assert not is_valid_locale("fr")


def test_all_supported_currencies_valid():
    for cur in ["IRT", "USD", "EUR", "CNY"]:
        assert is_valid_currency(cur)


def test_invalid_currency():
    assert not is_valid_currency("FAKE")
    assert not is_valid_currency("")


# ── user preferences API tests ───────────────────────────────────────────────

def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.db import Base
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return Session()


def _make_user(db):
    from app.models.user import User
    user = User(
        id=1,
        phone="09120000099",
        language="fa",
        preferred_currency="IRT",
        is_blocked=False,
        onboarding_completed=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_get_preferences():
    from app.main import app
    from app.db import get_db
    from app.core.auth import get_current_user

    db = _make_db()
    user = _make_user(db)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    try:
        r = client.get("/api/v1/users/me/preferences")
        assert r.status_code == 200
        data = r.json()
        assert data["language"] == "fa"
        assert data["preferred_currency"] == "IRT"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_update_language():
    from app.main import app
    from app.db import get_db
    from app.core.auth import get_current_user

    db = _make_db()
    user = _make_user(db)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    try:
        r = client.patch("/api/v1/users/me/preferences", json={"language": "en"})
        assert r.status_code == 200
        assert r.json()["language"] == "en"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_update_currency():
    from app.main import app
    from app.db import get_db
    from app.core.auth import get_current_user

    db = _make_db()
    user = _make_user(db)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    try:
        r = client.patch("/api/v1/users/me/preferences", json={"preferred_currency": "USD"})
        assert r.status_code == 200
        assert r.json()["preferred_currency"] == "USD"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_reject_invalid_language():
    from app.main import app
    from app.db import get_db
    from app.core.auth import get_current_user

    db = _make_db()
    user = _make_user(db)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    try:
        r = client.patch("/api/v1/users/me/preferences", json={"language": "fr"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_reject_invalid_currency():
    from app.main import app
    from app.db import get_db
    from app.core.auth import get_current_user

    db = _make_db()
    user = _make_user(db)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    try:
        r = client.patch("/api/v1/users/me/preferences", json={"preferred_currency": "FAKE"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_language_persists_in_me_endpoint():
    """language change via /me/preferences is visible in /me."""
    from app.main import app
    from app.db import get_db
    from app.core.auth import get_current_user

    db = _make_db()
    user = _make_user(db)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    try:
        client.patch("/api/v1/users/me/preferences", json={"language": "de"})
        db.refresh(user)
        r = client.get("/api/v1/users/me")
        assert r.status_code == 200
        assert r.json()["language"] == "de"
    finally:
        app.dependency_overrides.clear()
        db.close()
