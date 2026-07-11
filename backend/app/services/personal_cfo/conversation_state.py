"""Per-conversation reasoning state persisted in ``financial_facts``.

Purpose
-------
When a user says things like «قبلی‌ها رو حساب نکن» or "start over from here",
the assistant must remember that decision across turns in the same
conversation — but must not delete persistent financial records unless the
user explicitly asked to delete them.

The state is stored in the existing ``financial_facts`` table under the
reserved ``fact_type = "chat_reasoning_state"`` with ``is_active = True``.

On chat clear (``clear_chat_history_and_transient_state``), these facts are
deactivated so a new conversation starts from a clean baseline.

This module is NOT an intent router. It only reads and writes structured
state that the LLM planner can also read/write via existing SQL tools
against ``financial_facts``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.personal_cfo import FinancialFact

CHAT_REASONING_FACT_TYPE = "chat_reasoning_state"
CHAT_REASONING_SUBJECT = "conversation"


@dataclass
class ChatReasoningState:
    excluded_transaction_ids: list[int] = field(default_factory=list)
    excluded_commitment_ids: list[int] = field(default_factory=list)
    reasoning_baseline_at: str | None = None
    stated_balance: int | None = None
    stated_balance_at: str | None = None
    assumptions: list[dict[str, Any]] = field(default_factory=list)
    invalidated_amounts: list[dict[str, Any]] = field(default_factory=list)
    disclosed_debts: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "excluded_transaction_ids": list(self.excluded_transaction_ids),
            "excluded_commitment_ids": list(self.excluded_commitment_ids),
            "reasoning_baseline_at": self.reasoning_baseline_at,
            "stated_balance": self.stated_balance,
            "stated_balance_at": self.stated_balance_at,
            "assumptions": list(self.assumptions),
            "invalidated_amounts": list(self.invalidated_amounts),
            "disclosed_debts": list(self.disclosed_debts),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> "ChatReasoningState":
        data = data or {}
        return cls(
            excluded_transaction_ids=[int(x) for x in (data.get("excluded_transaction_ids") or [])],
            excluded_commitment_ids=[int(x) for x in (data.get("excluded_commitment_ids") or [])],
            reasoning_baseline_at=data.get("reasoning_baseline_at"),
            stated_balance=(
                int(data["stated_balance"]) if data.get("stated_balance") is not None else None
            ),
            stated_balance_at=data.get("stated_balance_at"),
            assumptions=list(data.get("assumptions") or []),
            invalidated_amounts=list(data.get("invalidated_amounts") or []),
            disclosed_debts=list(data.get("disclosed_debts") or []),
        )


def get_active_state(db: Session, user_id: int) -> ChatReasoningState:
    """Merge all active ``chat_reasoning_state`` facts into one state.

    Later rows override earlier rows for the ``stated_balance`` /
    ``reasoning_baseline_at`` scalar fields; list fields (exclusions,
    disclosed debts, assumptions) are union-merged. This lets the LLM
    accumulate exclusions by inserting small delta rows via the existing
    ``INSERT INTO financial_facts`` tool without needing to first fetch
    and re-serialize the whole state.
    """
    rows = (
        db.query(FinancialFact)
        .filter(
            FinancialFact.user_id == user_id,
            FinancialFact.fact_type == CHAT_REASONING_FACT_TYPE,
            FinancialFact.is_active.is_(True),
        )
        .order_by(FinancialFact.updated_at.asc())
        .all()
    )
    merged = ChatReasoningState()
    excluded_tx: set[int] = set()
    excluded_com: set[int] = set()
    for row in rows:
        payload = row.value_json if isinstance(row.value_json, dict) else {}
        partial = ChatReasoningState.from_json(payload)
        excluded_tx.update(partial.excluded_transaction_ids)
        excluded_com.update(partial.excluded_commitment_ids)
        if partial.reasoning_baseline_at:
            merged.reasoning_baseline_at = partial.reasoning_baseline_at
        if partial.stated_balance is not None:
            merged.stated_balance = partial.stated_balance
            merged.stated_balance_at = partial.stated_balance_at
        merged.assumptions.extend(partial.assumptions)
        merged.disclosed_debts.extend(partial.disclosed_debts)
        merged.invalidated_amounts.extend(partial.invalidated_amounts)
    merged.excluded_transaction_ids = sorted(excluded_tx)
    merged.excluded_commitment_ids = sorted(excluded_com)
    return merged


def upsert_state(
    db: Session, user_id: int, state: ChatReasoningState, source_message_id: int | None = None
) -> FinancialFact:
    """Store ``state`` as the single active chat_reasoning_state row.

    Any previously active row is deactivated so exactly one row is authoritative.
    """
    active = (
        db.query(FinancialFact)
        .filter(
            FinancialFact.user_id == user_id,
            FinancialFact.fact_type == CHAT_REASONING_FACT_TYPE,
            FinancialFact.is_active.is_(True),
        )
        .all()
    )
    for row in active:
        row.is_active = False
        row.updated_at = datetime.utcnow()
    fresh = FinancialFact(
        user_id=user_id,
        fact_type=CHAT_REASONING_FACT_TYPE,
        subject=CHAT_REASONING_SUBJECT,
        value_json=state.to_json(),
        source_message_id=source_message_id,
        confidence=1.0,
        is_active=True,
    )
    db.add(fresh)
    db.commit()
    db.refresh(fresh)
    return fresh


def exclude_transactions(
    db: Session, user_id: int, transaction_ids: list[int], source_message_id: int | None = None
) -> ChatReasoningState:
    state = get_active_state(db, user_id)
    combined = set(state.excluded_transaction_ids) | {int(x) for x in transaction_ids}
    state.excluded_transaction_ids = sorted(combined)
    upsert_state(db, user_id, state, source_message_id=source_message_id)
    return state


def set_stated_balance(
    db: Session,
    user_id: int,
    amount: int,
    at: datetime | None = None,
    source_message_id: int | None = None,
) -> ChatReasoningState:
    state = get_active_state(db, user_id)
    state.stated_balance = int(amount)
    state.stated_balance_at = (at or datetime.utcnow()).isoformat()
    upsert_state(db, user_id, state, source_message_id=source_message_id)
    return state


def add_assumption(
    db: Session,
    user_id: int,
    assumption: dict[str, Any],
    source_message_id: int | None = None,
) -> ChatReasoningState:
    state = get_active_state(db, user_id)
    state.assumptions.append({**assumption, "at": datetime.utcnow().isoformat()})
    upsert_state(db, user_id, state, source_message_id=source_message_id)
    return state


def add_disclosed_debt(
    db: Session,
    user_id: int,
    debt: dict[str, Any],
    source_message_id: int | None = None,
) -> ChatReasoningState:
    state = get_active_state(db, user_id)
    state.disclosed_debts.append({**debt, "at": datetime.utcnow().isoformat()})
    upsert_state(db, user_id, state, source_message_id=source_message_id)
    return state


def set_reasoning_baseline(
    db: Session,
    user_id: int,
    at: datetime | None = None,
    source_message_id: int | None = None,
) -> ChatReasoningState:
    state = get_active_state(db, user_id)
    state.reasoning_baseline_at = (at or datetime.utcnow()).isoformat()
    upsert_state(db, user_id, state, source_message_id=source_message_id)
    return state
