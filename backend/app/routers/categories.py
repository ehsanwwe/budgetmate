from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=List[CategoryOut])
def get_categories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cats = db.query(Category).filter(
        (Category.is_default == True) | (Category.user_id == current_user.id)
    ).all()
    return cats


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cat = Category(
        name=body.name,
        icon=body.icon or "📦",
        color=body.color or "#B0BEC5",
        is_default=False,
        user_id=current_user.id,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat
