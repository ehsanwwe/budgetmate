"""Tests for the onboarding intro (self-description memory) endpoints."""
from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.db import Base, get_db
from app.main import app
from app.models import User
from app.models.personal_cfo import FinancialMemory
from app.services.personal_cfo.memory_service import search_recent_memories


# ---------------------------------------------------------------------------
# Test DB helpers
# ---------------------------------------------------------------------------

def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, phone="09120000001", name="Test", language="fa"))
    session.commit()
    return session


def _client(db):
    test_user = db.query(User).filter(User.id == 1).first()

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: test_user
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /onboarding/intro — text only
# ---------------------------------------------------------------------------

def test_intro_with_text_creates_memory():
    db = _make_db()
    client = _client(db)
    res = client.post("/api/v1/onboarding/intro", json={"text": "من آدم ولخرجی هستم", "source": "text"})
    assert res.status_code == 200
    assert res.json()["ok"] is True

    memories = search_recent_memories(db, user_id=1, memory_types=["user_profile"])
    assert len(memories) == 1
    assert memories[0].title == "onboarding_self_description"
    assert memories[0].content_json["text"] == "من آدم ولخرجی هستم"
    assert memories[0].content_json["created_from"] == "onboarding_intro"
    assert memories[0].confidence == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# POST /onboarding/intro — audio transcript only
# ---------------------------------------------------------------------------

def test_intro_with_audio_transcript_creates_memory():
    db = _make_db()
    client = _client(db)
    res = client.post(
        "/api/v1/onboarding/intro",
        json={"audio_transcript": "درآمدم نامنظم است", "source": "audio"},
    )
    assert res.status_code == 200
    memories = search_recent_memories(db, user_id=1, memory_types=["user_profile"])
    assert len(memories) == 1
    assert memories[0].content_json["audio_transcript"] == "درآمدم نامنظم است"
    assert memories[0].confidence == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# POST /onboarding/intro — mixed (text + audio transcript)
# ---------------------------------------------------------------------------

def test_intro_mixed_combines_both_sources():
    db = _make_db()
    client = _client(db)
    res = client.post(
        "/api/v1/onboarding/intro",
        json={
            "text": "متن تایپی",
            "audio_transcript": "متن صوتی",
            "source": "mixed",
        },
    )
    assert res.status_code == 200
    memories = search_recent_memories(db, user_id=1, memory_types=["user_profile"])
    assert len(memories) == 1
    content = memories[0].content_json
    assert content["text"] == "متن تایپی"
    assert content["audio_transcript"] == "متن صوتی"
    assert "متن تایپی" in content["combined_text"]
    assert "متن صوتی" in content["combined_text"]
    assert memories[0].confidence == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# POST /onboarding/intro — empty body does not create memory
# ---------------------------------------------------------------------------

def test_intro_empty_body_creates_no_memory():
    db = _make_db()
    client = _client(db)
    res = client.post("/api/v1/onboarding/intro", json={})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    memories = search_recent_memories(db, user_id=1, memory_types=["user_profile"])
    assert len(memories) == 0


# ---------------------------------------------------------------------------
# POST /onboarding/intro — deduplication: second call replaces old memory
# ---------------------------------------------------------------------------

def test_intro_second_call_replaces_old_memory():
    db = _make_db()
    client = _client(db)

    client.post("/api/v1/onboarding/intro", json={"text": "اولین توضیح", "source": "text"})
    client.post("/api/v1/onboarding/intro", json={"text": "توضیح جدید", "source": "text"})

    active = search_recent_memories(db, user_id=1, memory_types=["user_profile"])
    assert len(active) == 1
    assert active[0].content_json["text"] == "توضیح جدید"

    # Old memory must be deactivated
    all_memories = (
        db.query(FinancialMemory)
        .filter(
            FinancialMemory.user_id == 1,
            FinancialMemory.title == "onboarding_self_description",
        )
        .all()
    )
    assert len(all_memories) == 2
    inactive = [m for m in all_memories if not m.is_active]
    assert len(inactive) == 1
    assert inactive[0].content_json["text"] == "اولین توضیح"


# ---------------------------------------------------------------------------
# POST /onboarding/intro/audio — success path
# ---------------------------------------------------------------------------

def test_audio_endpoint_returns_transcript():
    db = _make_db()
    client = _client(db)

    with patch(
        "app.routers.onboarding.transcribe_audio",
        new=AsyncMock(return_value={"transcript": "این یک تست است"}),
    ):
        res = client.post(
            "/api/v1/onboarding/intro/audio",
            files={"file": ("audio.webm", BytesIO(b"fakeaudio"), "audio/webm")},
            data={"duration_seconds": "3.5"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["transcript"] == "این یک تست است"
    assert body["empty"] is False


# ---------------------------------------------------------------------------
# POST /onboarding/intro/audio — empty transcript
# ---------------------------------------------------------------------------

def test_audio_endpoint_empty_transcript_returns_ok():
    db = _make_db()
    client = _client(db)

    with patch(
        "app.routers.onboarding.transcribe_audio",
        new=AsyncMock(return_value={"transcript": ""}),
    ):
        res = client.post(
            "/api/v1/onboarding/intro/audio",
            files={"file": ("audio.webm", BytesIO(b"fakeaudio"), "audio/webm")},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["transcript"] == ""
    assert body["empty"] is True


# ---------------------------------------------------------------------------
# Memory appears in build_cfo_context / serialize_memories_for_agent
# ---------------------------------------------------------------------------

def test_intro_memory_in_cfo_context():
    from app.services.personal_cfo.memory_service import serialize_memories_for_agent

    db = _make_db()
    client = _client(db)
    client.post("/api/v1/onboarding/intro", json={"text": "وقتی استرس دارم خرید می‌کنم", "source": "text"})

    serialized = serialize_memories_for_agent(db, user_id=1)
    assert len(serialized) == 1
    assert serialized[0]["title"] == "onboarding_self_description"
    assert "وقتی استرس دارم خرید می‌کنم" in serialized[0]["content"]["combined_text"]
