from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin
from app.db import get_db
from app.i18n.config import SUPPORTED_LOCALES
from app.i18n.service import get_i18n_service
from app.models.admin import AdminUser
from app.models.translation import TranslationEntry

router = APIRouter(prefix="/admin/translations", tags=["admin-translations"])


class TranslationEntryOut(BaseModel):
    id: int
    namespace: str
    key: str
    locale: str
    value: str
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    updated_by_user_id: Optional[int] = None

    model_config = {"from_attributes": True}


class TranslationEntryCreate(BaseModel):
    namespace: str
    key: str
    locale: str
    value: str
    is_active: bool = True


class TranslationEntryUpdate(BaseModel):
    value: Optional[str] = None
    is_active: Optional[bool] = None


class TranslationListResponse(BaseModel):
    items: List[TranslationEntryOut]
    total: int
    page: int
    page_size: int


def _reload_overrides(db: Session) -> None:
    entries = db.query(TranslationEntry).all()
    service = get_i18n_service()
    service.load_db_overrides([
        {
            "locale": e.locale,
            "namespace": e.namespace,
            "key": e.key,
            "value": e.value,
            "is_active": e.is_active,
        }
        for e in entries
    ])


@router.get("", response_model=TranslationListResponse)
def list_translations(
    locale: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    q = db.query(TranslationEntry)
    if locale:
        q = q.filter(TranslationEntry.locale == locale)
    if namespace:
        q = q.filter(TranslationEntry.namespace == namespace)
    if search:
        q = q.filter(
            TranslationEntry.key.ilike(f"%{search}%") |
            TranslationEntry.value.ilike(f"%{search}%")
        )
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return TranslationListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=TranslationEntryOut, status_code=201)
def create_translation(
    body: TranslationEntryCreate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if body.locale not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=422, detail=f"locale must be one of: {', '.join(SUPPORTED_LOCALES)}")

    existing = (
        db.query(TranslationEntry)
        .filter_by(locale=body.locale, namespace=body.namespace, key=body.key)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Translation entry already exists. Use PATCH to update.")

    entry = TranslationEntry(
        namespace=body.namespace,
        key=body.key,
        locale=body.locale,
        value=body.value,
        is_active=body.is_active,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        updated_by_user_id=None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    _reload_overrides(db)
    return entry


@router.patch("/{entry_id}", response_model=TranslationEntryOut)
def update_translation(
    entry_id: int,
    body: TranslationEntryUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    entry = db.query(TranslationEntry).filter(TranslationEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Translation entry not found")
    if body.value is not None:
        entry.value = body.value
    if body.is_active is not None:
        entry.is_active = body.is_active
    entry.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(entry)
    _reload_overrides(db)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_translation(
    entry_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    entry = db.query(TranslationEntry).filter(TranslationEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Translation entry not found")
    db.delete(entry)
    db.commit()
    _reload_overrides(db)
