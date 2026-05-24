from typing import Optional
from pydantic import BaseModel


class CategoryCreate(BaseModel):
    name: str
    icon: Optional[str] = "📦"
    color: Optional[str] = "#B0BEC5"


class CategoryOut(BaseModel):
    id: int
    name: str
    icon: str
    color: str
    is_default: bool
    user_id: Optional[int] = None

    model_config = {"from_attributes": True}
