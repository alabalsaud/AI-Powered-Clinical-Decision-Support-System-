"""
Admin-only routes: user directory and deactivation (physicians/staff).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import User, UserRole
from app.schemas.schemas import UserOut
from app.core.security import require_admin
from app.services.audit import log_action

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(User)
    if not include_inactive:
        q = q.filter(User.is_active == True)
    return q.order_by(User.full_name.asc()).all()


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_staff_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot deactivate your own account")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    if target.role == UserRole.administrator:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Administrator accounts cannot be deactivated via this endpoint",
        )

    if not target.is_active:
        return None

    target.is_active = False
    db.commit()

    log_action(
        db,
        "User Deactivated by Admin",
        user_id=admin.id,
        resource_type="user",
        resource_id=target.id,
        detail=f"Admin deactivated user: {target.email} ({target.role})",
        ip_address=request.client.host if request.client else None,
        log_type="auth",
    )
    return None
