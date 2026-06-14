from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.personal_cfo import FinancialFact


def create_fact(
    db: Session,
    user_id: int,
    fact_type: str,
    subject: str,
    value_json: dict[str, Any],
    confidence: float = 0.7,
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> FinancialFact:
    row = FinancialFact(
        user_id=user_id,
        fact_type=fact_type[:80],
        subject=subject[:200],
        value_json=value_json,
        confidence=max(0, min(float(confidence), 1)),
        valid_from=valid_from,
        valid_to=valid_to,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_facts(db: Session, user_id: int, fact_types: list[str] | None = None, limit: int = 20) -> list[FinancialFact]:
    query = db.query(FinancialFact).filter(FinancialFact.user_id == user_id, FinancialFact.is_active == True)
    if fact_types:
        query = query.filter(FinancialFact.fact_type.in_(fact_types))
    return query.order_by(FinancialFact.updated_at.desc(), FinancialFact.id.desc()).limit(limit).all()


def serialize_facts_for_agent(db: Session, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
    return [
        {
            "id": row.id,
            "fact_type": row.fact_type,
            "subject": row.subject,
            "value": row.value_json,
            "confidence": row.confidence,
            "valid_from": row.valid_from.isoformat() if row.valid_from else None,
            "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        }
        for row in list_facts(db, user_id, limit=limit)
    ]
