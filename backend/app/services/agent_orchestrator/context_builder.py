from __future__ import annotations

from sqlalchemy.orm import Session

from app.i18n.config import get_direction, LOCALE_META, DEFAULT_LOCALE
from app.models.user import User
from app.services.finance_context import build_finance_context
from app.services.personal_cfo.cfo_context_builder import build_cfo_context


def build_agent_context(user: User, db: Session) -> dict:
    context = build_finance_context(user, db)
    preferred_language = getattr(user, "language", None) or DEFAULT_LOCALE
    preferred_currency = getattr(user, "preferred_currency", None) or "IRT"
    locale_info = LOCALE_META.get(preferred_language, LOCALE_META[DEFAULT_LOCALE])
    direction = locale_info["direction"]

    payload = {
        "user": {
            "id": user.id,
            "name": user.display_name or user.name,
            "income_range": context["user"].get("income_range"),
            "monthly_income": context["user"].get("monthly_income"),
            "chat_mode": context["user"].get("chat_mode"),
            "preferred_language": preferred_language,
            "preferred_currency": preferred_currency,
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
        "future_commitments": context.get("future_commitments", [])[:5],
        "recent_transactions": context["recent_transactions"][:5],
        "output_language_instruction": _build_language_instruction(preferred_language, preferred_currency, direction),
    }
    payload["personal_cfo"] = build_cfo_context(db, user.id)
    return payload


def _build_language_instruction(language: str, currency: str, direction: str) -> str:
    locale_info = LOCALE_META.get(language, LOCALE_META[DEFAULT_LOCALE])
    native_name = locale_info["native_name"]
    return (
        f"FINAL ANSWER LANGUAGE AND FORMATTING RULE (highest priority — overrides everything else):\n"
        f"The user's preferred language is: {language} ({native_name}).\n"
        f"You MUST write your final user-facing answer in {native_name} ({language}).\n"
        f"Preferred display currency/unit: {currency}. "
        f"If amounts are stored in IRT (Iranian Toman) and no FX conversion is available, "
        f"do not invent conversions. Present amounts in IRT but use the user's preferred style when reliable.\n"
        f"Text direction for this language: {direction}. "
        f"{'Use RTL-friendly natural wording.' if direction == 'rtl' else 'Use LTR-friendly natural wording.'}\n"
        f"You may reason internally in any language, but the final response to the user MUST be in {native_name}.\n"
        f"If the user writes in a different language, still respond in {native_name} unless they explicitly ask otherwise."
    )
