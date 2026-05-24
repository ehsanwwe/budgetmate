from __future__ import annotations

import calendar
from datetime import date
from sqlalchemy import func, desc
from sqlalchemy.orm import Session, joinedload
from app.core.jalali import current_jalali_month, gregorian_to_jalali
from app.models.budget import Budget
from app.models.category import Category
from app.models.goal import Goal
from app.models.transaction import Transaction, TransactionType
from app.models.user import User


def _month_range() -> tuple[date, date]:
    today = date.today()
    start = date(today.year, today.month, 1)
    end = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
    return start, end


def _goal_payload(goal: Goal, today: date) -> dict:
    remaining = max(goal.target_amount - goal.current_amount, 0)
    days_left = (goal.deadline - today).days if goal.deadline else None
    return {
        "id": goal.id,
        "title": goal.title,
        "target_amount": goal.target_amount,
        "current_amount": goal.current_amount,
        "remaining_amount": remaining,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "progress_percent": round((goal.current_amount / goal.target_amount * 100), 1) if goal.target_amount else 0,
        "required_daily_saving": int(remaining / days_left) if days_left and days_left > 0 else None,
    }


def build_finance_context(user: User, db: Session) -> dict:
    today = date.today()
    jm, jy = current_jalali_month()
    _, _, jalali_day = gregorian_to_jalali(today.year, today.month, today.day)
    start, end = _month_range()

    budget = db.query(Budget).filter(Budget.user_id == user.id, Budget.month == jm, Budget.year == jy).first()
    budget_amount = budget.amount if budget else 0

    spent = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user.id,
        Transaction.type == TransactionType.expense,
        Transaction.date >= start,
        Transaction.date < end,
    ).scalar() or 0
    income = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user.id,
        Transaction.type == TransactionType.income,
        Transaction.date >= start,
        Transaction.date < end,
    ).scalar() or 0

    top_rows = db.query(
        Transaction.category_id,
        func.sum(Transaction.amount).label("amount"),
    ).filter(
        Transaction.user_id == user.id,
        Transaction.type == TransactionType.expense,
        Transaction.date >= start,
        Transaction.date < end,
    ).group_by(Transaction.category_id).order_by(desc("amount")).limit(5).all()

    categories = db.query(Category).filter((Category.is_default == True) | (Category.user_id == user.id)).all()
    category_by_id = {cat.id: cat for cat in categories}
    top_categories = [
        {
            "category_id": row.category_id,
            "name": category_by_id[row.category_id].name if row.category_id in category_by_id else "سایر",
            "amount": row.amount,
        }
        for row in top_rows
    ]

    recent = db.query(Transaction).options(joinedload(Transaction.category)).filter(
        Transaction.user_id == user.id
    ).order_by(Transaction.date.desc(), Transaction.id.desc()).limit(10).all()

    days_in_month = calendar.monthrange(today.year, today.month)[1]
    goals = db.query(Goal).filter(Goal.user_id == user.id, Goal.current_amount < Goal.target_amount).all()

    return {
        "user": {"id": user.id, "name": user.name, "phone": user.phone},
        "current_jalali_month": jm,
        "current_jalali_year": jy,
        "current_gregorian_date": today.isoformat(),
        "budget": {"amount": budget_amount, "currency": budget.currency if budget else "تومان"},
        "total_spent_this_month": spent,
        "total_income_this_month": income,
        "remaining_budget": budget_amount - spent,
        "budget_used_percent": round((spent / budget_amount * 100), 1) if budget_amount else 0,
        "days_passed": today.day,
        "days_remaining": max(days_in_month - today.day, 0),
        "jalali_day": jalali_day,
        "top_expense_categories": top_categories,
        "categories": [
            {"id": cat.id, "name": cat.name, "icon": cat.icon, "color": cat.color, "is_default": cat.is_default}
            for cat in categories
        ],
        "recent_transactions": [
            {
                "id": tx.id,
                "amount": tx.amount,
                "type": tx.type.value,
                "description": tx.description,
                "date": tx.date.isoformat(),
                "category_id": tx.category_id,
                "category_name": tx.category.name if tx.category else None,
            }
            for tx in recent
        ],
        "active_goals": [_goal_payload(goal, today) for goal in goals],
    }
