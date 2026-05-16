"""
JWT access tokens and FastAPI auth dependencies.

- Access tokens expire after 10 days (``ACCESS_TOKEN_EXPIRE_MINUTES = 14400``).
- ``iat`` is embedded for auditing; the frontend silently refreshes once per
  day via ``/api/auth/refresh`` to extend the session automatically.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Issue a JWT with ``sub`` (user id), ``iat``, and ``exp``."""
    to_encode = data.copy()
    now = datetime.utcnow()
    delta = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = now + delta
    to_encode.setdefault("iat", calendar.timegm(now.timetuple()))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate JWT or raise 401."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_token(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials],
        Depends(bearer_scheme),
    ],
) -> dict:
    """
    FastAPI dependency: validate Bearer JWT and return the payload (includes ``sub``, ``iat``, ``exp``).
    """
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(credentials.credentials)


def get_current_user(
    payload: Annotated[dict, Depends(verify_token)],
    db: Session = Depends(get_db),
):
    """Resolve the authenticated user from JWT ``sub``; enforces active + unlocked account."""
    from app.models.models import User

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    if user.account_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is locked. Contact administrator.",
        )
    return user
