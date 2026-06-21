from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_admin
from app.models.admin import AdminUser
from app.models.user import User
from app.models.transaction import Transaction
from app.models.budget import Budget
from app.models.goal import Goal
from app.models.chat import ChatMessage
from app.models.activity import ActivityLog
from app.models.billing import TokenUsageLog, TokenPurchase, UserSubscription, TokenWallet
from app.schemas.user import UserOut
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    blocked_users: int
    total_transactions: int
    total_goals: int


@router.get("/stats", response_model=AdminStats)
def get_stats(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    total_users = db.query(User).count()
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    active_users = db.query(func.count(func.distinct(ActivityLog.user_id))).filter(
        ActivityLog.created_at >= seven_days_ago,
        ActivityLog.user_id.isnot(None),
    ).scalar() or 0
    blocked_users = db.query(User).filter(User.is_blocked == True).count()
    total_transactions = db.query(Transaction).count()
    total_goals = db.query(Goal).count()
    return AdminStats(
        total_users=total_users,
        active_users=active_users,
        blocked_users=blocked_users,
        total_transactions=total_transactions,
        total_goals=total_goals,
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


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    phone = user.phone
    log = ActivityLog(
        user_id=None,
        action="admin_deleted_user",
        meta={"target_user_id": user_id, "target_phone": phone, "by_admin": admin.username},
    )
    db.add(log)
    db.query(TokenUsageLog).filter(TokenUsageLog.user_id == user_id).delete()
    db.query(TokenPurchase).filter(TokenPurchase.user_id == user_id).delete()
    db.query(UserSubscription).filter(UserSubscription.user_id == user_id).delete()
    db.query(TokenWallet).filter(TokenWallet.user_id == user_id).delete()
    db.query(ChatMessage).filter(ChatMessage.user_id == user_id).delete()
    db.query(Transaction).filter(Transaction.user_id == user_id).delete()
    db.query(Budget).filter(Budget.user_id == user_id).delete()
    db.query(Goal).filter(Goal.user_id == user_id).delete()
    db.query(ActivityLog).filter(ActivityLog.user_id == user_id).delete()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    return {"deleted": True, "user_id": user_id}


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatHistoryResponse(BaseModel):
    items: List[ChatMessageOut]
    page: int
    page_size: int
    total: int


@router.get("/users/{user_id}/chats", response_model=ChatHistoryResponse)
def get_user_chats(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not db.query(User).filter(User.id == user_id).first():
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    total = db.query(ChatMessage).filter(ChatMessage.user_id == user_id).count()
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    messages.reverse()
    return ChatHistoryResponse(items=messages, page=page, page_size=page_size, total=total)


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
