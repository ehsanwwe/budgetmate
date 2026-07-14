"""Deterministic rollback of chat-message-triggered financial side effects.

Used by chat_session_lifecycle when a prior user message is edited. Rollback
resolves what to undo through persisted provenance (source_message_id on
transactions, future_commitments, financial_facts, pending_agent_intents,
agent_operation_events) — the LLM is never asked to remember or generate
DELETE SQL during this path.

This module is INTERNAL. It is not exposed to the LLM's SQL tool surface.
The rollback service receives already-authenticated user + message ids
resolved by the edit endpoint, so record identity is authoritative and no
arbitrary SQL is accepted.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable

from sqlalchemy import text, update
from sqlalchemy.orm import Session

from app.models.agent_idempotency import AgentOperationEvent, PendingAgentIntent
from app.models.future_commitment import FutureCommitment
from app.models.personal_cfo import (
    BehaviorInsight,
    FinancialDecisionLog,
    FinancialFact,
    FinancialMemory,
    FinancialPersona,
    FinancialWarning,
)
from app.models.goal import Goal
from app.models.transaction import Transaction, TransactionType
from app.services.agent_orchestrator.goal_intake import STATE_CANCELLED

logger = logging.getLogger(__name__)


# Tables whose INSERTs the LLM can perform. We restore/re-insert only known
# tables so rollback never touches unrelated data.
_INSERTABLE_TABLES = {
    "transactions",
    "future_commitments",
    "financial_facts",
    "financial_memories",
    "behavior_insights",
    "financial_warnings",
    "financial_decision_logs",
    "goals",
}

_UPDATEABLE_TABLES = {
    "goals",
    "future_commitments",
    "financial_personas",
    "financial_memories",
    "behavior_insights",
    "financial_facts",
    "financial_warnings",
}


@dataclass(frozen=True)
class RollbackResult:
    deleted_transactions: int = 0
    deleted_future_commitments: int = 0
    deleted_financial_facts: int = 0
    deleted_goals: int = 0
    deleted_other_records: int = 0
    restored_updates: int = 0
    restored_deletes: int = 0
    cancelled_pending_intents: int = 0
    superseded_events: int = 0
    validation_errors: list[str] = field(default_factory=list)


class ChatBranchRollbackError(Exception):
    """Raised when rollback validation fails and the edit must be aborted."""


def rollback_chat_branch_side_effects(
    db: Session,
    user_id: int,
    message_ids: Iterable[int],
) -> RollbackResult:
    """Roll back all persistent side effects produced by the given chat messages.

    The caller (chat_session_lifecycle.edit_chat_message_and_truncate) owns
    the database transaction and is responsible for commit/rollback around
    this call. This function only issues data-modifying statements; it does
    not commit.
    """
    msg_ids = [int(mid) for mid in message_ids if mid is not None]
    if not msg_ids:
        return RollbackResult()

    result = RollbackResult()
    now = datetime.utcnow()

    # 1) Resolve chat-provenanced records that were CREATED by the branch.
    #    These deletes are keyed by source_message_id AND user_id so manual
    #    UI-created rows (source_message_id IS NULL) are never touched.
    tx_deleted = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .filter(Transaction.source_message_id.in_(msg_ids))
        .delete(synchronize_session="fetch")
    )
    result = _replace(result, deleted_transactions=tx_deleted)

    fc_deleted = (
        db.query(FutureCommitment)
        .filter(FutureCommitment.user_id == user_id)
        .filter(FutureCommitment.source_message_id.in_(msg_ids))
        .delete(synchronize_session="fetch")
    )
    result = _replace(result, deleted_future_commitments=fc_deleted)

    ff_deleted = (
        db.query(FinancialFact)
        .filter(FinancialFact.user_id == user_id)
        .filter(FinancialFact.source_message_id.in_(msg_ids))
        .delete(synchronize_session="fetch")
    )
    result = _replace(result, deleted_financial_facts=ff_deleted)

    # 2) Resolve operation-event provenanced records. This covers INSERTs
    #    into tables that don't carry source_message_id on the row itself
    #    (goals, memories, insights, warnings, decision logs), plus provides
    #    UPDATE/DELETE snapshots to restore.
    events = (
        db.query(AgentOperationEvent)
        .filter(AgentOperationEvent.user_id == user_id)
        .filter(AgentOperationEvent.source_message_id.in_(msg_ids))
        .filter(AgentOperationEvent.status == "executed")
        .order_by(AgentOperationEvent.created_at.desc(), AgentOperationEvent.id.desc())
        .all()
    )
    for event in events:
        try:
            deleted_extra = _rollback_single_event(db, user_id, event, result)
            result = deleted_extra
        except Exception as exc:  # pragma: no cover — logged and propagated
            logger.exception(
                "chat-edit rollback failed on event %s (%s %s): %s",
                event.id,
                event.operation_type,
                event.table_name,
                exc,
            )
            raise ChatBranchRollbackError(str(exc)) from exc

        event.status = "superseded_by_edit"
        event.payload_json = {
            **(event.payload_json or {}),
            "superseded_at": now.isoformat(),
        }
        result = _replace(result, superseded_events=result.superseded_events + 1)

    # 3) Cancel pending agent intents linked to the branch. We match on
    #    source_message_id first (deterministic), then fall back to intents
    #    created/updated during or after the removed messages.
    pending = (
        db.query(PendingAgentIntent)
        .filter(PendingAgentIntent.user_id == user_id)
        .filter(PendingAgentIntent.status == "pending")
        .filter(PendingAgentIntent.source_message_id.in_(msg_ids))
        .all()
    )
    for intent in pending:
        payload = dict(intent.payload_json or {})
        payload["state"] = STATE_CANCELLED
        payload["cancelled_reason"] = "chat_message_edited"
        intent.payload_json = payload
        intent.status = "cancelled"
        intent.consumed_at = now
        intent.updated_at = now
        intent.source_message_id = None
    result = _replace(result, cancelled_pending_intents=len(pending))

    # 4) Also mark request_guard events (client_message_id idempotency) tied
    #    to removed messages as superseded, so a duplicate submission of the
    #    old cmid does NOT replay the stale assistant response.
    guard_events = (
        db.query(AgentOperationEvent)
        .filter(AgentOperationEvent.user_id == user_id)
        .filter(AgentOperationEvent.operation_type == "request_guard")
        .filter(AgentOperationEvent.source_message_id.in_(msg_ids))
        .all()
    )
    for event in guard_events:
        event.status = "superseded_by_edit"
        payload = dict(event.payload_json or {})
        payload["superseded_at"] = now.isoformat()
        event.payload_json = payload

    return result


def _replace(result: RollbackResult, **kwargs: Any) -> RollbackResult:
    data = {
        "deleted_transactions": result.deleted_transactions,
        "deleted_future_commitments": result.deleted_future_commitments,
        "deleted_financial_facts": result.deleted_financial_facts,
        "deleted_goals": result.deleted_goals,
        "deleted_other_records": result.deleted_other_records,
        "restored_updates": result.restored_updates,
        "restored_deletes": result.restored_deletes,
        "cancelled_pending_intents": result.cancelled_pending_intents,
        "superseded_events": result.superseded_events,
        "validation_errors": list(result.validation_errors),
    }
    data.update(kwargs)
    return RollbackResult(**data)


def _rollback_single_event(
    db: Session,
    user_id: int,
    event: AgentOperationEvent,
    result: RollbackResult,
) -> RollbackResult:
    """Reverse a single agent operation, using its stored payload."""
    op = (event.operation_type or "").lower()
    table = (event.table_name or "").lower()
    if op == "insert":
        return _rollback_insert(db, user_id, event, result)
    if op == "update":
        return _rollback_update(db, user_id, event, result)
    if op == "delete":
        return _rollback_delete(db, user_id, event, result)
    # request_guard and unknown events don't need entity rollback.
    return result


def _rollback_insert(
    db: Session,
    user_id: int,
    event: AgentOperationEvent,
    result: RollbackResult,
) -> RollbackResult:
    """Delete a row that was inserted by the removed chat branch."""
    table = (event.table_name or "").lower()
    if table not in _INSERTABLE_TABLES:
        result.validation_errors.append(f"unknown insert table {table}")
        return result
    target_id = event.target_record_id
    if target_id is None:
        return result

    row_deleted = db.execute(
        text(f"DELETE FROM {table} WHERE id = :id AND user_id = :uid"),
        {"id": int(target_id), "uid": user_id},
    ).rowcount or 0

    if row_deleted <= 0:
        # Already gone (e.g. concurrent deletion or DB constraint). Not fatal.
        return result

    if table == "transactions":
        return _replace(result, deleted_transactions=result.deleted_transactions + row_deleted)
    if table == "future_commitments":
        return _replace(result, deleted_future_commitments=result.deleted_future_commitments + row_deleted)
    if table == "financial_facts":
        return _replace(result, deleted_financial_facts=result.deleted_financial_facts + row_deleted)
    if table == "goals":
        return _replace(result, deleted_goals=result.deleted_goals + row_deleted)
    return _replace(result, deleted_other_records=result.deleted_other_records + row_deleted)


def _rollback_update(
    db: Session,
    user_id: int,
    event: AgentOperationEvent,
    result: RollbackResult,
) -> RollbackResult:
    """Restore the pre-update column values for the target row."""
    table = (event.table_name or "").lower()
    if table not in _UPDATEABLE_TABLES:
        result.validation_errors.append(f"unknown update table {table}")
        return result
    payload = event.payload_json or {}
    before = payload.get("before") if isinstance(payload, dict) else None
    if not isinstance(before, dict) or not before:
        # No snapshot was captured; safest is to leave the row as-is rather
        # than approximate a rollback. Log the gap so future work can
        # backfill snapshots for the affected table.
        logger.info(
            "chat-edit rollback: no before-state for %s update event id=%s",
            table,
            event.id,
        )
        result.validation_errors.append(
            f"missing before snapshot for {table} update event {event.id}"
        )
        return result

    target_id = event.target_record_id
    if target_id is None:
        return result

    restored = _restore_row(db, user_id, table, int(target_id), before)
    if restored:
        return _replace(result, restored_updates=result.restored_updates + 1)
    return result


def _rollback_delete(
    db: Session,
    user_id: int,
    event: AgentOperationEvent,
    result: RollbackResult,
) -> RollbackResult:
    """Re-insert rows that were deleted by the removed chat branch.

    Only tables the LLM can DELETE from (currently: future_commitments) go
    through this path. Re-insertion uses the snapshot's original id so
    downstream references remain intact.
    """
    table = (event.table_name or "").lower()
    if table != "future_commitments":
        # transactions delete via LLM is disabled; other tables are not
        # LLM-deletable. Nothing to restore for now.
        return result

    payload = event.payload_json or {}
    rows = payload.get("before_rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        result.validation_errors.append(
            f"missing before_rows snapshot for {table} delete event {event.id}"
        )
        return result

    restored_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = row.get("id")
        if row_id is None:
            continue
        # Re-insert only if the row was actually removed
        exists = db.execute(
            text(f"SELECT id FROM {table} WHERE id = :id AND user_id = :uid"),
            {"id": int(row_id), "uid": user_id},
        ).first()
        if exists:
            continue
        try:
            _reinsert_future_commitment(db, user_id, row)
            restored_count += 1
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "chat-edit rollback: failed to re-insert %s row id=%s: %s",
                table,
                row_id,
                exc,
            )
            result.validation_errors.append(
                f"failed to restore {table} row id={row_id}"
            )

    if restored_count:
        return _replace(result, restored_deletes=result.restored_deletes + restored_count)
    return result


def _restore_row(
    db: Session, user_id: int, table: str, row_id: int, before: dict[str, Any]
) -> bool:
    """Apply the before-state snapshot column values to the target row."""
    model_map = {
        "goals": Goal,
        "future_commitments": FutureCommitment,
        "financial_personas": FinancialPersona,
        "financial_memories": FinancialMemory,
        "behavior_insights": BehaviorInsight,
        "financial_facts": FinancialFact,
        "financial_warnings": FinancialWarning,
    }
    model = model_map.get(table)
    if model is None:
        return False
    row = db.query(model).filter(model.id == row_id, model.user_id == user_id).first()
    if row is None:
        return False
    for column, value in before.items():
        if column == "id":
            continue
        if not hasattr(row, column):
            continue
        setattr(row, column, _coerce_value(model, column, value))
    return True


def _coerce_value(model: Any, column_name: str, value: Any) -> Any:
    """Best-effort coercion from JSON snapshot value back to a column type."""
    if value is None:
        return None
    col = getattr(model, column_name, None)
    col_type = None
    if col is not None and hasattr(col, "type"):
        col_type = str(getattr(col, "type", "")).lower()
    # Date/datetime revive
    if col_type and "date" in col_type and isinstance(value, str):
        try:
            if "time" in col_type:
                return datetime.fromisoformat(value)
            return date.fromisoformat(value)
        except ValueError:
            return value
    # Transaction type revive
    if column_name == "type" and model.__tablename__ == "transactions":
        if isinstance(value, str):
            try:
                return TransactionType(value)
            except ValueError:
                return value
    return value


def _reinsert_future_commitment(db: Session, user_id: int, row: dict[str, Any]) -> None:
    """Re-materialize a deleted future_commitment from its snapshot."""
    fc = FutureCommitment(
        id=int(row["id"]),
        user_id=user_id,
        title=str(row.get("title") or ""),
        amount=int(row.get("amount") or 0),
        due_date=_coerce_value(FutureCommitment, "due_date", row.get("due_date")),
        due_month=row.get("due_month"),
        category_id=row.get("category_id"),
        related_transaction_id=row.get("related_transaction_id"),
        related_goal_id=row.get("related_goal_id"),
        description=row.get("description"),
        status=str(row.get("status") or "pending"),
        source=str(row.get("source") or "chat"),
        metadata_json=row.get("metadata_json"),
        source_message_id=None,
    )
    db.add(fc)
