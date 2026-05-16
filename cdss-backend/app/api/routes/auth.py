"""
app/api/routes/auth.py
Authentication routes (FR10) — login, register, logout.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import User, UserRole
from app.schemas.schemas import UserRegister, UserLogin, TokenResponse, UserOut
from app.core.security import hash_password, verify_password, create_access_token, get_current_user
from app.services.audit import log_action

router = APIRouter(prefix="/auth", tags=["Authentication"])

MAX_FAILED_ATTEMPTS = 5


def _strip_opt(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: UserRegister, request: Request, db: Session = Depends(get_db)):
    email_norm = str(payload.email).strip().lower()
    if db.query(User).filter(func.lower(User.email) == email_norm).first():
        raise HTTPException(400, "Email already registered")
    if db.query(User).filter(User.username == payload.username.strip()).first():
        raise HTTPException(400, "Username already taken")

    try:
        role_enum = UserRole(payload.role)
    except ValueError as e:
        raise HTTPException(400, f"Invalid role: {payload.role}") from e

    user = User(
        username=payload.username.strip(),
        email=str(payload.email).strip().lower(),
        full_name=payload.full_name.strip(),
        hashed_password=hash_password(payload.password),
        role=role_enum,
        license_number=_strip_opt(payload.license_number),
        profile_image=payload.profile_image,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(db, "User Registered", user_id=user.id,
               resource_type="user", resource_id=user.id,
               detail=f"New {user.role} account created: {user.email}",
               ip_address=request.client.host, log_type="auth")
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    email_norm = str(payload.email).strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email_norm).first()

    if not user:
        raise HTTPException(401, "Invalid credentials")

    # Account lockout (NFR5) — locked flag or failed count threshold
    if user.account_locked or user.failed_login_count >= MAX_FAILED_ATTEMPTS:
        log_action(db, "Login Blocked", user_id=user.id,
                   detail="Account locked — too many failed attempts",
                   ip_address=request.client.host, log_type="auth")
        raise HTTPException(403, f"Account locked after {MAX_FAILED_ATTEMPTS} failed attempts. Contact administrator.")

    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
            user.account_locked = True
        db.commit()
        remaining = max(0, MAX_FAILED_ATTEMPTS - user.failed_login_count)
        log_action(db, "Failed Login", user_id=user.id,
                   detail=f"Invalid password — {remaining} attempts remaining",
                   ip_address=request.client.host, log_type="auth")
        raise HTTPException(401, f"Invalid credentials. {remaining} attempt(s) remaining.")

    if not user.is_active:
        raise HTTPException(403, "Account is inactive. Contact administrator.")

    # Success — reset counter, update last_login
    user.failed_login_count = 0
    user.account_locked = False
    user.last_login = datetime.utcnow()
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id)})

    log_action(db, "Login", user_id=user.id,
               detail=f"Successful login: {user.email}",
               ip_address=request.client.host, log_type="auth")

    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db),
           current_user: User = Depends(get_current_user)):
    log_action(db, "Logout", user_id=current_user.id,
               detail=f"User logged out: {current_user.email}",
               ip_address=request.client.host, log_type="auth")
    return {"message": "Logged out successfully"}
