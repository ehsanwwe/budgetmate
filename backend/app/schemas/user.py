from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    phone: str
    name: Optional[str] = None
    is_blocked: bool
    language: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    name: Optional[str] = None
