from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.config import settings
from app.models.user import User
from app.models.admin import AdminUser

bearer_scheme = HTTPBearer()

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="توکن نامعتبر است")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = _decode_token(credentials.credentials)
    user_id: Optional[int] = payload.get("sub")
    scope: Optional[str] = payload.get("scope")
    if user_id is None or scope != "user":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="توکن نامعتبر است")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="کاربر یافت نشد")
    if user.is_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="حساب شما توسط مدیر مسدود شده است")
    return user


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AdminUser:
    payload = _decode_token(credentials.credentials)
    admin_id: Optional[int] = payload.get("sub")
    scope: Optional[str] = payload.get("scope")
    if admin_id is None or scope != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="توکن ادمین نامعتبر است")
    admin = db.query(AdminUser).filter(AdminUser.id == int(admin_id)).first()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ادمین یافت نشد")
    return admin
