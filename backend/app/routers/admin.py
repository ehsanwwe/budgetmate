from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_admin
from app.models.admin import AdminUser
from app.models.user import User
from app.models.transaction import Transaction
from app.models.chat import ChatMessage
from app.models.activity import ActivityLog
from app.schemas.user import UserOut
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminStats(BaseModel):
    users_total: int
    users_active_7d: int
    transactions_total: int
    transactions_today: int
    chat_messages_total: int


@router.get("/stats", response_model=AdminStats)
def get_stats(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    users_total = db.query(User).count()
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    users_active_7d = db.query(func.count(func.distinct(ActivityLog.user_id))).filter(
        ActivityLog.created_at >= seven_days_ago,
        ActivityLog.user_id.isnot(None),
    ).scalar() or 0
    transactions_total = db.query(Transaction).count()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    transactions_today = db.query(Transaction).filter(Transaction.created_at >= today_start).count()
    chat_messages_total = db.query(ChatMessage).count()
    return AdminStats(
        users_total=users_total,
        users_active_7d=users_active_7d,
        transactions_total=transactions_total,
        transactions_today=transactions_today,
        chat_messages_total=chat_messages_total,
    )


class UserListResponse(BaseModel):
    users: List[UserOut]
    total: int
    page: int
    page_size: int


@router.get("/users", response_model=UserListResponse)
def list_users(
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if q:
        query = query.filter(
            (User.phone.ilike(f"%{q}%")) | (User.name.ilike(f"%{q}%"))
        )
    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()
    return UserListResponse(
        users=[UserOut.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    return user


@router.post("/users/{user_id}/block")
def block_user(
    user_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    user.is_blocked = True
    log = ActivityLog(action="user_blocked", meta={"user_id": user_id, "by_admin": admin.username})
    db.add(log)
    db.commit()
    return {"message": "کاربر مسدود شد"}


@router.post("/users/{user_id}/unblock")
def unblock_user(
    user_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    user.is_blocked = False
    log = ActivityLog(action="user_unblocked", meta={"user_id": user_id, "by_admin": admin.username})
    db.add(log)
    db.commit()
    return {"message": "مسدودیت کاربر رفع شد"}


class ActivityOut(BaseModel):
    id: int
    user_id: Optional[int] = None
    action: str
    meta: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/activity", response_model=List[ActivityOut])
def get_activity(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    logs = db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(100).all()
    return logs
