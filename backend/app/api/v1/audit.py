"""
app/api/v1/audit.py
Audit log inspection endpoints.
Enforces organization scoping and view_audit_logs permission.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.audit import AuditLog
from app.auth.dependencies import get_current_active_user
from app.auth.rbac import require_permission, PERM_VIEW_AUDIT_LOGS
from app.schemas.auth import AuditLogOut

router = APIRouter()


@router.get(
    "/logs",
    response_model=List[AuditLogOut],
    summary="List immutable audit trail for the caller's organisation",
    dependencies=[Depends(require_permission(PERM_VIEW_AUDIT_LOGS))],
)
def list_audit_logs(
    limit: int = Query(50, ge=1, le=500),
    action: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(AuditLog)
        .filter(AuditLog.organization_id == current_user.organization_id)
    )
    if action:
        query = query.filter(AuditLog.action == action)

    logs = (
        query
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return logs

