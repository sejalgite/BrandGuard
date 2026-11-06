"""
app/api/v1/notifications.py
In-App Notifications API Endpoints (Phase 6).
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.schemas.review import NotificationResponse
from app.services.workflow.notification_service import NotificationService

router = APIRouter()


@router.get("", response_model=List[NotificationResponse])
def get_my_notifications(
    unread_only: bool = Query(False, description="Filter only unread notifications"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve notifications for the authenticated user in their organization."""
    notifs = NotificationService.get_user_notifications(
        db=db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        unread_only=unread_only,
        limit=limit
    )
    return [
        NotificationResponse(
            id=n.id,
            title=n.title,
            message=n.message,
            notification_type=n.notification_type,
            resource_type=n.resource_type,
            resource_id=n.resource_id,
            is_read=n.is_read,
            created_at=n.created_at
        )
        for n in notifs
    ]


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a specific notification as read."""
    notif = NotificationService.mark_as_read(
        db=db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        notification_id=notification_id
    )
    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification {notification_id} not found."
        )
    return NotificationResponse(
        id=notif.id,
        title=notif.title,
        message=notif.message,
        notification_type=notif.notification_type,
        resource_type=notif.resource_type,
        resource_id=notif.resource_id,
        is_read=notif.is_read,
        created_at=notif.created_at
    )


@router.post("/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all unread notifications as read for current user."""
    count = NotificationService.mark_all_as_read(
        db=db,
        organization_id=current_user.organization_id,
        user_id=current_user.id
    )
    return {"marked_read": count}

