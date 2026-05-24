from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_user
from app.core.jalali import current_jalali_month, gregorian_to_jalali
from app.models.user import User
from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction, TransactionType
from app.schemas.transaction import TransactionCreate, TransactionOut, TransactionSummary, CategorySummary

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _get_current_month_range():
    jm, jy = current_jalali_month()
    # Get first day of current Jalali month in Gregorian
    from app.core.jalali import _jalali_to_gregorian
    gy, gday = _jalali_to_gregorian(jy, jm, 1)
    from datetime import date as dt
    import calendar
    # Simple approach: get date range for current Jalali month
    # Use approximate: current month start
    today = dt.today()
    start = dt(today.year, today.month, 1)
    if today.month == 12:
        end = dt(today.year + 1, 1, 1)
    else:
        end = dt(today.year, today.month + 1, 1)
    return start, end


@router.get("/summary", response_model=TransactionSummary)
def get_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start, end = _get_current_month_range()
    jm, jy = current_jalali_month()

    # Get budget
    budget = db.query(Budget).filter(
        Budget.user_id == current_user.id,
        Budget.month == jm,
        Budget.year == jy,
    ).first()
    budget_amount = budget.amount if budget else 0

    # Total spent
    spent_result = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == TransactionType.expense,
        Transaction.date >= start,
        Transaction.date < end,
    ).scalar()
    total_spent = spent_result or 0

    # Total income
    income_result = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == TransactionType.income,
        Transaction.date >= start,
        Transaction.date < end,
    ).scalar()
    total_income = income_result or 0

    # By category
    cat_rows = db.query(
        Transaction.category_id,
        func.sum(Transaction.amount).label("total"),
    ).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == TransactionType.expense,
        Transaction.date >= start,
        Transaction.date < end,
    ).group_by(Transaction.category_id).all()

    by_category = []
    for row in cat_rows:
        cat = db.query(Category).filter(Category.id == row.category_id).first()
        cat_name = cat.name if cat else "سایر"
        pct = (row.total / total_spent * 100) if total_spent > 0 else 0
        by_category.append(CategorySummary(
            category_id=row.category_id,
            category_name=cat_name,
            amount=row.total,
            percent=round(pct, 1),
        ))

    budget_used_pct = (total_spent / budget_amount * 100) if budget_amount > 0 else 0
    remaining = budget_amount - total_spent

    return TransactionSummary(
        total_spent_this_month=total_spent,
        total_income_this_month=total_income,
        by_category=by_category,
        budget_used_percent=round(budget_used_pct, 1),
        remaining=remaining,
    )


@router.get("", response_model=List[TransactionOut])
def list_transactions(
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    category_id: Optional[int] = None,
    type: Optional[TransactionType] = None,
    q: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Transaction).filter(Transaction.user_id == current_user.id)
    if from_date:
        query = query.filter(Transaction.date >= from_date)
    if to_date:
        query = query.filter(Transaction.date <= to_date)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if type:
        query = query.filter(Transaction.type == type)
    if q:
        query = query.filter(Transaction.description.ilike(f"%{q}%"))
    return query.order_by(Transaction.date.desc()).all()


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    body: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txn = Transaction(
        user_id=current_user.id,
        category_id=body.category_id,
        amount=body.amount,
        type=body.type,
        description=body.description,
        date=body.date or date.today(),
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txn = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == current_user.id,
    ).first()
    if not txn:
        raise HTTPException(status_code=404, detail="تراکنش یافت نشد")
    db.delete(txn)
    db.commit()
