import bcrypt
from fastapi import Depends, HTTPException, status

from app.models.models import UserRole

# Re-export JWT helpers from auth layer (assignment: auth/jwt_auth.py)
from app.auth.jwt_auth import (
    bearer_scheme,
    create_access_token,
    decode_token,
    get_current_user,
    verify_token,
)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except ValueError:
        # Handle case where hash is invalid
        return False


def require_admin(current_user=Depends(get_current_user)):
    """Only users with role *administrator* may access admin-only routes."""
    role = getattr(current_user, "role", None)
    role_val = role.value if hasattr(role, "value") else str(role)
    if role_val != UserRole.administrator.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return current_user


def require_clinical_staff(current_user=Depends(get_current_user)):
    """Block patient-role users from clinical-staff-only routes."""
    role = getattr(current_user, "role", None)
    role_val = role.value if hasattr(role, "value") else str(role)
    if role_val == UserRole.patient.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clinical staff access required",
        )
    return current_user
