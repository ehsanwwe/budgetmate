from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.chat import ChatMessage, MessageRole
from app.schemas.chat import ChatMessageIn, ChatReply, ChatHistoryResponse, ChatMessageOut
from app.services.finance_agent import handle_finance_message
import json

router = APIRouter(prefix="/chat", tags=["chat"])


def _save_message(db: Session, user_id: int, role: MessageRole, content: str) -> None:
    db.add(ChatMessage(user_id=user_id, role=role, content=content, created_at=datetime.utcnow()))
    db.commit()


@router.post("/message", response_model=ChatReply)
async def send_message(
    body: ChatMessageIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _save_message(db, current_user.id, MessageRole.user, body.content)
    reply = await handle_finance_message(body.content, current_user, db)
    _save_message(db, current_user.id, MessageRole.assistant, reply)
    return ChatReply(reply=reply)


@router.get("/stream")
async def stream_message(
    content: Optional[str] = Query(None),
    message: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_content = content or message
    if not user_content:
        raise HTTPException(status_code=400, detail="متن پیام الزامی است")

    async def event_generator():
        reply = await handle_finance_message(user_content, current_user, db)
        for word in reply.split(" "):
            yield f"data: {json.dumps({'chunk': word + ' '}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        _save_message(db, current_user.id, MessageRole.user, user_content)
        _save_message(db, current_user.id, MessageRole.assistant, reply)

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
