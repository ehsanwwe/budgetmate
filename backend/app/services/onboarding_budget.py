from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.jalali import current_jalali_month
from app.models.budget import Budget
from app.models.user import User
from app.services.income_range import income_range_max_toman


def initialize_budget_from_income_range(db: Session, user: User) -> Budget | None:
    """Create or set the current monthly budget from the user's income range max.

    This is intended for first-time onboarding completion only. Callers should
    skip this after `user.onboarding_completed` is already true.
    """
    amount = income_range_max_toman(user.income_range)
    if amount is None:
        return None

    month, year = current_jalali_month()
    budget = (
        db.query(Budget)
        .filter(Budget.user_id == user.id, Budget.month == month, Budget.year == year)
        .first()
    )
    if budget:
        budget.amount = amount
    else:
        budget = Budget(user_id=user.id, month=month, year=year, amount=amount)
        db.add(budget)
    return budget
