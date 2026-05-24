from typing import Optional
from pydantic import BaseModel


class BudgetCreate(BaseModel):
    month: int
    year: int
    amount: int
    currency: Optional[str] = "تومان"


class BudgetUpdate(BaseModel):
    amount: Optional[int] = None
    currency: Optional[str] = None


class BudgetOut(BaseModel):
    id: int
    user_id: int
    month: int
    year: int
    amount: int
    currency: str

    model_config = {"from_attributes": True}
