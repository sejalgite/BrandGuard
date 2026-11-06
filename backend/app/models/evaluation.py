"""
app/models/evaluation.py
SQLAlchemy models for Phase 7: Detection Evaluation, Benchmark Datasets & Reliability Engine.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float, DateTime, ForeignKey, text,
    ForeignKeyConstraint, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class EvaluationDataset(Base):
    """
    Structured benchmark or regression evaluation dataset containing test cases.
    """
    __tablename__ = "evaluation_datasets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    dataset_type = Column(String(50), nullable=False, default="BENCHMARK")  # BENCHMARK, REGRESSION, SYNTHETIC
    version = Column(String(50), nullable=False, default="1.0")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "name", "version", name="uq_evaluation_datasets_org_name_ver"),
        Index("ix_evaluation_datasets_org", "organization_id"),
    )

    test_cases = relationship("EvaluationTestCase", back_populates="dataset", cascade="all, delete-orphan")
    runs = relationship("EvaluationRun", back_populates="dataset", cascade="all, delete-orphan")


class EvaluationTestCase(Base):
    """
    Single ground-truth test document with expected violations or clean assertion.
    """
    __tablename__ = "evaluation_test_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), nullable=False)

    test_code = Column(String(100), nullable=False)  # e.g., TC-TONE-01
    title = Column(String(255), nullable=False)
    content_type = Column(String(50), nullable=False, default="TEXT")
    input_content = Column(Text, nullable=False)
    content_metadata = Column(JSONB, nullable=True, default=dict)
    
    # Expected ground truth: list of objects with category, snippet, cited_code, severity, explanation
    expected_findings = Column(JSONB, nullable=False, default=list)
    expected_compliant = Column(Boolean, nullable=False, default=False)
    is_ambiguous = Column(Boolean, nullable=False, default=False)
    target_category = Column(String(50), nullable=True)  # TONE, TERMINOLOGY, CLAIMS, etc.

    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "dataset_id", "test_code", name="uq_evaluation_test_cases_code"),
        Index("ix_evaluation_test_cases_dataset", "dataset_id"),
        Index("ix_evaluation_test_cases_org", "organization_id"),
    )

    dataset = relationship("EvaluationDataset", back_populates="test_cases")


class EvaluationRun(Base):
    """
    Persisted evaluation execution recording exact category-level metrics (P, R, F1),
    case outcomes, and engine version for regression comparisons.
    """
    __tablename__ = "evaluation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), nullable=False)

    engine_version = Column(String(50), nullable=False, default="1.0.0-phase7")
    run_type = Column(String(50), nullable=False, default="BENCHMARK")  # BENCHMARK, REGRESSION
    total_cases = Column(Integer, nullable=False, default=0)

    overall_precision = Column(Float, nullable=False, default=0.0)
    overall_recall = Column(Float, nullable=False, default=0.0)
    overall_f1 = Column(Float, nullable=False, default=0.0)
    overall_accuracy = Column(Float, nullable=False, default=0.0)

    # Keyed by category: {"TONE": {"tp": 10, "fp": 1, "fn": 0, "precision": 0.91, "recall": 1.0, "f1": 0.95, "coverage": 1.0}, ...}
    category_metrics = Column(JSONB, nullable=False, default=dict)
    
    # Detailed result per test case
    case_results = Column(JSONB, nullable=False, default=list)

    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        Index("ix_evaluation_runs_org", "organization_id"),
        Index("ix_evaluation_runs_dataset", "dataset_id"),
        Index("ix_evaluation_runs_created", "created_at"),
    )

    dataset = relationship("EvaluationDataset", back_populates="runs")
    user = relationship("User", foreign_keys=[triggered_by])
