from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Optional
from sqlalchemy.orm import Session
from app.models.category import Category
from app.models.goal import Goal
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.services.ai import get_ai_reply
from app.services.finance_context import build_finance_context
from app.services.money_parser import format_toman, normalize_digits, parse_money

CATEGORY_HINTS = {
    "غذا و خوراک": ["ناهار", "شام", "صبحانه", "رستوران", "خوراک", "غذا", "کافه", "قهوه"],
    "حمل و نقل": ["تاکسی", "اسنپ", "بنزین", "مترو", "اتوبوس", "آژانس"],
    "قبوض و شارژ": ["قبض", "برق", "آب", "گاز", "شارژ", "اینترنت"],
    "خرید": ["خرید", "لباس", "سوپرمارکت", "فروشگاه"],
    "سرگرمی": ["فیلم", "بازی", "تفریح", "سرگرمی", "سینما"],
}

EXPENSE_WORDS = ["هزینه", "خرج", "خریدم", "پرداخت", "اضافه بکن", "اضافه کن", "ثبت کن"]
INCOME_WORDS = ["درآمد", "حقوق", "واریز", "دریافت"]
GOAL_WORDS = ["هدف", "گول", "پس انداز", "پس‌انداز"]


def _clean(text: str) -> str:
    return normalize_digits(text).replace("‌", " ").strip().lower()


def _money(amount: int) -> str:
    return format_toman(amount)


def _available_categories(user_id: int, db: Session) -> list[Category]:
    return db.query(Category).filter((Category.is_default == True) | (Category.user_id == user_id)).all()


def _match_category(message: str, categories: list[Category]) -> Optional[Category]:
    clean = _clean(message)
    for category in categories:
        if _clean(category.name) in clean:
            return category
    for canonical, hints in CATEGORY_HINTS.items():
        if any(hint in clean for hint in hints):
            for category in categories:
                if canonical in category.name or category.name in canonical:
                    return category
    return None


def _match_goal(message: str, goals: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    clean = _clean(message)
    matches = []
    for goal in goals:
        title = _clean(goal["title"])
        title_words = [word for word in title.split() if len(word) > 2]
        if title in clean or any(word in clean for word in title_words):
            matches.append(goal)
    return matches[0] if len(matches) == 1 else None


def _infer_description(message: str, category: Optional[Category]) -> Optional[str]:
    clean = _clean(message)
    for hints in CATEGORY_HINTS.values():
        for hint in hints:
            if hint in clean:
                return hint
    if category and category.name in message:
        return category.name
    without_amount = re.sub(r"[\d,\.]+\s*(هزار|میلیون|ملیون|میلیارد|تومان|تومن)?", "", clean).strip()
    for word in ["هزینه", "خرج", "اضافه", "بکن", "کن", "ثبت", "کردم", "درآمد", "واریز"]:
        without_amount = without_amount.replace(word, " ")
    compact = " ".join(without_amount.split())
    return compact or None


async def _llm_classify(message: str, context: dict) -> dict[str, Any]:
    prompt = (
        "فقط JSON معتبر برگردان. پیام کاربر را برای اپ مالی طبقه‌بندی کن. "
        "کلیدها: intent, confidence, amount, type, category_guess, description, goal_guess, "
        "needs_confirmation, missing_fields. intent یکی از create_transaction, create_income, "
        "goal_question, budget_question, spending_summary, category_analysis, contribute_to_goal, general, clarify باشد.\n"
        f"دسته‌ها: {[c['name'] for c in context['categories']]}\n"
        f"هدف‌ها: {[g['title'] for g in context['active_goals']]}\n"
        f"پیام: {message}"
    )
    try:
        raw = await get_ai_reply(prompt, context)
        match = re.search(r"\{.*\}", raw, re.S)
        return json.loads(match.group(0)) if match else {}
    except Exception:
        return {}


def _goal_answer(goal: dict[str, Any]) -> str:
    lines = [f"تا هدف «{goal['title']}» {_money(goal['remaining_amount'])} فاصله داری."]
    if goal.get("required_daily_saving"):
        lines.append(f"برای رسیدن به موعد، حدود {_money(goal['required_daily_saving'])} در روز باید کنار بگذاری.")
    return "\n".join(lines)


def _multiple_goals_reply(goals: list[dict[str, Any]]) -> str:
    lines = ["چند هدف فعال داری. منظورت کدام است؟"]
    lines.extend([f"{g['title']} — مانده: {_money(g['remaining_amount'])}" for g in goals])
    return "\n".join(lines)


async def handle_finance_message(message: str, user: User, db: Session) -> str:
    context = build_finance_context(user, db)
    clean = _clean(message)
    amount = parse_money(message)
    categories = _available_categories(user.id, db)
    category = _match_category(message, categories)
    description = _infer_description(message, category)
    goals = context["active_goals"]

    is_goal_message = any(word in clean for word in GOAL_WORDS)
    if is_goal_message and any(word in clean for word in ["فاصله", "مانده", "چقدر", "برسم", "روزی"]):
        if not goals:
            return "فعلا هدف فعالی ثبت نکردی."
        goal = _match_goal(message, goals)
        if goal:
            return _goal_answer(goal)
        if len(goals) == 1:
            return _goal_answer(goals[0])
        return _multiple_goals_reply(goals)

    if amount and is_goal_message and any(word in clean for word in ["اضافه", "کنار", "پس انداز", "پس‌انداز", "واریز"]):
        if not goals:
            return "برای ثبت پس‌انداز، اول یک هدف مالی بساز."
        goal_data = _match_goal(message, goals) or (goals[0] if len(goals) == 1 else None)
        if not goal_data:
            return _multiple_goals_reply(goals)
        goal = db.query(Goal).filter(Goal.id == goal_data["id"], Goal.user_id == user.id).first()
        goal.current_amount = min(goal.current_amount + amount, goal.target_amount)
        db.commit()
        remaining = max(goal.target_amount - goal.current_amount, 0)
        return f"ثبت شد: {_money(amount)} به هدف «{goal.title}» اضافه شد. مانده هدف: {_money(remaining)}."

    if amount and (any(word in clean for word in EXPENSE_WORDS) or any(word in clean for word in INCOME_WORDS)):
        tx_type = TransactionType.income if any(word in clean for word in INCOME_WORDS) else TransactionType.expense
        if tx_type == TransactionType.expense and not category:
            likely = "\n".join([f"- {cat.name}" for cat in categories[:5]])
            return f"این هزینه را در کدام دسته ثبت کنم؟\n{likely}"
        if not description and tx_type == TransactionType.expense:
            return "برای ثبت دقیق‌تر، توضیح کوتاه هزینه را بگو."

        txn = Transaction(
            user_id=user.id,
            category_id=category.id if category else None,
            amount=amount,
            type=tx_type,
            description=description or ("درآمد" if tx_type == TransactionType.income else "هزینه"),
            date=date.today(),
        )
        db.add(txn)
        db.commit()
        if tx_type == TransactionType.income:
            return f"ثبت شد: {_money(amount)} درآمد با توضیح «{txn.description}»."
        return f"ثبت شد: {_money(amount)} هزینه برای «{txn.description}» در دسته «{category.name}»."

    if any(term in clean for term in ["این ماه چقدر خرج", "خرج این ماه", "هزینه این ماه"]):
        return f"این ماه {_money(context['total_spent_this_month'])} خرج کرده‌ای."

    if any(term in clean for term in ["کجاها", "بیشتر پول", "دسته", "بیشترین خرج"]):
        if not context["top_expense_categories"]:
            return "برای این ماه هنوز هزینه‌ای ثبت نشده که بتوانم دسته‌ها را تحلیل کنم."
        lines = ["بیشترین هزینه‌های این ماه:"]
        lines.extend([f"{cat['name']}: {_money(cat['amount'])}" for cat in context["top_expense_categories"]])
        return "\n".join(lines)

    if any(term in clean for term in ["بودجه", "کافیه", "باقی مانده", "باقی‌مانده"]):
        budget = context["budget"]["amount"]
        spent = context["total_spent_this_month"]
        remaining = context["remaining_budget"]
        return f"بودجه ماهانه‌ات {_money(budget)} است. تا الان {_money(spent)} خرج کرده‌ای و مانده بودجه {_money(remaining)} است."

    classified = await _llm_classify(message, context)
    if classified.get("intent") in {"create_transaction", "create_income"} and amount:
        return "برای ثبت تراکنش، لطفا دسته یا توضیح را هم مشخص کن."

    return await get_ai_reply(message, context)
