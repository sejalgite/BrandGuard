import enum
import uuid
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Numeric, DateTime, Enum,
    ForeignKeyConstraint, UniqueConstraint, CheckConstraint, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class DetectionCategory(str, enum.Enum):
    TONE = "TONE"
    TERMINOLOGY = "TERMINOLOGY"
    MESSAGING = "MESSAGING"
    VISUAL = "VISUAL"
    ACCESSIBILITY = "ACCESSIBILITY"
    CLAIMS = "CLAIMS"


class SeverityLevel(str, enum.Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    EDITED = "EDITED"
    DISPUTED = "DISPUTED"
    DISMISSED = "DISMISSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class FindingSource(str, enum.Enum):
    DETERMINISTIC_ENGINE = "DETERMINISTIC_ENGINE"
    LIVE_LLM = "LIVE_LLM"


class EvidenceEntityType(str, enum.Enum):
    RULE = "RULE"
    FACT = "FACT"
    TERM = "TERM"
    ASSET = "ASSET"


class ReviewJob(Base):
    __tablename__ = "review_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    document_id = Column(UUID(as_uuid=True), nullable=False)
    version_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(String(50), nullable=False, default="RUNNING")
    trigger_type = Column(String(50), nullable=False, default="MANUAL")
    total_findings = Column(Integer, nullable=False, default=0)
    categories_analyzed = Column(JSONB, nullable=False, default=list)
    execution_metadata = Column(JSONB, nullable=False, default=dict)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_id", "version_id"],
            ["document_versions.organization_id", "document_versions.document_id", "document_versions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "id", name="uq_jobs_org_id"),
        UniqueConstraint("organization_id", "document_id", "version_id", "id", name="uq_jobs_org_doc_ver_id"),
    )

    version = relationship("DocumentVersion", back_populates="review_jobs")
    findings = relationship("Finding", back_populates="job", cascade="all, delete-orphan")


class Finding(Base):
    __tablename__ = "findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    constitution_id = Column(UUID(as_uuid=True), nullable=False)
    document_id = Column(UUID(as_uuid=True), nullable=False)
    version_id = Column(UUID(as_uuid=True), nullable=False)
    job_id = Column(UUID(as_uuid=True), nullable=False)
    category = Column(Enum(DetectionCategory, name="detection_category"), nullable=False)
    severity = Column(Enum(SeverityLevel, name="severity_level"), nullable=False)
    confidence = Column(Numeric(4, 3), nullable=False)
    flagged_snippet = Column(Text, nullable=False)
    char_offset_start = Column(Integer)
    char_offset_end = Column(Integer)
    explanation = Column(Text, nullable=False)
    segment_id = Column(String(100))
    suggested_correction = Column(Text)

    # Typed Evidence References
    evidence_type = Column(Enum(EvidenceEntityType, name="evidence_entity_type"), nullable=False)
    rule_id = Column(UUID(as_uuid=True))
    fact_id = Column(UUID(as_uuid=True))
    term_id = Column(UUID(as_uuid=True))
    asset_id = Column(UUID(as_uuid=True))
    cited_code = Column(String(50), nullable=False)

    source = Column(Enum(FindingSource, name="finding_source"), nullable=False)
    status = Column(Enum(FindingStatus, name="finding_status"), nullable=False, default=FindingStatus.OPEN)
    verified_by_gate = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["review_jobs.organization_id", "review_jobs.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_id", "version_id"],
            ["document_versions.organization_id", "document_versions.document_id", "document_versions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "constitution_id"],
            ["brand_constitutions.organization_id", "brand_constitutions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "constitution_id", "rule_id"],
            ["brand_rules.organization_id", "brand_rules.constitution_id", "brand_rules.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "constitution_id", "fact_id"],
            ["fact_registry.organization_id", "fact_registry.constitution_id", "fact_registry.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "constitution_id", "term_id"],
            ["term_bank.organization_id", "term_bank.constitution_id", "term_bank.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "constitution_id", "asset_id"],
            ["brand_assets.organization_id", "brand_assets.constitution_id", "brand_assets.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_findings_org_id"),
        UniqueConstraint("organization_id", "document_id", "version_id", "id", name="uq_findings_org_doc_ver_id"),
        CheckConstraint(
            "((rule_id IS NOT NULL)::int + (fact_id IS NOT NULL)::int + (term_id IS NOT NULL)::int + (asset_id IS NOT NULL)::int) = 1",
            name="chk_exactly_one_evidence"
        ),
        CheckConstraint(
            "(evidence_type = 'RULE' AND rule_id IS NOT NULL) OR "
            "(evidence_type = 'FACT' AND fact_id IS NOT NULL) OR "
            "(evidence_type = 'TERM' AND term_id IS NOT NULL) OR "
            "(evidence_type = 'ASSET' AND asset_id IS NOT NULL)",
            name="chk_evidence_type_match"
        ),
        CheckConstraint(
            "confidence >= 0.000 AND confidence <= 1.000",
            name="chk_finding_confidence"
        ),
        CheckConstraint(
            "char_offset_start IS NULL OR (char_offset_start >= 0 AND (char_offset_end IS NULL OR char_offset_end >= char_offset_start))",
            name="chk_finding_char_offsets"
        ),
    )

    job = relationship("ReviewJob", back_populates="findings")
    corrections = relationship("SuggestedCorrection", back_populates="finding", cascade="all, delete-orphan")
    disputes = relationship("Dispute", back_populates="finding", cascade="all, delete-orphan")


class SuggestedCorrection(Base):
    __tablename__ = "suggested_corrections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    finding_id = Column(UUID(as_uuid=True), nullable=False)
    option_label = Column(String(50), nullable=False)
    suggested_text = Column(Text, nullable=False)
    intent_preserved = Column(Boolean, nullable=False, default=True)
    routing_action = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "finding_id"],
            ["findings.organization_id", "findings.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "id", name="uq_corrections_org_id"),
    )

    finding = relationship("Finding", back_populates="corrections")


class Dispute(Base):
    __tablename__ = "disputes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    finding_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    justification = Column(Text, nullable=False)
    resolved_by = Column(UUID(as_uuid=True))
    resolution_status = Column(String(50), nullable=False, default="PENDING")
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "finding_id"],
            ["findings.organization_id", "findings.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "resolved_by"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id", name="uq_disputes_org_id"),
    )

    finding = relationship("Finding", back_populates="disputes")

