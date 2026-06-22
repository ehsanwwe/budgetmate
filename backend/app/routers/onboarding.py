from datetime import date as DateType, datetime
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.personal_cfo import FinancialMemory
from app.schemas.user import AgreementAccept, OnboardingIntroRequest, OnboardingStatus, ProfileUpdate
from app.data.iran_geo import PROVINCES, CITIES
from app.services.onboarding_budget import initialize_budget_from_income_range
from app.services.personal_cfo.memory_service import create_memory
from app.services.stt import transcribe_audio

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


@router.post("/onboarding/intro")
def save_onboarding_intro(
    body: OnboardingIntroRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    text = (body.text or "").strip()
    transcript = (body.audio_transcript or "").strip()

    if not text and not transcript:
        return {"ok": True, "message": "هیچ محتوایی برای ذخیره وجود ندارد"}

    if text and transcript:
        source_label = "mixed"
        combined = f"{text}\n\n[صدا]: {transcript}"
        confidence = 0.8
    elif text:
        source_label = "text"
        combined = text
        confidence = 0.85
    else:
        source_label = "audio"
        combined = transcript
        confidence = 0.7

    existing = (
        db.query(FinancialMemory)
        .filter(
            FinancialMemory.user_id == current_user.id,
            FinancialMemory.title == "onboarding_self_description",
            FinancialMemory.is_active == True,
        )
        .all()
    )
    for m in existing:
        m.is_active = False
    if existing:
        db.commit()

    create_memory(
        db=db,
        user_id=current_user.id,
        memory_type="user_profile",
        title="onboarding_self_description",
        content_json={
            "text": text or None,
            "audio_transcript": transcript or None,
            "combined_text": combined,
            "source": source_label,
            "created_from": "onboarding_intro",
        },
        source="onboarding",
        confidence=confidence,
    )
    return {"ok": True, "message": "اطلاعات با موفقیت ذخیره شد"}


@router.post("/onboarding/intro/audio")
async def transcribe_intro_audio(
    file: UploadFile = File(...),
    duration_seconds: Optional[float] = Form(None),
    current_user: User = Depends(get_current_user),
):
    audio_bytes = await file.read()
    content_type = file.content_type or "audio/webm"
    result = await transcribe_audio(audio_bytes, content_type)
    transcript = result.get("transcript", "")
    empty = not bool(transcript.strip())
    return {"ok": True, "transcript": transcript, "empty": empty}


@router.get("/iran/provinces")
def get_provinces():
    return {"provinces": PROVINCES}


@router.get("/iran/cities")
def get_cities(province: str):
    cities = CITIES.get(province)
    if cities is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="استان یافت نشد")
    return {"province": province, "cities": cities}
