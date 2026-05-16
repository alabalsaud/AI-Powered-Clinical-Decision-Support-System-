"""
Audit logging service (NFR12, FR9).
All clinical actions are logged with user, resource, and detail.
Logs are retained and protected per SRS requirements.
"""

from typing import Optional
from sqlalchemy.orm import Session
from app.models.models import AuditLog


def log_action(
    db: Session,
    action: str,
    user_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    detail: Optional[str] = None,
    ip_address: Optional[str] = None,
    log_type: str = "data",
) -> AuditLog:
    """
    Create an audit log entry. Called after every significant system action.
    log_type: auth | data | clinical | prescription
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
        log_type=log_type,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
