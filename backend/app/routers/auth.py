import bcrypt
import logging
import secrets
import time
from datetime import date as DateType, datetime, timedelta
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
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
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_PEOPLE_URL = "https://people.googleapis.com/v1/people/me"
GOOGLE_STATE_COOKIE = "google_oauth_state"
GOOGLE_STATE_TTL_MINUTES = 10
SUPPORTED_LOCALES = {"fa", "ar", "en", "de", "zh"}
logger = logging.getLogger(__name__)
_google_jwks_cache: dict = {"keys": [], "expires_at": 0.0}


class GoogleJwksUnavailable(Exception):
    """The Google signing-key service could not be reached reliably."""


def _map_google_names(profile: dict, flow_id: str = "unknown") -> tuple[str | None, str | None, str | None]:
    _oauth_log("profile_name_mapping_started", flow_id=flow_id)
    given_name = str(profile.get("given_name") or "").strip() or None
    family_name = str(profile.get("family_name") or "").strip() or None
    display_name = str(profile.get("name") or "").strip() or None
    if not given_name and not family_name and display_name:
        # Preserve the existing full-name fallback behavior.
        parts = display_name.split(maxsplit=1)
        given_name = parts[0]
        family_name = parts[1] if len(parts) > 1 else None
    _oauth_log(
        "profile_name_mapping_succeeded",
        flow_id=flow_id,
        given_name_present=bool(given_name),
        family_name_present=bool(family_name),
    )
    return given_name, family_name, display_name


async def fetch_google_people_profile(
    access_token: str, client: httpx.AsyncClient, flow_id: str
) -> dict:
    _oauth_log("people_profile_fetch_started", flow_id=flow_id)
    try:
        response = await client.get(
            GOOGLE_PEOPLE_URL,
            params={"personFields": "phoneNumbers,birthdays,names,emailAddresses"},
            headers={
                "Accept": "application/json",
                "User-Agent": "BudgetMate-OAuth/1.0",
                "Authorization": f"Bearer {access_token}",
            },
        )
        response.raise_for_status()
        profile = response.json()
        _oauth_log("people_profile_fetch_succeeded", flow_id=flow_id)
        return profile
    except (httpx.HTTPError, RuntimeError, ValueError, TypeError) as exc:
        status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        _oauth_log(
            "people_profile_fetch_failed",
            level=logging.WARNING,
            flow_id=flow_id,
            status=status_code or "unavailable",
            error_type=type(exc).__name__,
            error_message=_safe_exception_message(exc),
        )
        return {}


def _extract_people_phone(profile: dict) -> str | None:
    entries = profile.get("phoneNumbers") or []
    ordered = sorted(entries, key=lambda item: not bool(item.get("metadata", {}).get("primary")))
    for item in ordered:
        candidate = str(item.get("canonicalForm") or item.get("value") or "").strip()
        if candidate.startswith("+") and candidate[1:].isdigit() and 8 <= len(candidate[1:]) <= 15:
            return candidate
    return None


def _extract_people_birthdate(profile: dict) -> DateType | None:
    entries = profile.get("birthdays") or []
    ordered = sorted(entries, key=lambda item: not bool(item.get("metadata", {}).get("primary")))
    for item in ordered:
        value = item.get("date") or {}
        if not all(value.get(part) for part in ("year", "month", "day")):
            continue
        try:
            return DateType(int(value["year"]), int(value["month"]), int(value["day"]))
        except (TypeError, ValueError):
            continue
    return None


def _apply_optional_people_data(user: User, profile: dict, db: Session, flow_id: str) -> None:
    people_phone = _extract_people_phone(profile)
    people_birthdate = _extract_people_birthdate(profile)
    if not user.phone and people_phone:
        phone_query = db.query(User).filter(User.phone == people_phone)
        if user.id is not None:
            phone_query = phone_query.filter(User.id != user.id)
        if phone_query.first() is None:
            user.phone = people_phone
            _oauth_log("optional_phone_imported", flow_id=flow_id, user_id=user.id or "pending")
        else:
            _oauth_log(
                "optional_phone_conflict_skipped",
                level=logging.WARNING,
                flow_id=flow_id,
                user_id=user.id or "pending",
            )
    if not user.birthdate and people_birthdate:
        user.birthdate = people_birthdate
        _oauth_log("optional_birthday_imported", flow_id=flow_id, user_id=user.id or "pending")


def _oauth_log(event: str, *, level: int = logging.INFO, **fields) -> None:
    safe_fields = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.log(level, "oauth_google event=%s %s", event, safe_fields)


def _safe_exception_message(exc: Exception) -> str:
    return " ".join(str(exc).split())[:240] or "no_message"


async def _get_google_jwks(client: httpx.AsyncClient, flow_id: str) -> list[dict]:
    now = time.monotonic()
    if _google_jwks_cache["keys"] and now < _google_jwks_cache["expires_at"]:
        _oauth_log("jwks_cache_hit", flow_id=flow_id)
        return _google_jwks_cache["keys"]

    _oauth_log("jwks_fetch_started", flow_id=flow_id)
    try:
        response = await client.get(GOOGLE_JWKS_URL)
        response.raise_for_status()
        keys = response.json().get("keys", [])
    except httpx.HTTPStatusError as exc:
        _oauth_log(
            "jwks_fetch_failed",
            level=logging.WARNING,
            flow_id=flow_id,
            error_type=type(exc).__name__,
            error_message=_safe_exception_message(exc),
        )
        if exc.response.status_code in {403, 429} or exc.response.status_code >= 500:
            raise GoogleJwksUnavailable(_safe_exception_message(exc)) from exc
        raise
    except (httpx.RequestError, RuntimeError, ValueError, TypeError) as exc:
        _oauth_log(
            "jwks_fetch_failed",
            level=logging.WARNING,
            flow_id=flow_id,
            error_type=type(exc).__name__,
            error_message=_safe_exception_message(exc),
        )
        raise GoogleJwksUnavailable(_safe_exception_message(exc)) from exc
    if not keys:
        raise GoogleJwksUnavailable("Google JWKS response contained no keys")
    max_age = 3600
    for directive in response.headers.get("cache-control", "").split(","):
        if directive.strip().startswith("max-age="):
            try:
                max_age = max(60, int(directive.split("=", 1)[1]))
            except ValueError:
                pass
    _google_jwks_cache.update(keys=keys, expires_at=now + max_age)
    _oauth_log("jwks_fetch_succeeded", flow_id=flow_id, key_count=len(keys), max_age=max_age)
    return keys


async def _validate_google_id_token_with_jwks(
    raw_id_token: str, client: httpx.AsyncClient, flow_id: str
) -> dict:
    header = jwt.get_unverified_header(raw_id_token)
    kid = header.get("kid")
    if header.get("alg") != "RS256" or not kid:
        raise JWTError("Google ID token has an invalid signing header")
    keys = await _get_google_jwks(client, flow_id)
    signing_key = next((key for key in keys if key.get("kid") == kid), None)
    if signing_key is None:
        # A rotated key may make a still-valid cache stale; refresh once.
        _google_jwks_cache.update(keys=[], expires_at=0.0)
        keys = await _get_google_jwks(client, flow_id)
        signing_key = next((key for key in keys if key.get("kid") == kid), None)
    if signing_key is None:
        raise JWTError("No matching Google signing key")

    claims = jwt.decode(
        raw_id_token,
        signing_key,
        algorithms=["RS256"],
        audience=settings.GOOGLE_CLIENT_ID,
        options={"verify_signature": True, "verify_aud": True, "verify_exp": True},
    )
    if claims.get("iss") not in {"https://accounts.google.com", "accounts.google.com"}:
        raise JWTError("Google ID token issuer is invalid")
    return claims


def _validate_tokeninfo_claims(claims: dict, raw_id_token: str, expected_nonce: str) -> dict:
    if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise JWTError("Google tokeninfo audience is invalid")
    if claims.get("iss") not in {"https://accounts.google.com", "accounts.google.com"}:
        raise JWTError("Google tokeninfo issuer is invalid")
    try:
        expires_at = int(claims.get("exp", 0))
    except (TypeError, ValueError) as exc:
        raise JWTError("Google tokeninfo expiry is invalid") from exc
    if expires_at <= int(time.time()):
        raise JWTError("Google tokeninfo token is expired")
    if not claims.get("sub"):
        raise JWTError("Google tokeninfo subject is missing")
    if not claims.get("email"):
        raise JWTError("Google tokeninfo email is missing")

    verified = claims.get("email_verified")
    if verified is not None and str(verified).lower() != "true":
        raise JWTError("Google tokeninfo email is not verified")
    claims["email_verified"] = True

    unverified_claims = jwt.get_unverified_claims(raw_id_token)
    token_nonce = claims.get("nonce") or unverified_claims.get("nonce")
    if token_nonce is not None and not secrets.compare_digest(str(token_nonce), expected_nonce):
        raise JWTError("Google tokeninfo nonce is invalid")
    return claims


async def _validate_google_id_token_with_tokeninfo(
    raw_id_token: str,
    client: httpx.AsyncClient,
    flow_id: str,
    expected_nonce: str,
) -> dict:
    _oauth_log("tokeninfo_validation_started", flow_id=flow_id)
    response = await client.post(
        GOOGLE_TOKENINFO_URL,
        data={"id_token": raw_id_token},
        headers={"Accept": "application/json", "User-Agent": "BudgetMate-OAuth/1.0"},
    )
    response.raise_for_status()
    claims = _validate_tokeninfo_claims(response.json(), raw_id_token, expected_nonce)
    _oauth_log("tokeninfo_validation_succeeded", flow_id=flow_id)
    return claims


async def _validate_google_id_token(
    raw_id_token: str,
    client: httpx.AsyncClient,
    flow_id: str,
    expected_nonce: str,
) -> dict:
    try:
        claims = await _validate_google_id_token_with_jwks(raw_id_token, client, flow_id)
        if claims.get("nonce") is not None and not secrets.compare_digest(
            str(claims["nonce"]), expected_nonce
        ):
            raise JWTError("Google ID token nonce is invalid")
        _oauth_log("token_validation_succeeded", flow_id=flow_id, method="httpx_jwks_rs256")
        return claims
    except GoogleJwksUnavailable as exc:
        _oauth_log(
            "token_validation_fallback",
            level=logging.WARNING,
            flow_id=flow_id,
            reason="jwks_unavailable",
            error_message=_safe_exception_message(exc),
        )
        claims = await _validate_google_id_token_with_tokeninfo(
            raw_id_token, client, flow_id, expected_nonce
        )
        _oauth_log("token_validation_succeeded", flow_id=flow_id, method="tokeninfo")
        return claims


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
    _oauth_log("callback_failed", level=logging.WARNING, locale=locale, reason=error)
    url = _localized_url(settings.GOOGLE_OAUTH_FRONTEND_ERROR_URL, locale)
    return RedirectResponse(f"{url}?{urlencode({'google_error': error})}")


@google_router.get("/login")
def google_login(locale: str = "fa"):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    if locale not in SUPPORTED_LOCALES:
        locale = "fa"

    nonce = secrets.token_urlsafe(32)
    flow_id = secrets.token_hex(8)
    state = jwt.encode(
        {
            "locale": locale,
            "nonce": nonce,
            "flow_id": flow_id,
            "exp": datetime.utcnow() + timedelta(minutes=GOOGLE_STATE_TTL_MINUTES),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    scopes = ["openid", "email", "profile"]
    if settings.GOOGLE_PEOPLE_PROFILE_ENRICHMENT_ENABLED:
        scopes.extend([
            "https://www.googleapis.com/auth/user.phonenumbers.read",
            "https://www.googleapis.com/auth/user.birthday.read",
        ])
    authorization_url = f"{GOOGLE_AUTH_URL}?{urlencode({
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(scopes),
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
    _oauth_log("login_redirect_created", flow_id=flow_id, locale=locale, redirect_uri=settings.GOOGLE_REDIRECT_URI)
    return response


@google_router.get("/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    state = request.query_params.get("state", "")
    cookie_state = request.cookies.get(GOOGLE_STATE_COOKIE, "")
    locale = "fa"
    flow_id = "unknown"
    _oauth_log(
        "callback_started",
        code_present=bool(request.query_params.get("code")),
        state_present=bool(state),
        state_cookie_present=bool(cookie_state),
    )
    people_profile: dict = {}
    try:
        state_data = jwt.decode(state, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        locale = state_data.get("locale", "fa")
        flow_id = state_data.get("flow_id", "unknown")
        if locale not in SUPPORTED_LOCALES or not secrets.compare_digest(state, cookie_state):
            raise JWTError("state mismatch")
    except (JWTError, ValueError):
        return _error_redirect(locale, "invalid_state")
    _oauth_log("state_validated", flow_id=flow_id, locale=locale)

    if request.query_params.get("error"):
        return _error_redirect(locale, "access_denied")
    code = request.query_params.get("code")
    if not code:
        return _error_redirect(locale, "missing_code")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15, connect=10),
            headers={"Accept": "application/json", "User-Agent": "BudgetMate-OAuth/1.0"},
        ) as client:
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
            _oauth_log("token_exchange_succeeded", flow_id=flow_id, status=token_response.status_code)
            token_payload = token_response.json()
            raw_id_token = token_payload.get("id_token")
            _oauth_log(
                "token_payload_received",
                flow_id=flow_id,
                id_token_present=bool(raw_id_token),
                access_token_present=bool(token_payload.get("access_token")),
            )
            if not raw_id_token:
                raise ValueError("missing id_token")
            _oauth_log("token_validation_started", flow_id=flow_id, method="httpx_jwks_rs256")
            claims = await _validate_google_id_token(
                raw_id_token, client, flow_id, state_data["nonce"]
            )
            access_token = token_payload.get("access_token")
            if settings.GOOGLE_PEOPLE_PROFILE_ENRICHMENT_ENABLED and access_token:
                people_profile = await fetch_google_people_profile(access_token, client, flow_id)
            else:
                _oauth_log(
                    "people_profile_fetch_skipped",
                    flow_id=flow_id,
                    reason="disabled" if not settings.GOOGLE_PEOPLE_PROFILE_ENRICHMENT_ENABLED else "missing_access_token",
                )
    except (httpx.HTTPError, JWTError, RuntimeError, ValueError, TypeError) as exc:
        _oauth_log(
            "token_validation_failed",
            level=logging.WARNING,
            flow_id=flow_id,
            error_type=type(exc).__name__,
            error_message=_safe_exception_message(exc),
        )
        return _error_redirect(locale, "token_validation_failed")

    google_sub = claims.get("sub")
    email = claims.get("email")
    if not google_sub or not email or claims.get("email_verified") is not True:
        return _error_redirect(locale, "unverified_email")
    email = email.strip().lower()
    _oauth_log("profile_validated", flow_id=flow_id, email_domain=email.rsplit("@", 1)[-1])

    combined_profile = dict(claims)
    people_names = people_profile.get("names") or []
    if people_names:
        people_name = next(
            (item for item in people_names if item.get("metadata", {}).get("primary")),
            people_names[0],
        )
        if not combined_profile.get("given_name"):
            combined_profile["given_name"] = people_name.get("givenName")
        if not combined_profile.get("family_name"):
            combined_profile["family_name"] = people_name.get("familyName")
        if not combined_profile.get("name"):
            combined_profile["name"] = people_name.get("displayName")
    given_name, family_name, display_name = _map_google_names(combined_profile, flow_id)

    user = db.query(User).filter(User.google_sub == google_sub).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
    is_new_user = user is None
    if user is None:
        user = User(
            email=email,
            name=display_name,
            first_name=given_name,
            last_name=family_name,
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
        if not user.first_name and given_name:
            user.first_name = given_name
        if not user.last_name and family_name:
            user.last_name = family_name

    _apply_optional_people_data(user, people_profile, db, flow_id)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        user = db.query(User).filter(User.google_sub == google_sub).first()
        if user is None:
            return _error_redirect(locale, "account_conflict")

    _oauth_log(
        "local_user_ready",
        flow_id=flow_id,
        user_id=user.id,
        action="created" if is_new_user else "linked_or_existing",
    )

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
    _oauth_log(
        "session_redirect_created",
        flow_id=flow_id,
        user_id=user.id,
        auth_mechanism="bearer_fragment",
        callback_origin=urlsplit(callback_url).netloc,
    )
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
