from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.personal_cfo import FinancialMemory

ALLOWED_MEMORY_TYPES = {
    "goal",
    "income_pattern",
    "expense_pattern",
    "preference",
    "constraint",
    "behavioral_trigger",
    "important_decision",
    "user_profile",
    "recurring_payment",
    "saving_plan",
    "risk_note",
    "project_income",
    "future_commitment",
}


def create_memory(
    db: Session,
    user_id: int,
    memory_type: str,
    title: str,
    content_json: dict[str, Any],
    source: str = "chat",
    confidence: float = 0.7,
) -> FinancialMemory:
    if memory_type not in ALLOWED_MEMORY_TYPES:
        raise ValueError("unsupported memory type")
    memory = FinancialMemory(
        user_id=user_id,
        memory_type=memory_type,
        title=title[:200],
        content_json=content_json,
        source=source,
        confidence=max(0, min(float(confidence), 1)),
        is_active=True,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def search_recent_memories(
    db: Session,
    user_id: int,
    memory_types: list[str] | None = None,
    limit: int = 10,
) -> list[FinancialMemory]:
    query = db.query(FinancialMemory).filter(FinancialMemory.user_id == user_id, FinancialMemory.is_active == True)
    if memory_types:
        query = query.filter(FinancialMemory.memory_type.in_(memory_types))
    return query.order_by(FinancialMemory.updated_at.desc(), FinancialMemory.id.desc()).limit(limit).all()


def deactivate_memory(db: Session, memory_id: int, user_id: int) -> bool:
    memory = db.query(FinancialMemory).filter(FinancialMemory.id == memory_id, FinancialMemory.user_id == user_id).first()
    if not memory:
        return False
    memory.is_active = False
    db.commit()
    return True


def serialize_memories_for_agent(db: Session, user_id: int) -> list[dict[str, Any]]:
    return [
        {
            "memory_type": memory.memory_type,
            "title": memory.title,
            "content": memory.content_json,
            "confidence": memory.confidence,
        }
        for memory in search_recent_memories(db, user_id, limit=8)
    ]
