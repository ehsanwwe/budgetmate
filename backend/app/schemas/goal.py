from datetime import date
from typing import Optional
from pydantic import BaseModel


class GoalCreate(BaseModel):
    title: str
    target_amount: int
    current_amount: Optional[int] = 0
    deadline: Optional[date] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    target_amount: Optional[int] = None
    deadline: Optional[date] = None


class GoalContribute(BaseModel):
    amount: int


class GoalOut(BaseModel):
    id: int
    user_id: int
    title: str
    target_amount: int
    current_amount: int
    deadline: Optional[date] = None

    model_config = {"from_attributes": True}
