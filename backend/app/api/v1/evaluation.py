"""
app/api/v1/evaluation.py
REST API endpoints for Phase 7: Detection Evaluation, Quality Verification & Guideline Intelligence.
"""
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.user import User, UserRole
from app.models.evaluation import EvaluationDataset, EvaluationTestCase, EvaluationRun
from app.auth.dependencies import get_current_user
from app.audit.audit_logger import log_action
from app.schemas.evaluation import (
    EvaluationDatasetResponse,
    EvaluationTestCaseResponse,
    EvaluationRunTriggerRequest,
    EvaluationRunResponse,
    RulePerformanceStat,
    RecommendationResponse,
    QualityDashboardSummary
)
from app.services.evaluation.dataset_generator import EvaluationDatasetGenerator
from app.services.evaluation.evaluator import BenchmarkEvaluator
from app.services.evaluation.guideline_intelligence import GuidelineIntelligenceEngine

router = APIRouter()


@router.post("/datasets/seed", response_model=EvaluationDatasetResponse, status_code=status.HTTP_201_CREATED)
def seed_benchmark_dataset(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Seed the standard synthetic ApexCloud Benchmark Dataset for the current organization.
    """
    dataset = EvaluationDatasetGenerator.seed_apexcloud_benchmark(
        db=db,
        organization_id=current_user.organization_id
    )

    tc_count = db.query(EvaluationTestCase).filter(
        EvaluationTestCase.dataset_id == dataset.id
    ).count()

    log_action(
        db=db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="EVALUATION_DATASET_SEEDED",
        target_entity="evaluation_datasets",
        target_id=dataset.id,
        details={"name": dataset.name, "cases_count": tc_count}
    )

    return EvaluationDatasetResponse(
        id=dataset.id,
        organization_id=dataset.organization_id,
        name=dataset.name,
        description=dataset.description,
        dataset_type=dataset.dataset_type,
        version=dataset.version,
        is_active=dataset.is_active,
        test_cases_count=tc_count,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at
    )


@router.get("/datasets", response_model=List[EvaluationDatasetResponse])
def list_datasets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List evaluation datasets for the current organization."""
    datasets = db.query(EvaluationDataset).filter(
        EvaluationDataset.organization_id == current_user.organization_id,
        EvaluationDataset.is_active == True
    ).order_by(EvaluationDataset.created_at.desc()).all()

    result = []
    for d in datasets:
        tc_count = db.query(EvaluationTestCase).filter(
            EvaluationTestCase.dataset_id == d.id
        ).count()
        result.append(EvaluationDatasetResponse(
            id=d.id,
            organization_id=d.organization_id,
            name=d.name,
            description=d.description,
            dataset_type=d.dataset_type,
            version=d.version,
            is_active=d.is_active,
            test_cases_count=tc_count,
            created_at=d.created_at,
            updated_at=d.updated_at
        ))
    return result


@router.get("/datasets/{dataset_id}/test-cases", response_model=List[EvaluationTestCaseResponse])
def list_dataset_test_cases(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all ground-truth test cases in a dataset."""
    dataset = db.query(EvaluationDataset).filter(
        EvaluationDataset.id == dataset_id,
        EvaluationDataset.organization_id == current_user.organization_id
    ).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation dataset not found."
        )

    test_cases = db.query(EvaluationTestCase).filter(
        EvaluationTestCase.dataset_id == dataset.id,
        EvaluationTestCase.organization_id == current_user.organization_id
    ).order_by(EvaluationTestCase.test_code.asc()).all()

    return test_cases


@router.post("/runs", response_model=EvaluationRunResponse, status_code=status.HTTP_201_CREATED)
def trigger_evaluation_run(
    req: EvaluationRunTriggerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Execute a formal evaluation run on a dataset and persist versioned metrics.
    """
    dataset = db.query(EvaluationDataset).filter(
        EvaluationDataset.id == req.dataset_id,
        EvaluationDataset.organization_id == current_user.organization_id
    ).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation dataset not found."
        )

    eval_run = BenchmarkEvaluator.run_evaluation(
        db=db,
        organization_id=current_user.organization_id,
        dataset_id=dataset.id,
        triggered_by=current_user.id,
        engine_version=req.engine_version or "1.0.0-phase7",
        run_type=req.run_type or "BENCHMARK"
    )

    log_action(
        db=db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="EVALUATION_RUN_COMPLETED",
        target_entity="evaluation_runs",
        target_id=eval_run.id,
        details={
            "f1": eval_run.overall_f1,
            "precision": eval_run.overall_precision,
            "recall": eval_run.overall_recall,
            "total_cases": eval_run.total_cases
        }
    )

    return _build_eval_run_response(eval_run, dataset.name)


@router.get("/runs", response_model=List[EvaluationRunResponse])
def list_evaluation_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List historical evaluation runs for trend tracking."""
    runs = db.query(EvaluationRun).filter(
        EvaluationRun.organization_id == current_user.organization_id
    ).order_by(desc(EvaluationRun.created_at)).all()

    datasets = {d.id: d for d in db.query(EvaluationDataset).filter(
        EvaluationDataset.organization_id == current_user.organization_id
    ).all()}

    return [_build_eval_run_response(r, datasets.get(r.dataset_id).name if datasets.get(r.dataset_id) else None) for r in runs]


@router.get("/runs/{run_id}", response_model=EvaluationRunResponse)
def get_evaluation_run_detail(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed breakdown of an individual evaluation run."""
    eval_run = db.query(EvaluationRun).filter(
        EvaluationRun.id == run_id,
        EvaluationRun.organization_id == current_user.organization_id
    ).first()
    if not eval_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation run not found."
        )

    dataset = db.query(EvaluationDataset).filter(
        EvaluationDataset.id == eval_run.dataset_id
    ).first()

    return _build_eval_run_response(eval_run, dataset.name if dataset else None)


@router.get("/dashboard", response_model=QualityDashboardSummary)
def get_quality_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get aggregated quality, reliability and intelligence dashboard metrics.
    """
    org_id = current_user.organization_id

    # 1. Total datasets & benchmark cases
    total_datasets = db.query(EvaluationDataset).filter(EvaluationDataset.organization_id == org_id).count()
    total_cases = db.query(EvaluationTestCase).filter(EvaluationTestCase.organization_id == org_id).count()

    # 2. Latest run
    latest_run = db.query(EvaluationRun).filter(
        EvaluationRun.organization_id == org_id
    ).order_by(desc(EvaluationRun.created_at)).first()

    historical_runs_count = db.query(EvaluationRun).filter(
        EvaluationRun.organization_id == org_id
    ).count()

    latest_resp = None
    category_scores = {}
    if latest_run:
        dataset = db.query(EvaluationDataset).filter(EvaluationDataset.id == latest_run.dataset_id).first()
        latest_resp = _build_eval_run_response(latest_run, dataset.name if dataset else None)
        
        # Build category score matrix
        for cat, data in latest_run.category_metrics.items():
            category_scores[cat] = {
                "precision": data.get("precision", 0.0),
                "recall": data.get("recall", 0.0),
                "f1": data.get("f1", 0.0),
                "coverage": data.get("coverage", 0.0)
            }

    # 3. Disputed rules & recommendations
    disputed_rules_data = GuidelineIntelligenceEngine.analyze_rule_performance(db, org_id)
    recommendations_data = GuidelineIntelligenceEngine.generate_clarity_recommendations(db, org_id)

    top_disputed = [
        RulePerformanceStat(**r) for r in disputed_rules_data[:5]
    ]

    return QualityDashboardSummary(
        latest_run=latest_resp,
        total_datasets=total_datasets,
        total_benchmark_cases=total_cases,
        overall_precision=latest_run.overall_precision if latest_run else 0.0,
        overall_recall=latest_run.overall_recall if latest_run else 0.0,
        overall_f1=latest_run.overall_f1 if latest_run else 0.0,
        overall_accuracy=latest_run.overall_accuracy if latest_run else 0.0,
        overall_verification_rate=1.0,
        category_scores=category_scores,
        historical_runs_count=historical_runs_count,
        top_disputed_rules=top_disputed,
        recommendations_count=len(recommendations_data)
    )


@router.get("/intelligence/rules", response_model=List[RulePerformanceStat])
def get_rule_clarity_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Inspect rule dispute/dismissal friction and textual ambiguity scores."""
    return GuidelineIntelligenceEngine.analyze_rule_performance(db, current_user.organization_id)


@router.get("/intelligence/recommendations", response_model=List[RecommendationResponse])
def get_guideline_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get automated guideline clarity recommendations.
    Notice: Recommendations require human approval before changing the Constitution.
    """
    return GuidelineIntelligenceEngine.generate_clarity_recommendations(db, current_user.organization_id)


# --- Helper ---

def _build_eval_run_response(eval_run: EvaluationRun, dataset_name: Optional[str]) -> EvaluationRunResponse:
    return EvaluationRunResponse(
        id=eval_run.id,
        organization_id=eval_run.organization_id,
        dataset_id=eval_run.dataset_id,
        dataset_name=dataset_name,
        engine_version=eval_run.engine_version,
        run_type=eval_run.run_type,
        total_cases=eval_run.total_cases,
        overall_precision=eval_run.overall_precision,
        overall_recall=eval_run.overall_recall,
        overall_f1=eval_run.overall_f1,
        overall_accuracy=eval_run.overall_accuracy,
        category_metrics=eval_run.category_metrics,
        case_results=eval_run.case_results,
        triggered_by=eval_run.triggered_by,
        created_at=eval_run.created_at
    )
