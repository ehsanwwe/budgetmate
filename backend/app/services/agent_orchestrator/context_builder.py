from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.finance_context import build_finance_context
from app.services.personal_cfo.cfo_context_builder import build_cfo_context


def build_agent_context(user: User, db: Session) -> dict:
    context = build_finance_context(user, db)
    payload = {
        "user": {
            "id": user.id,
            "name": user.display_name or user.name,
            "income_range": context["user"].get("income_range"),
            "monthly_income": context["user"].get("monthly_income"),
            "chat_mode": context["user"].get("chat_mode"),
        },
        "current_gregorian_date": context["current_gregorian_date"],
        "current_jalali_month": context["current_jalali_month"],
        "current_jalali_year": context["current_jalali_year"],
        "budget": context["budget"],
        "total_spent_this_month": context["total_spent_this_month"],
        "total_income_this_month": context["total_income_this_month"],
        "remaining_budget": context["remaining_budget"],
        "top_expense_categories": context["top_expense_categories"],
        "active_goals": context["active_goals"][:5],
        "recent_transactions": context["recent_transactions"][:5],
    }
    payload["personal_cfo"] = build_cfo_context(db, user.id)
    return payload
