import bcrypt
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.config import settings
from app.core.auth import create_access_token
from app.models.user import User
from app.models.admin import AdminUser
from app.models.activity import ActivityLog
from app.schemas.auth import OTPRequest, OTPVerify, TokenResponse, AdminLogin, AdminTokenResponse
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


@router.post("/request-otp")
def request_otp(body: OTPRequest, db: Session = Depends(get_db)):
    log = ActivityLog(action="otp_requested", meta={"phone": body.phone}, created_at=datetime.utcnow())
    db.add(log)
    db.commit()
    return {"message": "کد تأیید ارسال شد", "hint": f"کد آزمایشی: {settings.OTP_MOCK_CODE}"}


@router.post("/verify-otp", response_model=TokenResponse)
def verify_otp(body: OTPVerify, db: Session = Depends(get_db)):
    if body.code != settings.OTP_MOCK_CODE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="کد تأیید اشتباه است")

    user = db.query(User).filter(User.phone == body.phone).first()
    if not user:
        user = User(phone=body.phone, created_at=datetime.utcnow())
        db.add(user)
        db.commit()
        db.refresh(user)
        log = ActivityLog(user_id=user.id, action="user_registered", meta={"phone": body.phone})
        db.add(log)
        db.commit()
    else:
        log = ActivityLog(user_id=user.id, action="user_login", meta={"phone": body.phone})
        db.add(log)
        db.commit()

    token = create_access_token({"sub": str(user.id), "scope": "user"})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/admin/login", response_model=AdminTokenResponse)
def admin_login(body: AdminLogin, db: Session = Depends(get_db)):
    admin = db.query(AdminUser).filter(AdminUser.username == body.username).first()
    if not admin or not _verify_password(body.password, admin.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="نام کاربری یا رمز عبور اشتباه است")
    token = create_access_token({"sub": str(admin.id), "scope": "admin"})
    log = ActivityLog(action="admin_login", meta={"username": body.username})
    db.add(log)
    db.commit()
    return AdminTokenResponse(access_token=token)
