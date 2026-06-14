from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db import get_db
from app.models.personal_cfo import BehaviorInsight, FinancialMemory
from app.models.user import User
from app.schemas.personal_cfo import (
    BehaviorInsightRead,
    FinancialMemoryCreate,
    FinancialMemoryRead,
    FinancialPersonaRead,
    FinancialPersonaUpdate,
)
from app.services.personal_cfo.memory_service import create_memory, deactivate_memory
from app.services.personal_cfo.persona_service import get_or_create_persona

router = APIRouter(prefix="/personal-cfo", tags=["personal-cfo"])


@router.get("/persona", response_model=FinancialPersonaRead)
def get_persona(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_or_create_persona(db, current_user.id)


@router.patch("/persona", response_model=FinancialPersonaRead)
def update_persona(
    body: FinancialPersonaUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    persona = get_or_create_persona(db, current_user.id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(persona, key, value)
    db.commit()
    db.refresh(persona)
    return persona


@router.get("/memories", response_model=list[FinancialMemoryRead])
def list_memories(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(FinancialMemory).filter(
        FinancialMemory.user_id == current_user.id,
        FinancialMemory.is_active == True,
    ).order_by(FinancialMemory.updated_at.desc()).limit(50).all()


@router.post("/memories", response_model=FinancialMemoryRead, status_code=status.HTTP_201_CREATED)
def add_memory(
    body: FinancialMemoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_memory(
        db,
        current_user.id,
        body.memory_type,
        body.title,
        body.content_json,
        body.source,
        body.confidence,
    )


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not deactivate_memory(db, memory_id, current_user.id):
        raise HTTPException(status_code=404, detail="memory not found")


@router.get("/behavior-insights", response_model=list[BehaviorInsightRead])
def list_behavior_insights(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(BehaviorInsight).filter(
        BehaviorInsight.user_id == current_user.id,
        BehaviorInsight.is_active == True,
    ).order_by(BehaviorInsight.last_detected_at.desc()).limit(50).all()
