"""
app/schemas/evaluation.py
Pydantic schemas for Phase 7: Detection Evaluation, Benchmark Datasets & Reliability Engine.
"""
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class EvaluationTestCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    test_code: str
    title: str
    content_type: str
    input_content: str
    content_metadata: Optional[Dict[str, Any]] = {}
    expected_findings: List[Dict[str, Any]] = []
    expected_compliant: bool
    is_ambiguous: bool
    target_category: Optional[str] = None
    created_at: datetime


class EvaluationDatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: Optional[str] = None
    dataset_type: str
    version: str
    is_active: bool
    test_cases_count: Optional[int] = 0
    created_at: datetime
    updated_at: datetime


class EvaluationRunTriggerRequest(BaseModel):
    dataset_id: uuid.UUID
    engine_version: Optional[str] = "1.0.0-phase7"
    run_type: Optional[str] = "BENCHMARK"


class CategoryMetricDetail(BaseModel):
    tp: int
    fp: int
    fn: int
    expected: int
    predicted: int
    precision: float
    recall: float
    f1: float
    coverage: float


class TestCaseResultItem(BaseModel):
    test_code: str
    title: str
    target_category: Optional[str] = None
    expected_count: int
    predicted_count: int
    tp: int
    fp: int
    fn: int
    passed: bool
    is_ambiguous: bool
    verified_rate: float
    predicted_snippets: List[str] = []
    expected_snippets: List[str] = []


class EvaluationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_name: Optional[str] = None
    engine_version: str
    run_type: str
    total_cases: int
    overall_precision: float
    overall_recall: float
    overall_f1: float
    overall_accuracy: float
    test_case_pass_rate: Optional[float] = None
    document_accuracy: Optional[float] = None
    macro_precision: Optional[float] = None
    macro_recall: Optional[float] = None
    macro_f1: Optional[float] = None
    total_tp: Optional[int] = None
    total_fp: Optional[int] = None
    total_fn: Optional[int] = None
    passed_cases: Optional[int] = None
    category_metrics: Dict[str, CategoryMetricDetail]
    case_results: List[TestCaseResultItem] = []
    triggered_by: Optional[uuid.UUID] = None
    created_at: datetime


class RulePerformanceStat(BaseModel):
    rule_id: str
    rule_code: str
    title: str
    category: str
    total_decisions: int
    accepted_count: int
    dismissed_count: int
    disputed_count: int
    resolved_count: int
    dispute_rate: float
    dismissal_rate: float
    ambiguity_score: float
    detected_vague_terms: List[str]
    needs_review: bool


class RecommendationResponse(BaseModel):
    id: str
    recommendation_type: str
    target_rule_code: str
    target_rule_title: str
    severity: str
    issue_summary: str
    action_suggested: str
    requires_human_approval: bool
    applied: bool


class QualityDashboardSummary(BaseModel):
    latest_run: Optional[EvaluationRunResponse] = None
    total_datasets: int
    total_benchmark_cases: int
    overall_precision: float
    overall_recall: float
    overall_f1: float
    overall_accuracy: float
    test_case_pass_rate: Optional[float] = None
    document_accuracy: Optional[float] = None
    macro_precision: Optional[float] = None
    macro_recall: Optional[float] = None
    macro_f1: Optional[float] = None
    overall_verification_rate: float
    category_scores: Dict[str, Dict[str, float]]
    historical_runs_count: int
    top_disputed_rules: List[RulePerformanceStat] = []
    recommendations_count: int

