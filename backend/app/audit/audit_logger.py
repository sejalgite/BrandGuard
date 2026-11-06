"""
app/audit/audit_logger.py
Utility to append rows to the audit_logs table.

Rules:
- Must be called within an active SQLAlchemy transaction (the caller's db session).
- Never commits or rolls back; that is the caller's responsibility.
- actor_id may be None for system-generated events (e.g. automated jobs).
"""
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def log_action(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: Optional[uuid.UUID],
    action: str,
    target_entity: str,
    target_id: uuid.UUID,
    details: Optional[dict] = None,
    version_number: Optional[int] = None,
) -> AuditLog:
    """
    Insert one immutable audit-log record and add it to *db* (unflushed).

    The caller must commit the session for the record to persist.  If the
    enclosing transaction rolls back, this record is discarded with it —
    which is intentional: a failed action must not appear in audit history.
    """
    entry = AuditLog(
        id=uuid.uuid4(),
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        target_entity=target_entity,
        target_id=target_id,
        details=details,
        version_number=version_number,
    )
    db.add(entry)
    return entry

