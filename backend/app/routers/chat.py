from datetime import datetime
from typing import AsyncIterator
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_user
from app.core.jalali import current_jalali_month
from app.models.user import User
from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction, TransactionType
from app.models.goal import Goal
from app.models.chat import ChatMessage, MessageRole
from app.schemas.chat import ChatMessageIn, ChatReply, ChatHistoryResponse, ChatMessageOut
from app.services.ai import get_ai_reply, stream_ai_reply
import json

router = APIRouter(prefix="/chat", tags=["chat"])


def _build_user_context(user: User, db: Session) -> dict:
    jm, jy = current_jalali_month()
    from datetime import date
    today = date.today()
    start = date(today.year, today.month, 1)

    budget = db.query(Budget).filter(
        Budget.user_id == user.id, Budget.month == jm, Budget.year == jy
    ).first()

    spent = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user.id,
        Transaction.type == TransactionType.expense,
        Transaction.date >= start,
    ).scalar() or 0

    # Top 3 categories
    from sqlalchemy import desc
    cat_rows = db.query(
        Transaction.category_id,
        func.sum(Transaction.amount).label("total"),
    ).filter(
        Transaction.user_id == user.id,
        Transaction.type == TransactionType.expense,
        Transaction.date >= start,
    ).group_by(Transaction.category_id).order_by(desc("total")).limit(3).all()

    top_cats = []
    for row in cat_rows:
        cat = db.query(Category).filter(Category.id == row.category_id).first()
        top_cats.append({"name": cat.name if cat else "سایر", "amount": row.total})

    goals = db.query(Goal).filter(Goal.user_id == user.id).limit(5).all()
    goal_data = [{"title": g.title, "current": g.current_amount, "target": g.target_amount} for g in goals]

    budget_amount = budget.amount if budget else 0
    return {
        "budget": budget_amount,
        "spent": spent,
        "remaining": budget_amount - spent,
        "top_categories": top_cats,
        "goals": goal_data,
    }


@router.post("/message", response_model=ChatReply)
async def send_message(
    body: ChatMessageIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Save user message
    user_msg = ChatMessage(
        user_id=current_user.id,
        role=MessageRole.user,
        content=body.content,
        created_at=datetime.utcnow(),
    )
    db.add(user_msg)
    db.commit()

    context = _build_user_context(current_user, db)
    reply = await get_ai_reply(body.content, context)

    # Save assistant reply
    assistant_msg = ChatMessage(
        user_id=current_user.id,
        role=MessageRole.assistant,
        content=reply,
        created_at=datetime.utcnow(),
    )
    db.add(assistant_msg)
    db.commit()

    return ChatReply(reply=reply)


@router.get("/stream")
async def stream_message(
    content: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    context = _build_user_context(current_user, db)

    async def event_generator():
        full_reply = []
        async for chunk in stream_ai_reply(content, context):
            full_reply.append(chunk)
            yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

        # Save messages after streaming
        user_msg = ChatMessage(user_id=current_user.id, role=MessageRole.user, content=content)
        assistant_msg = ChatMessage(
            user_id=current_user.id,
            role=MessageRole.assistant,
            content="".join(full_reply),
        )
        db.add(user_msg)
        db.add(assistant_msg)
        db.commit()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/history", response_model=ChatHistoryResponse)
def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total = db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id).count()
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ChatHistoryResponse(
        messages=[ChatMessageOut.model_validate(m) for m in messages],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id).delete()
    db.commit()
