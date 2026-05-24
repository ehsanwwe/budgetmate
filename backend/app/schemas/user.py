from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class UserOut(BaseModel):
    id: int
    phone: str
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_blocked: bool
    language: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def strip_and_reject_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        stripped = str(v).strip()
        if stripped == "":
            raise ValueError("نمی‌تواند خالی باشد")
        return stripped
