from datetime import date as DateType, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.schemas.user import ProfileUpdate, AgreementAccept, OnboardingStatus
from app.data.iran_geo import PROVINCES, CITIES
from app.services.onboarding_budget import initialize_budget_from_income_range

router = APIRouter(tags=["onboarding"])


@router.get("/onboarding/status", response_model=OnboardingStatus)
def get_onboarding_status(current_user: User = Depends(get_current_user)):
    return OnboardingStatus(
        onboarding_completed=bool(current_user.onboarding_completed),
        needs_agreement=current_user.agreement_accepted_at is None,
        id=current_user.id,
        phone=current_user.phone,
        name=current_user.name,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        family_name=current_user.family_name,
        province=current_user.province,
        city=current_user.city,
        income_range=current_user.income_range,
        agreement_version=current_user.agreement_version,
        current_financial_status=current_user.current_financial_status,
    )


@router.post("/onboarding/profile")
def update_profile(
    body: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.name is not None:
        current_user.name = body.name.strip()
        current_user.first_name = body.name.strip()
    if body.family_name is not None:
        current_user.family_name = body.family_name.strip()
        current_user.last_name = body.family_name.strip()
    if body.birthdate is not None:
        current_user.birthdate = DateType.fromisoformat(body.birthdate)
    if body.province is not None:
        current_user.province = body.province
    if body.city is not None:
        current_user.city = body.city
    if body.income_range is not None:
        current_user.income_range = body.income_range
    if body.current_financial_status is not None:
        current_user.current_financial_status = body.current_financial_status
    db.commit()
    db.refresh(current_user)
    return {"ok": True, "message": "پروفایل با موفقیت به‌روز شد"}


@router.post("/onboarding/agreement")
def accept_agreement(
    body: AgreementAccept,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.agreement_accepted_at = datetime.utcnow()
    current_user.agreement_version = body.version
    db.commit()
    return {"ok": True, "message": "شرایط و قوانین پذیرفته شد"}


@router.post("/onboarding/complete")
def complete_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    first_completion = not bool(current_user.onboarding_completed)
    if first_completion:
        initialize_budget_from_income_range(db, current_user)
    current_user.onboarding_completed = True
    current_user.onboarding_completed_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "ثبت‌نام تکمیل شد"}


@router.get("/iran/provinces")
def get_provinces():
    return {"provinces": PROVINCES}


@router.get("/iran/cities")
def get_cities(province: str):
    cities = CITIES.get(province)
    if cities is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="استان یافت نشد")
    return {"province": province, "cities": cities}
