from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from app.db import Base


class FinancialPersona(Base):
    __tablename__ = "financial_personas"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    financial_literacy_level = Column(String, nullable=True)
    risk_tolerance = Column(String, nullable=True)
    financial_anxiety_level = Column(String, nullable=True)
    decision_style = Column(String, nullable=True)
    time_horizon = Column(String, nullable=True)
    debt_sensitivity = Column(String, nullable=True)
    discipline_score = Column(Float, nullable=True)
    saving_preference = Column(String, nullable=True)
    emotional_spending_triggers_json = Column(JSON, nullable=True)
    notes_json = Column(JSON, nullable=True)
    confidence = Column(Float, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class FinancialMemory(Base):
    __tablename__ = "financial_memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    memory_type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    content_json = Column(JSON, nullable=False)
    source = Column(String, nullable=False, default="chat")
    confidence = Column(Float, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class BehaviorInsight(Base):
    __tablename__ = "behavior_insights"
    __table_args__ = (UniqueConstraint("user_id", "insight_type", name="uq_behavior_insight_user_type"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    insight_type = Column(String, nullable=False, index=True)
    evidence_json = Column(JSON, nullable=False)
    confidence = Column(Float, default=0, nullable=False)
    first_detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_detected_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)


class PersonaUpdateLog(Base):
    __tablename__ = "persona_update_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    previous_json = Column(JSON, nullable=True)
    new_json = Column(JSON, nullable=False)
    reason = Column(Text, nullable=True)
    confidence = Column(Float, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
