from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.chat import ChatMessage, MessageRole
from app.schemas.chat import ChatMessageIn, ChatReply, ChatHistoryResponse, ChatMessageOut
from app.services.billing import INSUFFICIENT_TOKENS_MESSAGE, consume_chat_tokens, ensure_wallet
from app.services.token_meter import estimate_tokens, estimate_chat_usage
from app.services.stt import transcribe_audio
from app.services.agent_orchestrator import AgentOrchestrator
import json

router = APIRouter(prefix="/chat", tags=["chat"])
orchestrator = AgentOrchestrator()


def _save_message(db: Session, user_id: int, role: MessageRole, content: str) -> ChatMessage:
    msg = ChatMessage(user_id=user_id, role=role, content=content, created_at=datetime.utcnow())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _get_history(db: Session, user_id: int, limit: int = 20) -> list[dict]:
    """Fetch last `limit` messages ordered oldest-first, formatted for the AI provider."""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return [{"role": m.role.value, "content": m.content} for m in reversed(messages)]


@router.post("/message", response_model=ChatReply)
async def send_message(
    body: ChatMessageIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallet = ensure_wallet(db, current_user.id)
    est_prompt = estimate_tokens(body.content)
    if wallet.balance_tokens <= 0 or wallet.balance_tokens < est_prompt:
        return ChatReply(reply=INSUFFICIENT_TOKENS_MESSAGE)

    history = _get_history(db, current_user.id)
    _save_message(db, current_user.id, MessageRole.user, body.content)
    final = await orchestrator.run(
        db,
        current_user,
        body.content,
        history=history,
        chat_mode=getattr(current_user, "chat_mode", "normal"),
    )
    reply = final.message
    assistant_msg = _save_message(db, current_user.id, MessageRole.assistant, reply)

    usage = estimate_chat_usage(body.content, reply)
    consume_chat_tokens(
        db,
        current_user.id,
        usage,
        chat_message_id=assistant_msg.id,
    )
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

    wallet = ensure_wallet(db, current_user.id)
    est_prompt = estimate_tokens(user_content)
    if wallet.balance_tokens <= 0 or wallet.balance_tokens < est_prompt:
        async def insufficient():
            yield f"data: {json.dumps({'chunk': INSUFFICIENT_TOKENS_MESSAGE}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(insufficient(), media_type="text/event-stream")

    history = _get_history(db, current_user.id)

    async def event_generator():
        final = await orchestrator.run(
            db,
            current_user,
            user_content,
            history=history,
            chat_mode=getattr(current_user, "chat_mode", "normal"),
        )
        final_reply = final.message
        for word in final_reply.split(" "):
            yield f"data: {json.dumps({'chunk': word + ' '}, ensure_ascii=False)}\n\n"
        yield f"event: complete\ndata: {json.dumps({'text': final_reply}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        _save_message(db, current_user.id, MessageRole.user, user_content)
        assistant_msg = _save_message(db, current_user.id, MessageRole.assistant, final_reply)
        usage = estimate_chat_usage(user_content, final_reply)
        consume_chat_tokens(db, current_user.id, usage, chat_message_id=assistant_msg.id)

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


@router.post("/voice")
async def voice_message(
    audio: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Accept audio file, transcribe to Persian text, forward to AI chat pipeline."""
    audio_bytes = await audio.read()
    content_type = audio.content_type or "audio/webm"
    stt_result = await transcribe_audio(audio_bytes, content_type)

    if stt_result.get("error") and not stt_result.get("transcript"):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"transcript": "", "error": stt_result["error"]},
        )

    transcript = stt_result["transcript"]
    if not transcript.strip():
        return {"transcript": "", "reply": "", "message_id": None}

    # Forward transcript to chat pipeline
    wallet = ensure_wallet(db, current_user.id)
    est_prompt = estimate_tokens(transcript)
    if wallet.balance_tokens <= 0 or wallet.balance_tokens < est_prompt:
        return {"transcript": transcript, "reply": INSUFFICIENT_TOKENS_MESSAGE, "message_id": None}

    history = _get_history(db, current_user.id)
    _save_message(db, current_user.id, MessageRole.user, transcript)
    final = await orchestrator.run(
        db,
        current_user,
        transcript,
        history=history,
        chat_mode=getattr(current_user, "chat_mode", "normal"),
    )
    reply = final.message
    assistant_msg = _save_message(db, current_user.id, MessageRole.assistant, reply)

    usage = estimate_chat_usage(transcript, reply)
    consume_chat_tokens(db, current_user.id, usage, chat_message_id=assistant_msg.id)

    return {"transcript": transcript, "reply": reply, "message_id": assistant_msg.id}


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id).delete()
    db.commit()
