"""
app/models/notification.py
In-App Notification Model for Review & Governance Workflow (Phase 6).
Tracks asynchronous notifications for review assignments, submissions,
change requests, comments, and approvals with unread/read state.
"""
import uuid
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime,
    ForeignKeyConstraint, UniqueConstraint, Index, text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Notification(Base):
    """
    In-app notification entity.
    Scoped strictly by organization and target user.
    """
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    recipient_id = Column(UUID(as_uuid=True), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=True)

    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(50), nullable=False)
    # Types: REVIEW_ASSIGNED, REVIEW_SUBMITTED, CHANGES_REQUESTED,
    #        DOCUMENT_RESUBMITTED, COMMENT_RECEIVED, APPROVAL_GRANTED,
    #        REVIEW_REJECTED, LEGAL_REVIEW_REQUESTED

    resource_type = Column(String(50), nullable=True)  # e.g. "review", "document"
    resource_id = Column(UUID(as_uuid=True), nullable=True)

    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "recipient_id"],
            ["users.organization_id", "users.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_id"],
            ["users.organization_id", "users.id"],
            ondelete="SET NULL",
        ),
        UniqueConstraint("organization_id", "id", name="uq_notifications_org_id"),
        Index("ix_notifications_recipient_unread", "organization_id", "recipient_id", "is_read"),
        Index("ix_notifications_created_at", "organization_id", "created_at"),
    )

    recipient = relationship("User", foreign_keys=[recipient_id], primaryjoin="Notification.recipient_id == User.id")
    actor = relationship("User", foreign_keys=[actor_id], primaryjoin="Notification.actor_id == User.id")

