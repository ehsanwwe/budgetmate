from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.models.agent_idempotency import PendingAgentIntent
from app.models.activity import ActivityLog
from app.models.chat import ChatMessage
from app.models.future_commitment import FutureCommitment
from app.models.personal_cfo import FinancialFact
from app.models.transaction import Transaction
from app.services.agent_orchestrator.goal_intake import STATE_CANCELLED, STATE_CONSULTATION

# fact_type reserved for per-conversation reasoning state (exclusions,
# baselines, user-stated balance). See personal_cfo/conversation_state.py.
CHAT_REASONING_FACT_TYPE = "chat_reasoning_state"


@dataclass(frozen=True)
class ChatClearResult:
    cleared_messages: int
    cancelled_pending_intents: int
    cancelled_advisory_sessions: int


@dataclass(frozen=True)
class ChatEditResult:
    message: ChatMessage
    removed_messages: int
    history: list[dict]


class ChatMessageNotFoundError(Exception):
    pass


class ChatMessageNotEditableError(Exception):
    pass


def _is_after_message(message: ChatMessage):
    return or_(
        ChatMessage.created_at > message.created_at,
        (ChatMessage.created_at == message.created_at) & (ChatMessage.id > message.id),
    )


def _history_before_message(
    db: Session, user_id: int, message: ChatMessage, limit: int = 30
) -> list[dict]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .filter(
            or_(
                ChatMessage.created_at < message.created_at,
                (ChatMessage.created_at == message.created_at) & (ChatMessage.id < message.id),
            )
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    return [{"role": row.role.value, "content": row.content} for row in reversed(rows)]


def edit_chat_message_and_truncate(
    db: Session, user_id: int, message_id: int, content: str
) -> ChatEditResult:
    """Replace one user message and remove its obsolete continuation atomically."""
    target = (
        db.query(ChatMessage)
        .filter(ChatMessage.id == message_id, ChatMessage.user_id == user_id)
        .first()
    )
    if target is None:
        raise ChatMessageNotFoundError
    if target.role.value != "user":
        raise ChatMessageNotEditableError

    later_rows = (
        db.query(ChatMessage.id)
        .filter(ChatMessage.user_id == user_id)
        .filter(_is_after_message(target))
        .all()
    )
    later_ids = [row.id for row in later_rows]
    now = datetime.utcnow()

    try:
        if later_ids:
            # Durable financial records survive branch replacement, but must not
            # retain foreign keys to chat messages that are about to be deleted.
            db.execute(
                update(Transaction)
                .where(Transaction.user_id == user_id)
                .where(Transaction.source_message_id.in_(later_ids))
                .values(source_message_id=None)
            )
            db.execute(
                update(FutureCommitment)
                .where(FutureCommitment.user_id == user_id)
                .where(FutureCommitment.source_message_id.in_(later_ids))
                .values(source_message_id=None)
            )
            db.execute(
                update(FinancialFact)
                .where(FinancialFact.user_id == user_id)
                .where(FinancialFact.source_message_id.in_(later_ids))
                .values(source_message_id=None, is_active=False)
            )

        affected_intents = (
            db.query(PendingAgentIntent)
            .filter(
                PendingAgentIntent.user_id == user_id,
                PendingAgentIntent.status == "pending",
                or_(
                    PendingAgentIntent.created_at >= target.created_at,
                    PendingAgentIntent.updated_at >= target.created_at,
                    PendingAgentIntent.source_message_id.in_(later_ids) if later_ids else False,
                ),
            )
            .all()
        )
        for intent in affected_intents:
            payload = dict(intent.payload_json or {})
            payload["state"] = STATE_CANCELLED
            payload["cancelled_reason"] = "chat_message_edited"
            intent.payload_json = payload
            intent.status = "cancelled"
            intent.consumed_at = now
            intent.updated_at = now
            if intent.source_message_id in later_ids:
                intent.source_message_id = None

        target.content = content
        removed_messages = 0
        if later_ids:
            removed_messages = (
                db.query(ChatMessage)
                .filter(ChatMessage.user_id == user_id, ChatMessage.id.in_(later_ids))
                .delete(synchronize_session="fetch")
            )

        db.add(
            ActivityLog(
                user_id=user_id,
                action="chat_message_edited",
                meta={"message_id": message_id, "removed_messages": removed_messages},
                created_at=now,
            )
        )
        db.commit()
        db.refresh(target)
    except Exception:
        db.rollback()
        raise

    return ChatEditResult(
        message=target,
        removed_messages=removed_messages,
        history=_history_before_message(db, user_id, target),
    )


def clear_chat_history_and_transient_state(db: Session, user_id: int) -> ChatClearResult:
    """Clear user-visible chat history and cancel transient conversation state.

    Durable financial records, CFO memories/facts/persona, goals, commitments,
    budgets, and audit logs are intentionally left untouched — but their
    chat-provenance link is dropped (source_message_id → NULL), and any
    conversational-only reasoning exclusions are deactivated. This means:
    "everything from this chat" queries after clear will match zero rows.
    """
    now = datetime.utcnow()

    active_intents = (
        db.query(PendingAgentIntent)
        .filter(
            PendingAgentIntent.user_id == user_id,
            PendingAgentIntent.status == "pending",
        )
        .all()
    )

    cancelled_advisory_sessions = 0
    for intent in active_intents:
        payload = dict(intent.payload_json or {})
        if payload.get("state") == STATE_CONSULTATION:
            cancelled_advisory_sessions += 1
        payload["state"] = STATE_CANCELLED
        payload["cancelled_reason"] = "chat_history_cleared"
        intent.payload_json = payload
        intent.status = "cancelled"
        intent.consumed_at = now
        intent.updated_at = now

    # Detach chat provenance so a later "delete everything from this chat"
    # cannot match records created in the previous, now-cleared conversation.
    db.execute(
        update(Transaction)
        .where(Transaction.user_id == user_id)
        .where(Transaction.source_message_id.isnot(None))
        .values(source_message_id=None)
    )
    db.execute(
        update(FutureCommitment)
        .where(FutureCommitment.user_id == user_id)
        .where(FutureCommitment.source_message_id.isnot(None))
        .values(source_message_id=None)
    )

    # Deactivate conversation-only reasoning state (exclusions, baselines,
    # stated balance). Persistent CFO facts survive.
    db.execute(
        update(FinancialFact)
        .where(FinancialFact.user_id == user_id)
        .where(FinancialFact.fact_type == CHAT_REASONING_FACT_TYPE)
        .where(FinancialFact.is_active.is_(True))
        .values(is_active=False)
    )

    cleared_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .delete(synchronize_session=False)
    )

    db.commit()
    return ChatClearResult(
        cleared_messages=cleared_messages,
        cancelled_pending_intents=len(active_intents),
        cancelled_advisory_sessions=cancelled_advisory_sessions,
    )
