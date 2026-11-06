"""
app/services/workflow/notification_service.py
In-App Notification Dispatcher and Query Service (Phase 6).
Handles dispatching notifications for workflow events and deduplicating
repeated alerts.
"""
import uuid
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.notification import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """Manages dispatch and retrieval of organization-scoped in-app notifications."""

    @staticmethod
    def send_notification(
        db: Session,
        organization_id: uuid.UUID,
        recipient_id: uuid.UUID,
        title: str,
        message: str,
        notification_type: str,
        actor_id: Optional[uuid.UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[uuid.UUID] = None
    ) -> Notification:
        """Create and persist an unread in-app notification."""
        # Avoid duplicate unread notification for the exact same event
        existing = db.query(Notification).filter(
            Notification.organization_id == organization_id,
            Notification.recipient_id == recipient_id,
            Notification.notification_type == notification_type,
            Notification.resource_id == resource_id,
            Notification.is_read == False
        ).first()

        if existing:
            # Update message and timestamp instead of spamming duplicates
            existing.message = message
            existing.title = title
            db.commit()
            db.refresh(existing)
            return existing

        notif = Notification(
            organization_id=organization_id,
            recipient_id=recipient_id,
            actor_id=actor_id,
            title=title,
            message=message,
            notification_type=notification_type,
            resource_type=resource_type,
            resource_id=resource_id,
            is_read=False
        )
        db.add(notif)
        db.commit()
        db.refresh(notif)
        return notif

    @staticmethod
    def get_user_notifications(
        db: Session,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        unread_only: bool = False,
        limit: int = 50
    ) -> List[Notification]:
        """Fetch notifications for the current authenticated user."""
        q = db.query(Notification).filter(
            Notification.organization_id == organization_id,
            Notification.recipient_id == user_id
        )
        if unread_only:
            q = q.filter(Notification.is_read == False)
        return q.order_by(desc(Notification.created_at)).limit(limit).all()

    @staticmethod
    def mark_as_read(
        db: Session,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        notification_id: uuid.UUID
    ) -> Optional[Notification]:
        """Mark a notification as read."""
        notif = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.organization_id == organization_id,
            Notification.recipient_id == user_id
        ).first()
        if notif:
            notif.is_read = True
            db.commit()
            db.refresh(notif)
        return notif

    @staticmethod
    def mark_all_as_read(
        db: Session,
        organization_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> int:
        """Mark all unread notifications for user as read."""
        count = db.query(Notification).filter(
            Notification.organization_id == organization_id,
            Notification.recipient_id == user_id,
            Notification.is_read == False
        ).update({"is_read": True})
        db.commit()
        return count

