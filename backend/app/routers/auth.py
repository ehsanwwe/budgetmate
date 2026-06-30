import bcrypt
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app.db import get_db
from app.core.config import settings
from app.core.auth import create_access_token
from app.models.user import User
from app.models.admin import AdminUser
from app.models.activity import ActivityLog
from app.schemas.auth import OTPRequest, OTPVerify, TokenResponse, AdminLogin, AdminTokenResponse
from app.schemas.user import UserOut
from app.services.billing import ensure_wallet

router = APIRouter(prefix="/auth", tags=["auth"])
google_router = APIRouter(prefix="/auth/google", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_STATE_COOKIE = "google_oauth_state"
GOOGLE_STATE_TTL_MINUTES = 10
SUPPORTED_LOCALES = {"fa", "ar", "en", "de", "zh"}


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _localized_url(configured_url: str, locale: str, suffix: str = "") -> str:
    parts = urlsplit(configured_url)
    segments = [segment for segment in parts.path.split("/") if segment]
    if segments and segments[0] in SUPPORTED_LOCALES:
        segments[0] = locale
    elif not segments:
        segments = [locale]
    path = "/" + "/".join(segments)
    if suffix:
        path = path.rstrip("/") + "/" + suffix.lstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _error_redirect(locale: str, error: str) -> RedirectResponse:
    url = _localized_url(settings.GOOGLE_OAUTH_FRONTEND_ERROR_URL, locale)
    return RedirectResponse(f"{url}?{urlencode({'google_error': error})}")


@google_router.get("/login")
def google_login(locale: str = "fa"):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    if locale not in SUPPORTED_LOCALES:
        locale = "fa"

    nonce = secrets.token_urlsafe(32)
    state = jwt.encode(
        {"locale": locale, "nonce": nonce, "exp": datetime.utcnow() + timedelta(minutes=GOOGLE_STATE_TTL_MINUTES)},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    authorization_url = f"{GOOGLE_AUTH_URL}?{urlencode({
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'nonce': nonce,
    })}"
    response = RedirectResponse(authorization_url)
    response.set_cookie(
        GOOGLE_STATE_COOKIE,
        state,
        max_age=GOOGLE_STATE_TTL_MINUTES * 60,
        httponly=True,
        secure=settings.GOOGLE_REDIRECT_URI.startswith("https://"),
        samesite="lax",
        path="/api/auth/google/callback",
    )
    return response


@google_router.get("/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    state = request.query_params.get("state", "")
    cookie_state = request.cookies.get(GOOGLE_STATE_COOKIE, "")
    locale = "fa"
    try:
        state_data = jwt.decode(state, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        locale = state_data.get("locale", "fa")
        if locale not in SUPPORTED_LOCALES or not secrets.compare_digest(state, cookie_state):
            raise JWTError("state mismatch")
    except (JWTError, ValueError):
        return _error_redirect(locale, "invalid_state")

    if request.query_params.get("error"):
        return _error_redirect(locale, "access_denied")
    code = request.query_params.get("code")
    if not code:
        return _error_redirect(locale, "missing_code")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
        token_response.raise_for_status()
        raw_id_token = token_response.json().get("id_token")
        if not raw_id_token:
            raise ValueError("missing id_token")
        claims = await run_in_threadpool(
            google_id_token.verify_oauth2_token,
            raw_id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
        if claims.get("nonce") != state_data.get("nonce"):
            raise ValueError("nonce mismatch")
    except (httpx.HTTPError, GoogleAuthError, ValueError, TypeError):
        return _error_redirect(locale, "token_validation_failed")

    google_sub = claims.get("sub")
    email = claims.get("email")
    if not google_sub or not email or claims.get("email_verified") is not True:
        return _error_redirect(locale, "unverified_email")
    email = email.strip().lower()

    user = db.query(User).filter(User.google_sub == google_sub).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
    is_new_user = user is None
    if user is None:
        display_name = (claims.get("name") or "").strip() or None
        name_parts = display_name.split(maxsplit=1) if display_name else []
        user = User(
            email=email,
            name=display_name,
            first_name=name_parts[0] if name_parts else None,
            last_name=name_parts[1] if len(name_parts) > 1 else None,
            language=locale,
            auth_provider="google",
            google_sub=google_sub,
            avatar_url=claims.get("picture"),
            created_at=datetime.utcnow(),
        )
        db.add(user)
    else:
        if user.google_sub and user.google_sub != google_sub:
            return _error_redirect(locale, "account_conflict")
        user.email = user.email or email
        user.google_sub = google_sub
        user.auth_provider = "google"
        user.avatar_url = claims.get("picture") or user.avatar_url

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        user = db.query(User).filter(User.google_sub == google_sub).first()
        if user is None:
            return _error_redirect(locale, "account_conflict")

    ensure_wallet(db, user.id)
    db.add(ActivityLog(
        user_id=user.id,
        action="user_registered" if is_new_user else "user_login",
        meta={"provider": "google", "email": email},
    ))
    db.commit()

    app_token = create_access_token({"sub": str(user.id), "scope": "user"})
    callback_url = _localized_url(
        settings.GOOGLE_OAUTH_FRONTEND_SUCCESS_URL, locale, "auth/google/callback"
    )
    response = RedirectResponse(f"{callback_url}#access_token={app_token}")
    response.delete_cookie(GOOGLE_STATE_COOKIE, path="/api/auth/google/callback")
    return response


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
    is_new_user = user is None
    if is_new_user:
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

    ensure_wallet(db, user.id)

    needs_profile = not user.first_name
    token = create_access_token({"sub": str(user.id), "scope": "user"})
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(user),
        needs_profile=needs_profile,
        onboarding_completed=bool(user.onboarding_completed),
    )


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
