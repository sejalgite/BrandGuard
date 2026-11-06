import enum
import uuid
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Numeric, DateTime, Enum,
    ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class DocumentLifecycleStatus(str, enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"


class VersionWorkflowStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ANALYZING = "ANALYZING"
    CHANGES_REQUIRED = "CHANGES_REQUIRED"
    REVIEW_PENDING = "REVIEW_PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    creator_id = Column(UUID(as_uuid=True), nullable=False)
    title = Column(String(255), nullable=False)
    content_type = Column(String(50), nullable=False)  # 'TEXT', 'DOCX', 'PDF', 'IMAGE'
    lifecycle_status = Column(
        Enum(DocumentLifecycleStatus, name="document_lifecycle_status"),
        nullable=False,
        default=DocumentLifecycleStatus.IN_PROGRESS
    )
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "creator_id"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_documents_org_id"),
    )

    organization = relationship("Organization", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    document_id = Column(UUID(as_uuid=True), nullable=False)
    version_number = Column(Integer, nullable=False)
    raw_content = Column(Text)
    file_path = Column(String(500))
    extracted_text = Column(Text)
    intent_lock = Column(JSONB)
    brand_health_score = Column(Numeric(5, 2))
    word_count = Column(Integer, nullable=False, default=0)
    version_status = Column(
        Enum(VersionWorkflowStatus, name="version_workflow_status"),
        nullable=False,
        default=VersionWorkflowStatus.DRAFT
    )
    is_locked = Column(Boolean, nullable=False, default=False)
    approved_at = Column(DateTime(timezone=True))
    approved_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    original_filename = Column(String(255))
    file_size_bytes = Column(Integer)
    mime_type = Column(String(100))
    extraction_status = Column(String(50), nullable=False, default="PENDING")
    extraction_metadata = Column(JSONB)
    structured_content = Column(JSONB)
    character_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "approved_by"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_versions_org_id"),
        UniqueConstraint("organization_id", "document_id", "id", name="uq_versions_org_doc_id"),
        UniqueConstraint("document_id", "version_number", name="uq_doc_version"),
        CheckConstraint(
            "version_status != 'APPROVED' OR is_locked = TRUE",
            name="chk_approved_is_locked"
        ),
        CheckConstraint(
            "brand_health_score IS NULL OR (brand_health_score >= 0.00 AND brand_health_score <= 100.00)",
            name="chk_version_brand_score"
        ),
        CheckConstraint("word_count >= 0", name="chk_version_word_count"),
    )

    document = relationship("Document", back_populates="versions")
    review_jobs = relationship("ReviewJob", back_populates="version", cascade="all, delete-orphan")

