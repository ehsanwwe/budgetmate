from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.models.agent_idempotency import AgentOperationEvent, PendingAgentIntent
from app.models.activity import ActivityLog
from app.models.chat import ChatMessage
from app.models.future_commitment import FutureCommitment
from app.models.personal_cfo import FinancialFact
from app.models.transaction import Transaction
from app.services.agent_orchestrator.goal_intake import STATE_CANCELLED, STATE_CONSULTATION
from app.services.chat_edit_rollback import (
    ChatBranchRollbackError,
    RollbackResult,
    rollback_chat_branch_side_effects,
)

# fact_type reserved for per-conversation reasoning state (exclusions,
# baselines, user-stated balance). See personal_cfo/conversation_state.py.
CHAT_REASONING_FACT_TYPE = "chat_reasoning_state"

logger = logging.getLogger(__name__)

# Operation type used to guard against duplicate chat-edit submissions.
EDIT_GUARD_OPERATION_TYPE = "chat_edit_guard"
# How long we consider an identical edit re-submission to be a duplicate.
EDIT_GUARD_WINDOW_MINUTES = 30


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
    rollback: RollbackResult = field(default_factory=RollbackResult)
    duplicate_edit: bool = False


class ChatMessageNotFoundError(Exception):
    pass


class ChatMessageNotEditableError(Exception):
    pass


class ChatEditRollbackFailedError(Exception):
    """Rollback validation failed; the edit was aborted and the branch preserved."""


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


def _edit_fingerprint(user_id: int, message_id: int, content: str) -> str:
    raw = f"edit:{user_id}:{message_id}:{content.strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def _find_recent_duplicate_edit(
    db: Session, user_id: int, fingerprint: str
) -> AgentOperationEvent | None:
    from datetime import timedelta

    window_start = datetime.utcnow() - timedelta(minutes=EDIT_GUARD_WINDOW_MINUTES)
    return (
        db.query(AgentOperationEvent)
        .filter(
            AgentOperationEvent.user_id == user_id,
            AgentOperationEvent.operation_fingerprint == fingerprint,
            AgentOperationEvent.operation_type == EDIT_GUARD_OPERATION_TYPE,
            AgentOperationEvent.created_at >= window_start,
        )
        .order_by(AgentOperationEvent.created_at.desc())
        .first()
    )


def _record_edit_guard(
    db: Session,
    user_id: int,
    fingerprint: str,
    target_message_id: int,
    rollback: RollbackResult,
) -> None:
    event = AgentOperationEvent(
        user_id=user_id,
        operation_fingerprint=fingerprint,
        operation_type=EDIT_GUARD_OPERATION_TYPE,
        table_name="chat_messages",
        target_record_id=target_message_id,
        status="executed",
        payload_json={
            "deleted_transactions": rollback.deleted_transactions,
            "deleted_future_commitments": rollback.deleted_future_commitments,
            "deleted_financial_facts": rollback.deleted_financial_facts,
            "restored_updates": rollback.restored_updates,
            "cancelled_pending_intents": rollback.cancelled_pending_intents,
            "superseded_events": rollback.superseded_events,
        },
        source_message_id=target_message_id,
    )
    db.add(event)


def edit_chat_message_and_truncate(
    db: Session, user_id: int, message_id: int, content: str
) -> ChatEditResult:
    """Replace one user message and atomically roll back its side effects.

    Rollback is deterministic (uses persisted provenance and operation
    events); the LLM is not asked to remember or reason about undo.
    """
    target = (
        db.query(ChatMessage)
        .filter(ChatMessage.id == message_id, ChatMessage.user_id == user_id)
        .first()
    )
    if target is None:
        raise ChatMessageNotFoundError
    if target.role.value != "user":
        raise ChatMessageNotEditableError

    fingerprint = _edit_fingerprint(user_id, message_id, content)
    duplicate = _find_recent_duplicate_edit(db, user_id, fingerprint)
    if duplicate is not None:
        # Return without re-running rollback. The target message already
        # holds the edited content from the previous submission.
        return ChatEditResult(
            message=target,
            removed_messages=0,
            history=_history_before_message(db, user_id, target),
            duplicate_edit=True,
        )

    later_rows = (
        db.query(ChatMessage.id)
        .filter(ChatMessage.user_id == user_id)
        .filter(_is_after_message(target))
        .all()
    )
    later_ids = [row.id for row in later_rows]
    branch_ids = [target.id] + later_ids
    now = datetime.utcnow()

    try:
        try:
            rollback_result = rollback_chat_branch_side_effects(db, user_id, branch_ids)
        except ChatBranchRollbackError as exc:
            db.rollback()
            raise ChatEditRollbackFailedError(str(exc)) from exc

        # Cancel any pending intents that were created/updated during the
        # replaced branch time window but that carry no source_message_id
        # (older intents predating provenance). Keeping them would let the
        # regenerated branch inherit stale reasoning state.
        legacy_intents = (
            db.query(PendingAgentIntent)
            .filter(
                PendingAgentIntent.user_id == user_id,
                PendingAgentIntent.status == "pending",
                PendingAgentIntent.source_message_id.is_(None),
                or_(
                    PendingAgentIntent.created_at >= target.created_at,
                    PendingAgentIntent.updated_at >= target.created_at,
                ),
            )
            .all()
        )
        for intent in legacy_intents:
            payload = dict(intent.payload_json or {})
            payload["state"] = STATE_CANCELLED
            payload["cancelled_reason"] = "chat_message_edited"
            intent.payload_json = payload
            intent.status = "cancelled"
            intent.consumed_at = now
            intent.updated_at = now

        # Deactivate chat reasoning-state facts that survived because they
        # predate source_message_id provenance and reference the removed
        # branch by timestamp.
        db.execute(
            update(FinancialFact)
            .where(FinancialFact.user_id == user_id)
            .where(FinancialFact.fact_type == CHAT_REASONING_FACT_TYPE)
            .where(FinancialFact.source_message_id.is_(None))
            .where(FinancialFact.created_at >= target.created_at)
            .where(FinancialFact.is_active.is_(True))
            .values(is_active=False)
        )

        target.content = content
        removed_messages = 0
        if later_ids:
            removed_messages = (
                db.query(ChatMessage)
                .filter(ChatMessage.user_id == user_id, ChatMessage.id.in_(later_ids))
                .delete(synchronize_session="fetch")
            )

        _record_edit_guard(db, user_id, fingerprint, target.id, rollback_result)

        db.add(
            ActivityLog(
                user_id=user_id,
                action="chat_message_edited",
                meta={
                    "message_id": message_id,
                    "removed_messages": removed_messages,
                    "deleted_transactions": rollback_result.deleted_transactions,
                    "deleted_future_commitments": rollback_result.deleted_future_commitments,
                    "deleted_financial_facts": rollback_result.deleted_financial_facts,
                    "restored_updates": rollback_result.restored_updates,
                    "cancelled_pending_intents": rollback_result.cancelled_pending_intents + len(legacy_intents),
                    "superseded_events": rollback_result.superseded_events,
                },
                created_at=now,
            )
        )
        db.commit()
        db.refresh(target)
    except ChatEditRollbackFailedError:
        raise
    except Exception:
        db.rollback()
        raise

    return ChatEditResult(
        message=target,
        removed_messages=removed_messages,
        history=_history_before_message(db, user_id, target),
        rollback=rollback_result,
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
