from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.future_commitment import FutureCommitment


def create_future_commitment(
    db: Session,
    user_id: int,
    title: str,
    amount: int,
    due_date: date | None = None,
    due_month: str | None = None,
    description: str | None = None,
    status: str = "pending",
    source: str = "chat",
    metadata_json: dict[str, Any] | None = None,
) -> FutureCommitment:
    row = FutureCommitment(
        user_id=user_id,
        title=title[:200],
        amount=int(amount),
        due_date=due_date,
        due_month=due_month,
        description=description,
        status=status,
        source=source,
        metadata_json=metadata_json,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_future_commitments(
    db: Session,
    user_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
    status: str | None = "pending",
    limit: int = 100,
) -> list[FutureCommitment]:
    query = db.query(FutureCommitment).filter(FutureCommitment.user_id == user_id)
    if status:
        query = query.filter(FutureCommitment.status == status)
    if from_date:
        query = query.filter((FutureCommitment.due_date == None) | (FutureCommitment.due_date >= from_date))
    if to_date:
        query = query.filter((FutureCommitment.due_date == None) | (FutureCommitment.due_date <= to_date))
    return query.order_by(FutureCommitment.due_date.asc().nullslast(), FutureCommitment.id.desc()).limit(limit).all()


def update_future_commitment(db: Session, commitment_id: int, user_id: int, **values: Any) -> FutureCommitment | None:
    row = db.query(FutureCommitment).filter(FutureCommitment.id == commitment_id, FutureCommitment.user_id == user_id).first()
    if not row:
        return None
    for key, value in values.items():
        if value is not None and hasattr(row, key):
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def mark_commitment_paid(db: Session, commitment_id: int, user_id: int) -> FutureCommitment | None:
    return update_future_commitment(db, commitment_id, user_id, status="paid")


def serialize_commitments_for_agent(
    db: Session,
    user_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
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
        for row in list_future_commitments(db, user_id, from_date=from_date, to_date=to_date, limit=limit)
    ]
