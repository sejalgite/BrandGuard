import uuid
from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey,
    ForeignKeyConstraint, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    actor_id = Column(UUID(as_uuid=True))
    action = Column(String(100), nullable=False)
    target_entity = Column(String(100), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)
    version_number = Column(Integer)
    details = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "actor_id"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
    )

    organization = relationship("Organization", back_populates="audit_logs")


class AIDisclosureLog(Base):
    __tablename__ = "ai_disclosure_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    review_job_id = Column(UUID(as_uuid=True), nullable=False)
    model_name = Column(String(100), nullable=False)
    prompt_type = Column(String(100), nullable=False)
    tokens_prompt = Column(Integer)
    tokens_completion = Column(Integer)
    redacted_preview_hash = Column(String(64), nullable=False)  # SHA-256 hash ONLY
    latency_ms = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "review_job_id"],
            ["review_jobs.organization_id", "review_jobs.id"],
            ondelete="CASCADE",
        ),
    )

