from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.future_commitment import FutureCommitment
from app.models.personal_cfo import FinancialFact, FinancialWarning
from app.services.personal_cfo.behavior_service import serialize_behavior_insights_for_agent
from app.services.personal_cfo.memory_service import serialize_memories_for_agent
from app.services.personal_cfo.persona_service import serialize_persona_for_agent


def build_cfo_context(db: Session, user_id: int) -> dict:
    return {
        "persona": serialize_persona_for_agent(db, user_id),
        "memories": serialize_memories_for_agent(db, user_id),
        "behavior_insights": serialize_behavior_insights_for_agent(db, user_id),
        "facts": _serialize_facts(db, user_id),
        "warnings": _serialize_warnings(db, user_id),
        "future_commitments": _serialize_future_commitments(db, user_id),
    }


def _serialize_facts(db: Session, user_id: int) -> list[dict]:
    rows = db.query(FinancialFact).filter(
        FinancialFact.user_id == user_id,
        FinancialFact.is_active == True,
    ).order_by(FinancialFact.updated_at.desc(), FinancialFact.id.desc()).limit(8).all()
    return [
        {
            "fact_type": row.fact_type,
            "subject": row.subject,
            "value": row.value_json,
            "confidence": row.confidence,
            "valid_from": row.valid_from.isoformat() if row.valid_from else None,
            "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        }
        for row in rows
    ]


def _serialize_warnings(db: Session, user_id: int) -> list[dict]:
    rows = db.query(FinancialWarning).filter(
        FinancialWarning.user_id == user_id,
        FinancialWarning.status == "active",
    ).order_by(FinancialWarning.created_at.desc(), FinancialWarning.id.desc()).limit(5).all()
    return [
        {
            "warning_type": row.warning_type,
            "severity": row.severity,
            "message": row.message,
            "confidence_source": row.evidence_json,
        }
        for row in rows
    ]


def _serialize_future_commitments(db: Session, user_id: int) -> list[dict]:
    rows = db.query(FutureCommitment).filter(
        FutureCommitment.user_id == user_id,
        FutureCommitment.status == "pending",
    ).order_by(FutureCommitment.due_date.asc().nullslast(), FutureCommitment.id.desc()).limit(8).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "amount": row.amount,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "due_month": row.due_month,
            "description": row.description,
            "status": row.status,
        }
        for row in rows
    ]
