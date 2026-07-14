from datetime import datetime
import json
import logging
import threading
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.chat import ChatMessage, MessageRole
from app.schemas.chat import ChatClearResponse, ChatMessageEdit, ChatMessageIn, ChatReply, ChatHistoryResponse, ChatMessageOut
from app.services.billing import INSUFFICIENT_TOKENS_MESSAGE, consume_chat_tokens, ensure_wallet
from app.services.chat_session_lifecycle import (
    ChatMessageNotEditableError,
    ChatMessageNotFoundError,
    clear_chat_history_and_transient_state,
    edit_chat_message_and_truncate,
)
from app.services.token_meter import estimate_tokens, estimate_chat_usage
from app.services.stt import transcribe_audio
from app.services.agent_orchestrator import AgentOrchestrator

router = APIRouter(prefix="/chat", tags=["chat"])
orchestrator = AgentOrchestrator()
logger = logging.getLogger(__name__)

_generation_locks: dict[int, threading.Lock] = {}
_generation_locks_guard = threading.Lock()


def _try_acquire_generation(user_id: int) -> threading.Lock | None:
    with _generation_locks_guard:
        lock = _generation_locks.setdefault(user_id, threading.Lock())
    return lock if lock.acquire(blocking=False) else None


def _generation_conflict() -> HTTPException:
    return HTTPException(status_code=409, detail="A chat response is already being generated")


def _save_message(db: Session, user_id: int, role: MessageRole, content: str) -> ChatMessage:
    msg = ChatMessage(user_id=user_id, role=role, content=content, created_at=datetime.utcnow())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _get_history(db: Session, user_id: int, limit: int = 30) -> list[dict]:
    """Fetch last `limit` messages ordered oldest-first, formatted for the AI provider."""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    return [{"role": m.role.value, "content": m.content} for m in reversed(messages)]


def _stream_assistant_response(
    *,
    db: Session,
    current_user: User,
    user_content: str,
    history: list[dict],
    user_message_id: int,
    client_message_id: str | None,
    generation_lock: threading.Lock,
):
    async def event_generator():
        try:
            yield (
                "event: metadata\n"
                f"data: {json.dumps({'user_message_id': user_message_id})}\n\n"
            )
            final = await orchestrator.run(
                db,
                current_user,
                user_content,
                history=history,
                chat_mode=getattr(current_user, "chat_mode", "normal"),
                client_message_id=client_message_id,
                source_message_id=user_message_id,
            )
            final_reply = final.message
            for word in final_reply.split(" "):
                yield f"data: {json.dumps({'chunk': word + ' '}, ensure_ascii=False)}\n\n"

            assistant_msg = _save_message(
                db, current_user.id, MessageRole.assistant, final_reply
            )
            usage = estimate_chat_usage(user_content, final_reply)
            consume_chat_tokens(
                db,
                current_user.id,
                usage,
                chat_message_id=assistant_msg.id,
            )
            yield (
                "event: complete\n"
                f"data: {json.dumps({'text': final_reply, 'assistant_message_id': assistant_msg.id}, ensure_ascii=False)}\n\n"
            )
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("Chat generation failed for user_id=%s", current_user.id)
            yield "event: error\ndata: {\"detail\": \"generation_failed\"}\n\n"
        finally:
            generation_lock.release()

    return event_generator()


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

    generation_lock = _try_acquire_generation(current_user.id)
    if generation_lock is None:
        raise _generation_conflict()
    try:
        history = _get_history(db, current_user.id)
        user_msg = _save_message(db, current_user.id, MessageRole.user, body.content)
        final = await orchestrator.run(
            db,
            current_user,
            body.content,
            history=history,
            chat_mode=getattr(current_user, "chat_mode", "normal"),
            client_message_id=body.client_message_id,
            source_message_id=user_msg.id,
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
        return ChatReply(
            reply=reply,
            user_message_id=user_msg.id,
            assistant_message_id=assistant_msg.id,
        )
    finally:
        generation_lock.release()


@router.get("/stream")
async def stream_message(
    content: Optional[str] = Query(None),
    message: Optional[str] = Query(None),
    client_message_id: Optional[str] = Query(None),
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

    generation_lock = _try_acquire_generation(current_user.id)
    if generation_lock is None:
        raise _generation_conflict()
    try:
        history = _get_history(db, current_user.id)
        # Save before orchestration so tool writes retain chat provenance.
        user_msg_id = _save_message(db, current_user.id, MessageRole.user, user_content).id
        generator = _stream_assistant_response(
            db=db,
            current_user=current_user,
            user_content=user_content,
            history=history,
            user_message_id=user_msg_id,
            client_message_id=client_message_id,
            generation_lock=generation_lock,
        )
    except Exception:
        generation_lock.release()
        raise
    return StreamingResponse(generator, media_type="text/event-stream")


@router.patch("/messages/{message_id}")
async def edit_message(
    message_id: int,
    body: ChatMessageEdit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = (
        db.query(ChatMessage)
        .filter(ChatMessage.id == message_id, ChatMessage.user_id == current_user.id)
        .first()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if target.role != MessageRole.user:
        raise HTTPException(status_code=422, detail="Message cannot be edited")

    wallet = ensure_wallet(db, current_user.id)
    est_prompt = estimate_tokens(body.content)
    if wallet.balance_tokens <= 0 or wallet.balance_tokens < est_prompt:
        raise HTTPException(status_code=402, detail=INSUFFICIENT_TOKENS_MESSAGE)

    generation_lock = _try_acquire_generation(current_user.id)
    if generation_lock is None:
        raise _generation_conflict()
    try:
        result = edit_chat_message_and_truncate(
            db, current_user.id, message_id, body.content
        )
        generator = _stream_assistant_response(
            db=db,
            current_user=current_user,
            user_content=body.content,
            history=result.history,
            user_message_id=result.message.id,
            client_message_id=body.client_message_id,
            generation_lock=generation_lock,
        )
    except ChatMessageNotFoundError:
        generation_lock.release()
        raise HTTPException(status_code=404, detail="Message not found")
    except ChatMessageNotEditableError:
        generation_lock.release()
        raise HTTPException(status_code=422, detail="Message cannot be edited")
    except Exception:
        generation_lock.release()
        raise
    return StreamingResponse(generator, media_type="text/event-stream")


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

    generation_lock = _try_acquire_generation(current_user.id)
    if generation_lock is None:
        raise _generation_conflict()
    try:
        history = _get_history(db, current_user.id)
        user_msg = _save_message(db, current_user.id, MessageRole.user, transcript)
        final = await orchestrator.run(
            db,
            current_user,
            transcript,
            history=history,
            chat_mode=getattr(current_user, "chat_mode", "normal"),
            source_message_id=user_msg.id,
        )
        reply = final.message
        assistant_msg = _save_message(db, current_user.id, MessageRole.assistant, reply)

        usage = estimate_chat_usage(transcript, reply)
        consume_chat_tokens(db, current_user.id, usage, chat_message_id=assistant_msg.id)

        return {
            "transcript": transcript,
            "reply": reply,
            "user_message_id": user_msg.id,
            "message_id": assistant_msg.id,
        }
    finally:
        generation_lock.release()


@router.delete("/history", response_model=ChatClearResponse)
def clear_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return clear_chat_history_and_transient_state(db, current_user.id)
