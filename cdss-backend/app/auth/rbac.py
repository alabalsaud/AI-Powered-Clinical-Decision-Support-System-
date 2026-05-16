"""
Role-based access control for FastAPI routes.

Usage::

    @router.get("/team", dependencies=[Depends(role_required(["physician", "nurse", "admin"]))])
    def team_board(): ...

    # or inject the user:
    @router.get("/chart")
    def chart(user: User = Depends(role_required(["physician", "admin"]))):
        ...
"""
from __future__ import annotations

from typing import Callable, Iterable, List

from fastapi import Depends, HTTPException, status

from app.auth.jwt_auth import get_current_user
from app.models.models import User, UserRole


def _normalize_role(name: str) -> UserRole:
    n = (name or "").strip().lower()
    if n == "admin":
        n = "administrator"
    try:
        return UserRole(n)
    except ValueError as e:
        raise ValueError(f"Unknown role: {name!r}") from e


def role_required(roles: Iterable[str]) -> Callable[..., User]:
    """
    Build a FastAPI dependency that requires the current user's role to be one of ``roles``.

    Accepts ``'physician'``, ``'nurse'``, ``'pharmacist'``, ``'administrator'``, and ``'admin'``
    (alias for administrator).
    """
    allowed: List[UserRole] = []
    for r in roles:
        allowed.append(_normalize_role(str(r)))
    allowed_set = set(allowed)

    def _checker(current_user: User = Depends(get_current_user)) -> User:
        role = current_user.role
        if role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this resource",
            )
        return current_user

    return _checker
