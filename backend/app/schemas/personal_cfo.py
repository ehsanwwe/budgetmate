from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FinancialPersonaRead(BaseModel):
    id: int
    user_id: int
    financial_literacy_level: str | None = None
    risk_tolerance: str | None = None
    financial_anxiety_level: str | None = None
    decision_style: str | None = None
    time_horizon: str | None = None
    debt_sensitivity: str | None = None
    discipline_score: float | None = None
    saving_preference: str | None = None
    emotional_spending_triggers_json: list[str] | dict[str, Any] | None = None
    notes_json: dict[str, Any] | None = None
    confidence: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FinancialPersonaUpdate(BaseModel):
    financial_literacy_level: str | None = None
    risk_tolerance: str | None = None
    financial_anxiety_level: str | None = None
    decision_style: str | None = None
    time_horizon: str | None = None
    debt_sensitivity: str | None = None
    discipline_score: float | None = Field(default=None, ge=0, le=1)
    saving_preference: str | None = None
    emotional_spending_triggers_json: list[str] | dict[str, Any] | None = None
    notes_json: dict[str, Any] | None = None


class FinancialMemoryCreate(BaseModel):
    memory_type: str
    title: str
    content_json: dict[str, Any]
    source: str = "manual"
    confidence: float = Field(default=0.8, ge=0, le=1)


class FinancialMemoryRead(BaseModel):
    id: int
    user_id: int
    memory_type: str
    title: str
    content_json: dict[str, Any]
    source: str
    confidence: float
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BehaviorInsightRead(BaseModel):
    id: int
    user_id: int
    insight_type: str
    evidence_json: dict[str, Any]
    confidence: float
    first_detected_at: datetime
    last_detected_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}
