from datetime import date as DateType, datetime
from typing import Optional
from pydantic import BaseModel, field_validator
from app.i18n.config import SUPPORTED_LOCALES, SUPPORTED_CURRENCIES

VALID_INCOME_RANGES = {"lt10", "10to20", "20to40", "40to80", "gt80", "prefer_not"}
VALID_CHAT_MODES = {"normal", "roast", "hype"}
VALID_FINANCIAL_STATUSES = {
    "stable_income",
    "irregular_income",
    "overspending",
    "in_debt",
    "saving_for_goal",
    "low_income_pressure",
    "planning_only",
    "other",
}


class UserOut(BaseModel):
    id: int
    phone: str
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_blocked: bool
    language: str
    created_at: datetime
    family_name: Optional[str] = None
    birthdate: Optional[DateType] = None
    province: Optional[str] = None
    city: Optional[str] = None
    income_range: Optional[str] = None
    agreement_accepted_at: Optional[datetime] = None
    agreement_version: Optional[str] = None
    onboarding_completed: bool = False
    onboarding_completed_at: Optional[datetime] = None
    chat_mode: str = "normal"
    preferred_currency: str = "IRT"
    current_financial_status: Optional[str] = None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    chat_mode: Optional[str] = None
    language: Optional[str] = None
    preferred_currency: Optional[str] = None

    @field_validator("chat_mode", mode="before")
    @classmethod
    def validate_chat_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_CHAT_MODES:
            raise ValueError(f"chat_mode must be one of: {', '.join(VALID_CHAT_MODES)}")
        return v

    @field_validator("language", mode="before")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SUPPORTED_LOCALES:
            raise ValueError(f"language must be one of: {', '.join(SUPPORTED_LOCALES)}")
        return v

    @field_validator("preferred_currency", mode="before")
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SUPPORTED_CURRENCIES:
            raise ValueError(f"preferred_currency must be one of: {', '.join(SUPPORTED_CURRENCIES)}")
        return v

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def strip_and_reject_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        stripped = str(v).strip()
        if stripped == "":
            raise ValueError("نمی‌تواند خالی باشد")
        return stripped


class UserPreferencesUpdate(BaseModel):
    language: Optional[str] = None
    preferred_currency: Optional[str] = None

    @field_validator("language", mode="before")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SUPPORTED_LOCALES:
            raise ValueError(f"language must be one of: {', '.join(SUPPORTED_LOCALES)}")
        return v

    @field_validator("preferred_currency", mode="before")
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SUPPORTED_CURRENCIES:
            raise ValueError(f"preferred_currency must be one of: {', '.join(SUPPORTED_CURRENCIES)}")
        return v


class UserPreferencesRead(BaseModel):
    language: str
    preferred_currency: str

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    family_name: Optional[str] = None
    birthdate: Optional[str] = None  # ISO date string YYYY-MM-DD
    province: Optional[str] = None
    city: Optional[str] = None
    income_range: Optional[str] = None
    current_financial_status: Optional[str] = None

    @field_validator("income_range", mode="before")
    @classmethod
    def validate_income_range(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_INCOME_RANGES:
            raise ValueError(f"income_range must be one of: {', '.join(VALID_INCOME_RANGES)}")
        return v

    @field_validator("current_financial_status", mode="before")
    @classmethod
    def validate_financial_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_FINANCIAL_STATUSES:
            raise ValueError(f"current_financial_status must be one of: {', '.join(VALID_FINANCIAL_STATUSES)}")
        return v

    @field_validator("birthdate", mode="before")
    @classmethod
    def validate_birthdate(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                DateType.fromisoformat(str(v))
            except ValueError:
                raise ValueError("birthdate must be ISO format YYYY-MM-DD")
        return v


class AgreementAccept(BaseModel):
    version: str


class OnboardingStatus(BaseModel):
    onboarding_completed: bool
    needs_agreement: bool
    id: int
    phone: str
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    family_name: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    income_range: Optional[str] = None
    agreement_version: Optional[str] = None
    current_financial_status: Optional[str] = None

    model_config = {"from_attributes": True}


class OnboardingIntroRequest(BaseModel):
    text: Optional[str] = None
    audio_transcript: Optional[str] = None
    audio_duration_seconds: Optional[float] = None
    source: Optional[str] = None  # "text" | "audio" | "mixed"
