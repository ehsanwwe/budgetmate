from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.agent_idempotency import PendingAgentIntent
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
