import uuid
from sqlalchemy import (
    Column, String, Text, DateTime, Enum,
    ForeignKeyConstraint, UniqueConstraint, text
)
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.user import UserRole


class ReviewAssignment(Base):
    __tablename__ = "review_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    document_id = Column(UUID(as_uuid=True), nullable=False)
    version_id = Column(UUID(as_uuid=True), nullable=False)
    assigned_user_id = Column(UUID(as_uuid=True), nullable=False)
    assigned_by = Column(UUID(as_uuid=True), nullable=False)
    role_required = Column(Enum(UserRole, name="user_role"), nullable=False)
    status = Column(String(50), nullable=False, default="PENDING")
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_id", "version_id"],
            ["document_versions.organization_id", "document_versions.document_id", "document_versions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assigned_user_id"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assigned_by"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_assignments_org_id"),
    )


class Comment(Base):
    __tablename__ = "comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    document_id = Column(UUID(as_uuid=True), nullable=False)
    version_id = Column(UUID(as_uuid=True), nullable=False)
    review_id = Column(UUID(as_uuid=True), nullable=True)
    finding_id = Column(UUID(as_uuid=True))
    user_id = Column(UUID(as_uuid=True), nullable=False)
    parent_comment_id = Column(UUID(as_uuid=True))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_id", "version_id"],
            ["document_versions.organization_id", "document_versions.document_id", "document_versions.id"],
            ondelete="CASCADE",
        ),
        # Safeguard: Comment can only reference a finding belonging to the SAME org, doc, and version
        ForeignKeyConstraint(
            ["organization_id", "document_id", "version_id", "finding_id"],
            ["findings.organization_id", "findings.document_id", "findings.version_id", "findings.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "document_id", "version_id", "id", name="uq_comments_org_doc_ver_id"),
        # Reply must belong to the exact same organization, document, and version
        ForeignKeyConstraint(
            ["organization_id", "document_id", "version_id", "parent_comment_id"],
            ["comments.organization_id", "comments.document_id", "comments.version_id", "comments.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "id", name="uq_comments_org_id"),
    )

