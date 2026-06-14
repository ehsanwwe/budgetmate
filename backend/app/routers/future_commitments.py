from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db import get_db
from app.models.user import User
from app.schemas.future_commitment import FutureCommitmentCreate, FutureCommitmentOut, FutureCommitmentUpdate
from app.services.agent_orchestrator.date_utils import local_month_range, local_today
from app.services.personal_cfo.future_commitment_service import list_future_commitments as list_future_commitment_rows

router = APIRouter(prefix="/future-commitments", tags=["future-commitments"])


@router.get("", response_model=list[FutureCommitmentOut])
def list_future_commitments(
    status_filter: str | None = Query(default=None, alias="status"),
    from_date: date | None = None,
    to_date: date | None = None,
    period: str | None = Query(default=None, pattern="^(next_month|until_next_year)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if period == "next_month":
        _, next_month_anchor = local_month_range(local_today())
        from_date, to_date = local_month_range(next_month_anchor)
    elif period == "until_next_year":
        today = local_today()
        from_date = from_date or today
        to_date = to_date or date(today.year + 1, today.month, today.day)
    status = status_filter if status_filter in {"pending", "paid", "cancelled"} else None
    rows = list_future_commitment_rows(
        db,
        current_user.id,
        from_date=from_date,
        to_date=to_date,
        status=status,
        limit=100,
    )
    if status_filter is None:
        rows = [row for row in rows if row.status != "cancelled"]
    return rows


@router.post("", response_model=FutureCommitmentOut, status_code=status.HTTP_201_CREATED)
def create_future_commitment(
    body: FutureCommitmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.future_commitment import FutureCommitment

    row = FutureCommitment(user_id=current_user.id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{commitment_id}", response_model=FutureCommitmentOut)
def update_future_commitment(
    commitment_id: int,
    body: FutureCommitmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.future_commitment import FutureCommitment

    row = db.query(FutureCommitment).filter(
        FutureCommitment.id == commitment_id,
        FutureCommitment.user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="future commitment not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row
