from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.schemas.user import UserOut, UserUpdate, UserPreferencesRead, UserPreferencesUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.name is not None:
        current_user.name = body.name
    if body.first_name is not None:
        current_user.first_name = body.first_name
    if body.last_name is not None:
        current_user.last_name = body.last_name
    if body.chat_mode is not None:
        current_user.chat_mode = body.chat_mode
    if body.language is not None:
        current_user.language = body.language
    if body.preferred_currency is not None:
        current_user.preferred_currency = body.preferred_currency
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me/preferences", response_model=UserPreferencesRead)
def get_preferences(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me/preferences", response_model=UserPreferencesRead)
def update_preferences(
    body: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.language is not None:
        current_user.language = body.language
    if body.preferred_currency is not None:
        current_user.preferred_currency = body.preferred_currency
    db.commit()
    db.refresh(current_user)
    return current_user
