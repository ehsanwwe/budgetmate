from datetime import date as DateType
from typing import List, Optional
from pydantic import BaseModel
from app.models.transaction import TransactionType


class TransactionCreate(BaseModel):
    category_id: Optional[int] = None
    amount: int
    type: TransactionType = TransactionType.expense
    description: Optional[str] = None
    date: Optional[DateType] = None


class TransactionOut(BaseModel):
    id: int
    user_id: int
    category_id: Optional[int] = None
    amount: int
    type: TransactionType
    description: Optional[str] = None
    date: DateType

    model_config = {"from_attributes": True}


class CategorySummary(BaseModel):
    category_id: Optional[int]
    category_name: str
    amount: int
    percent: float


class TransactionSummary(BaseModel):
    total_spent_this_month: int
    total_income_this_month: int
    by_category: List[CategorySummary]
    budget_used_percent: float
    remaining: int
