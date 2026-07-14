from datetime import date as DateType
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from app.models.transaction import TransactionType


class TransactionCreate(BaseModel):
    category_id: Optional[int] = None
    amount: int
    type: TransactionType = TransactionType.expense
    description: Optional[str] = None
    date: Optional[DateType] = None


class TransactionUpdate(BaseModel):
    """Payload for PATCH /transactions/{id}. All fields are optional; unset
    fields are left unchanged. `user_id`, provenance and system fields are
    intentionally not editable."""

    category_id: Optional[int] = None
    amount: Optional[int] = Field(default=None)
    type: Optional[TransactionType] = None
    description: Optional[str] = None
    date: Optional[DateType] = None

    @field_validator("amount")
    @classmethod
    def _amount_must_be_positive(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("amount must be positive")
        return value

    @field_validator("description")
    @classmethod
    def _description_strip(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class TransactionOut(BaseModel):
    id: int
    user_id: int
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    category_icon: Optional[str] = None
    category_color: Optional[str] = None
    amount: int
    type: TransactionType
    description: Optional[str] = None
    date: DateType

    model_config = {"from_attributes": True}


class CategorySummary(BaseModel):
    category_id: Optional[int]
    category_name: str
    category: str
    amount: int
    percent: float


class DailySummary(BaseModel):
    date: DateType
    amount: int


class TransactionSummary(BaseModel):
    total_spent_this_month: int
    total_income_this_month: int
    total_expense: int
    total_income: int
    budget_amount: int
    by_category: List[CategorySummary]
    budget_used_percent: float
    remaining: int
    daily: List[DailySummary]
