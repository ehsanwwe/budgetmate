from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db import get_db
from app.models.future_commitment import FutureCommitment
from app.models.user import User
from app.schemas.future_commitment import FutureCommitmentCreate, FutureCommitmentOut, FutureCommitmentUpdate

router = APIRouter(prefix="/future-commitments", tags=["future-commitments"])


@router.get("", response_model=list[FutureCommitmentOut])
def list_future_commitments(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(FutureCommitment).filter(
        FutureCommitment.user_id == current_user.id,
        FutureCommitment.status != "cancelled",
    ).order_by(FutureCommitment.due_date.asc().nullslast(), FutureCommitment.id.desc()).limit(100).all()


@router.post("", response_model=FutureCommitmentOut, status_code=status.HTTP_201_CREATED)
def create_future_commitment(
    body: FutureCommitmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
