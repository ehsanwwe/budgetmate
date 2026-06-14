from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.budget import Budget
from app.models.future_commitment import FutureCommitment
from app.models.personal_cfo import FinancialWarning
from app.models.transaction import Transaction, TransactionType
from app.services.agent_orchestrator.date_utils import local_month_range, local_today
from app.services.personal_cfo.behavior_service import serialize_behavior_insights_for_agent
from app.services.personal_cfo.fact_service import serialize_facts_for_agent
from app.services.personal_cfo.future_commitment_service import serialize_commitments_for_agent
from app.services.personal_cfo.goal_context_service import serialize_goals_for_agent
from app.services.personal_cfo.memory_service import serialize_memories_for_agent
from app.services.personal_cfo.persona_service import serialize_persona_for_agent


def build_cfo_context(db: Session, user_id: int) -> dict:
    today = local_today()
    current_month_start, current_month_end = local_month_range(today)
    next_month_start, next_month_end = local_month_range(current_month_end)
    next_year_end = date(today.year + 1, today.month, today.day)
    return {
        "persona": serialize_persona_for_agent(db, user_id),
        "active_goals": serialize_goals_for_agent(db, user_id),
        "memories": serialize_memories_for_agent(db, user_id),
        "behavior_insights": serialize_behavior_insights_for_agent(db, user_id),
        "facts": serialize_facts_for_agent(db, user_id),
        "warnings": _serialize_warnings(db, user_id),
        "future_commitments": serialize_commitments_for_agent(db, user_id),
        "next_month_commitments": serialize_commitments_for_agent(db, user_id, from_date=next_month_start, to_date=next_month_end),
        "commitments_until_next_year": serialize_commitments_for_agent(db, user_id, from_date=today, to_date=next_year_end),
        "current_month_budget_summary": _budget_summary(db, user_id, current_month_start, current_month_end),
    }


def build_personal_cfo_context(db: Session, user_id: int) -> dict:
    return build_cfo_context(db, user_id)


def _serialize_warnings(db: Session, user_id: int) -> list[dict]:
    rows = db.query(FinancialWarning).filter(
        FinancialWarning.user_id == user_id,
        FinancialWarning.status == "active",
    ).order_by(FinancialWarning.created_at.desc(), FinancialWarning.id.desc()).limit(5).all()
    return [
        {
            "warning_type": row.warning_type,
            "severity": row.severity,
            "message": row.message,
            "confidence_source": row.evidence_json,
        }
        for row in rows
    ]


def _budget_summary(db: Session, user_id: int, start: date, end: date) -> dict:
    budget = db.query(Budget).filter(Budget.user_id == user_id).order_by(Budget.year.desc(), Budget.month.desc()).first()
    expenses = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id,
        Transaction.type == TransactionType.expense,
        Transaction.date >= start,
        Transaction.date < end,
    ).scalar() or 0
    income = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id,
        Transaction.type == TransactionType.income,
        Transaction.date >= start,
        Transaction.date < end,
    ).scalar() or 0
    budget_amount = int(budget.amount) if budget else 0
    pending_commitments = db.query(func.sum(FutureCommitment.amount)).filter(
        FutureCommitment.user_id == user_id,
        FutureCommitment.status == "pending",
        FutureCommitment.due_date >= start,
        FutureCommitment.due_date < end,
    ).scalar() or 0
    return {
        "budget_amount": budget_amount,
        "income": int(income),
        "expenses": int(expenses),
        "remaining_budget": int(budget_amount - expenses),
        "pending_commitments": int(pending_commitments),
    }
