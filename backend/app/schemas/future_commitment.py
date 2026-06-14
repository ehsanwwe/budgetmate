from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class FutureCommitmentCreate(BaseModel):
    title: str
    amount: int
    due_date: date | None = None
    due_month: str | None = None
    category_id: int | None = None
    related_transaction_id: int | None = None
    related_goal_id: int | None = None
    description: str | None = None
    status: str = "pending"
    source: str = "manual"
    metadata_json: dict[str, Any] | None = None


class FutureCommitmentUpdate(BaseModel):
    title: str | None = None
    amount: int | None = Field(default=None, ge=0)
    due_date: date | None = None
    due_month: str | None = None
    category_id: int | None = None
    related_transaction_id: int | None = None
    related_goal_id: int | None = None
    description: str | None = None
    status: str | None = None
    metadata_json: dict[str, Any] | None = None


class FutureCommitmentOut(BaseModel):
    id: int
    user_id: int
    title: str
    amount: int
    due_date: date | None = None
    due_month: str | None = None
    category_id: int | None = None
    related_transaction_id: int | None = None
    related_goal_id: int | None = None
    description: str | None = None
    status: str
    source: str
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


FutureCommitmentRead = FutureCommitmentOut
