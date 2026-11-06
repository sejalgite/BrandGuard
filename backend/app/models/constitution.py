import enum
import uuid
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Date, Numeric, Enum,
    ForeignKey, ForeignKeyConstraint, UniqueConstraint, ARRAY, JSON, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.database import Base


class RuleCategory(str, enum.Enum):
    TONE_VOICE = "TONE_VOICE"
    WRITING_STYLE = "WRITING_STYLE"
    MESSAGING_PILLAR = "MESSAGING_PILLAR"
    VISUAL = "VISUAL"
    ACCESSIBILITY = "ACCESSIBILITY"


class EntityStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"
    EXPIRED = "EXPIRED"


class BrandConstitution(Base):
    __tablename__ = "brand_constitutions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    version = Column(String(50), default="1.0")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_constitutions_org_id"),
    )

    organization = relationship("Organization", back_populates="constitutions")
    rules = relationship("BrandRule", back_populates="constitution", cascade="all, delete-orphan")
    facts = relationship("FactRegistry", back_populates="constitution", cascade="all, delete-orphan")
    terms = relationship("TermBank", back_populates="constitution", cascade="all, delete-orphan")
    assets = relationship("BrandAsset", back_populates="constitution", cascade="all, delete-orphan")


class BrandRule(Base):
    __tablename__ = "brand_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    constitution_id = Column(UUID(as_uuid=True), nullable=False)
    rule_code = Column(String(50), nullable=False)
    category = Column(Enum(RuleCategory, name="rule_category"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    examples_positive = Column(ARRAY(Text))
    examples_negative = Column(ARRAY(Text))
    embedding = Column(Vector(384))
    status = Column(Enum(EntityStatus, name="entity_status"), nullable=False, default=EntityStatus.ACTIVE)
    approved_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "constitution_id"],
            ["brand_constitutions.organization_id", "brand_constitutions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "approved_by"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "constitution_id", "id", name="uq_rules_org_const_id"),
        UniqueConstraint("constitution_id", "rule_code", name="uq_constitution_rule_code"),
    )

    constitution = relationship("BrandConstitution", back_populates="rules")


class FactRegistry(Base):
    __tablename__ = "fact_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    constitution_id = Column(UUID(as_uuid=True), nullable=False)
    fact_code = Column(String(50), nullable=False)
    claim_type = Column(String(100), nullable=False)
    statement = Column(Text, nullable=False)
    numerical_value = Column(Numeric)
    unit = Column(String(50))
    source_reference = Column(String(255), nullable=False)
    fact_owner = Column(String(255), nullable=False)
    expiry_date = Column(Date, nullable=False)
    embedding = Column(Vector(384))
    status = Column(Enum(EntityStatus, name="entity_status"), nullable=False, default=EntityStatus.ACTIVE)
    approved_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "constitution_id"],
            ["brand_constitutions.organization_id", "brand_constitutions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "approved_by"],
            ["users.organization_id", "users.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "constitution_id", "id", name="uq_facts_org_const_id"),
        UniqueConstraint("constitution_id", "fact_code", name="uq_constitution_fact_code"),
    )

    constitution = relationship("BrandConstitution", back_populates="facts")


class TermBank(Base):
    __tablename__ = "term_bank"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    constitution_id = Column(UUID(as_uuid=True), nullable=False)
    term_code = Column(String(50), nullable=False)
    prohibited_term = Column(String(255), nullable=False)
    preferred_term = Column(String(255), nullable=False)
    usage_context = Column(Text)
    is_case_sensitive = Column(Boolean, nullable=False, default=False)
    status = Column(Enum(EntityStatus, name="entity_status"), nullable=False, default=EntityStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "constitution_id"],
            ["brand_constitutions.organization_id", "brand_constitutions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "constitution_id", "id", name="uq_terms_org_const_id"),
        UniqueConstraint("constitution_id", "term_code", name="uq_constitution_term_code"),
    )

    constitution = relationship("BrandConstitution", back_populates="terms")


class BrandAsset(Base):
    __tablename__ = "brand_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    constitution_id = Column(UUID(as_uuid=True), nullable=False)
    asset_code = Column(String(50), nullable=False)
    asset_type = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    specifications = Column(JSONB, nullable=False)
    file_path = Column(String(500))
    status = Column(Enum(EntityStatus, name="entity_status"), nullable=False, default=EntityStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "constitution_id"],
            ["brand_constitutions.organization_id", "brand_constitutions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "constitution_id", "id", name="uq_assets_org_const_id"),
        UniqueConstraint("constitution_id", "asset_code", name="uq_constitution_asset_code"),
    )

    constitution = relationship("BrandConstitution", back_populates="assets")

