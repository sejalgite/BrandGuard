"""
app/models/review.py
SQLAlchemy models for Human Review, Approval & Governance Workflow (Phase 6).
Includes Review, ReviewHistory, and FindingDecision with multi-tenant isolation,
composite foreign key referential integrity, and complete action auditability.
"""
import enum
import uuid
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, DateTime, Enum,
    ForeignKeyConstraint, UniqueConstraint, Index, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class ReviewStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    RESUBMITTED = "RESUBMITTED"
    PENDING_BRAND_APPROVAL = "PENDING_BRAND_APPROVAL"
    PENDING_LEGAL_APPROVAL = "PENDING_LEGAL_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class FindingDecisionType(str, enum.Enum):
    ACCEPTED = "ACCEPTED"
    DISMISSED = "DISMISSED"
    DISPUTED = "DISPUTED"
    RESOLVED = "RESOLVED"
    CORRECTION_REQUESTED = "CORRECTION_REQUESTED"


class Review(Base):
    """
    Core human review lifecycle entity. Connects an immutable document version
    and its analysis findings with creator, reviewers, legal sign-off, and final decisions.
    """
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    document_id = Column(UUID(as_uuid=True), nullable=False)
    version_id = Column(UUID(as_uuid=True), nullable=False)
    job_id = Column(UUID(as_uuid=True), nullable=True)  # Associated review_job (analysis run)

    creator_id = Column(UUID(as_uuid=True), nullable=False)
    assigned_reviewer_id = Column(UUID(as_uuid=True), nullable=True)
    legal_reviewer_id = Column(UUID(as_uuid=True), nullable=True)

    status = Column(
        Enum(ReviewStatus, name="review_workflow_status"),
        nullable=False,
        default=ReviewStatus.DRAFT
    )
    priority = Column(String(20), nullable=False, default="NORMAL")  # LOW, NORMAL, HIGH, URGENT
    due_date = Column(DateTime(timezone=True), nullable=True)

    legal_review_required = Column(Boolean, nullable=False, default=False)
    legal_status = Column(String(50), nullable=False, default="NOT_REQUIRED")  # NOT_REQUIRED, PENDING, APPROVED, REJECTED

    final_decision_by = Column(UUID(as_uuid=True), nullable=True)
    final_decision_at = Column(DateTime(timezone=True), nullable=True)
    decision_notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_id", "version_id"],
            ["document_versions.organization_id", "document_versions.document_id", "document_versions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "creator_id"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assigned_reviewer_id"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "legal_reviewer_id"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "final_decision_by"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_reviews_org_id"),
        UniqueConstraint("organization_id", "document_id", "version_id", "id", name="uq_reviews_org_doc_ver_id"),
        Index("ix_reviews_org_status", "organization_id", "status"),
        Index("ix_reviews_assigned_reviewer", "organization_id", "assigned_reviewer_id"),
        Index("ix_reviews_doc_version", "organization_id", "document_id", "version_id"),
    )

    # Relationships
    document = relationship("Document", foreign_keys=[document_id], primaryjoin="Review.document_id == Document.id")
    version = relationship("DocumentVersion", foreign_keys=[version_id], primaryjoin="Review.version_id == DocumentVersion.id")
    creator = relationship("User", foreign_keys=[creator_id], primaryjoin="Review.creator_id == User.id")
    assigned_reviewer = relationship("User", foreign_keys=[assigned_reviewer_id], primaryjoin="Review.assigned_reviewer_id == User.id")
    legal_reviewer = relationship("User", foreign_keys=[legal_reviewer_id], primaryjoin="Review.legal_reviewer_id == User.id")
    final_decider = relationship("User", foreign_keys=[final_decision_by], primaryjoin="Review.final_decision_by == User.id")

    history = relationship("ReviewHistory", back_populates="review", cascade="all, delete-orphan", order_by="ReviewHistory.created_at.asc()")
    finding_decisions = relationship("FindingDecision", back_populates="review", cascade="all, delete-orphan")


class ReviewHistory(Base):
    """
    Immutable state transition log for review workflow.
    Records every status change, action, actor, and comment/reason.
    """
    __tablename__ = "review_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    review_id = Column(UUID(as_uuid=True), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=False)

    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)  # e.g. SUBMIT, START_REVIEW, REQUEST_CHANGES, RESUBMIT, APPROVE, REJECT, WITHDRAW
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "review_id"],
            ["reviews.organization_id", "reviews.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_id"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_review_history_org_id"),
        Index("ix_review_history_review_id", "organization_id", "review_id", "created_at"),
    )

    review = relationship("Review", back_populates="history")
    actor = relationship("User", foreign_keys=[actor_id], primaryjoin="ReviewHistory.actor_id == User.id")


class FindingDecision(Base):
    """
    Formal human review decision on an individual compliance finding.
    Preserves decision, justification reason, reviewer identity, and timestamp.
    """
    __tablename__ = "finding_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    review_id = Column(UUID(as_uuid=True), nullable=False)
    finding_id = Column(UUID(as_uuid=True), nullable=False)
    decided_by = Column(UUID(as_uuid=True), nullable=False)

    decision = Column(
        Enum(FindingDecisionType, name="finding_decision_type"),
        nullable=False
    )
    reason = Column(Text, nullable=True)  # Mandatory for DISMISSED and DISPUTED
    suggested_correction = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "review_id"],
            ["reviews.organization_id", "reviews.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "finding_id"],
            ["findings.organization_id", "findings.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "decided_by"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_finding_decisions_org_id"),
        Index("ix_finding_decisions_finding", "organization_id", "finding_id"),
        Index("ix_finding_decisions_review", "organization_id", "review_id"),
    )

    review = relationship("Review", back_populates="finding_decisions")
    finding = relationship("Finding", foreign_keys=[finding_id], primaryjoin="FindingDecision.finding_id == Finding.id")
    decider = relationship("User", foreign_keys=[decided_by], primaryjoin="FindingDecision.decided_by == User.id")

