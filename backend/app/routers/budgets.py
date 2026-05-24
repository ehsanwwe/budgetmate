from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_user
from app.core.jalali import current_jalali_month
from app.models.user import User
from app.models.budget import Budget
from app.schemas.budget import BudgetCreate, BudgetUpdate, BudgetOut

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("/current", response_model=BudgetOut)
def get_current_budget(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month, year = current_jalali_month()
    budget = db.query(Budget).filter(
        Budget.user_id == current_user.id,
        Budget.month == month,
        Budget.year == year,
    ).first()
    if not budget:
        budget = Budget(user_id=current_user.id, month=month, year=year, amount=0)
        db.add(budget)
        db.commit()
        db.refresh(budget)
    return budget


@router.post("", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
def create_budget(
    body: BudgetCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(Budget).filter(
        Budget.user_id == current_user.id,
        Budget.month == body.month,
        Budget.year == body.year,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="بودجه برای این ماه قبلاً ثبت شده است")
    budget = Budget(
        user_id=current_user.id,
        month=body.month,
        year=body.year,
        amount=body.amount,
        currency=body.currency or "تومان",
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


@router.put("/{budget_id}", response_model=BudgetOut)
def update_budget(
    budget_id: int,
    body: BudgetUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    budget = db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == current_user.id).first()
    if not budget:
        raise HTTPException(status_code=404, detail="بودجه یافت نشد")
    if body.amount is not None:
        budget.amount = body.amount
    if body.currency is not None:
        budget.currency = body.currency
    db.commit()
    db.refresh(budget)
    return budget
