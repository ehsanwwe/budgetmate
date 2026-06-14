from datetime import date, datetime
from typing import Any, Optional
from pydantic import BaseModel


class GoalCreate(BaseModel):
    title: str
    target_amount: int
    current_amount: Optional[int] = 0
    deadline: Optional[date] = None
    notes_json: Optional[dict[str, Any]] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    target_amount: Optional[int] = None
    current_amount: Optional[int] = None
    deadline: Optional[date] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    notes_json: Optional[dict[str, Any]] = None


class GoalContribute(BaseModel):
    amount: int


class GoalOut(BaseModel):
    id: int
    user_id: int
    title: str
    target_amount: int
    current_amount: int
    deadline: Optional[date] = None
    status: str = "active"
    is_active: bool = True
    notes_json: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
