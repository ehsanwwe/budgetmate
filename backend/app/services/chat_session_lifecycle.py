from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.agent_idempotency import PendingAgentIntent
from app.models.chat import ChatMessage
from app.services.agent_orchestrator.goal_intake import STATE_CANCELLED, STATE_CONSULTATION


@dataclass(frozen=True)
class ChatClearResult:
    cleared_messages: int
    cancelled_pending_intents: int
    cancelled_advisory_sessions: int


def clear_chat_history_and_transient_state(db: Session, user_id: int) -> ChatClearResult:
    """Clear user-visible chat history and cancel transient conversation state.

    Durable financial records, CFO memories/facts/persona, goals, commitments,
    budgets, and audit logs are intentionally left untouched.
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
