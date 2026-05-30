from datetime import date as DateType, datetime
from typing import Optional
from pydantic import BaseModel, field_validator

VALID_INCOME_RANGES = {"lt10", "10to20", "20to40", "40to80", "gt80", "prefer_not"}
VALID_CHAT_MODES = {"normal", "roast", "hype"}


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

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    chat_mode: Optional[str] = None

    @field_validator("chat_mode", mode="before")
    @classmethod
    def validate_chat_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_CHAT_MODES:
            raise ValueError(f"chat_mode must be one of: {', '.join(VALID_CHAT_MODES)}")
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


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    family_name: Optional[str] = None
    birthdate: Optional[str] = None  # ISO date string YYYY-MM-DD
    province: Optional[str] = None
    city: Optional[str] = None
    income_range: Optional[str] = None

    @field_validator("income_range", mode="before")
    @classmethod
    def validate_income_range(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_INCOME_RANGES:
            raise ValueError(f"income_range must be one of: {', '.join(VALID_INCOME_RANGES)}")
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

    model_config = {"from_attributes": True}
