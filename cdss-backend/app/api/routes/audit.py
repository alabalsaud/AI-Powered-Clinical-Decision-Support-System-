"""
app/api/routes/audit.py — NFR12 (admin-only listing).
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.models.models import User, AuditLog
from app.schemas.schemas import AuditLogWithUserOut
from app.core.security import require_admin

router = APIRouter(prefix="/audit", tags=["Audit Logs"])


@router.get("/", response_model=List[AuditLogWithUserOut])
def get_audit_logs(
    log_type: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None, description="Filter by user who triggered the event"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(AuditLog).options(joinedload(AuditLog.user))
    if log_type:
        q = q.filter(AuditLog.log_type == log_type)
    if user_id is not None:
        q = q.filter(AuditLog.user_id == user_id)
    logs = q.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    out: List[AuditLogWithUserOut] = []
    for log in logs:
        u = log.user
        out.append(
            AuditLogWithUserOut(
                id=log.id,
                user_id=log.user_id,
                user_email=u.email if u else None,
                user_full_name=u.full_name if u else None,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                detail=log.detail,
                ip_address=log.ip_address,
                log_type=log.log_type,
                created_at=log.created_at,
            )
        )
    return out
