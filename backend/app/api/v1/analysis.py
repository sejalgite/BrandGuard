"""
app/api/v1/analysis.py
Brand Analysis Engine API Endpoints.
Provides analysis execution, run monitoring, finding inspection, and status management.
Strictly enforces tenant isolation, RBAC permissions, and comprehensive audit logging.
"""
import uuid
import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.user import User
from app.models.document import Document, DocumentVersion
from app.models.finding import ReviewJob, Finding, FindingStatus, SeverityLevel, DetectionCategory
from app.models.constitution import BrandRule, FactRegistry, TermBank, BrandAsset
from app.schemas.analysis import (
    AnalysisRunOut, FindingOut, FindingStatusUpdate, AnalysisStartRequest, DocumentAnalysisSummary
)
from app.auth.dependencies import get_current_active_user
from app.auth.rbac import (
    require_permission, PERM_RUN_ANALYSIS, PERM_APPROVE_FINDINGS, PERM_READ_OWN_DOCS
)
from app.audit.audit_logger import log_action
from app.services.analysis.engine import BrandAnalysisEngine

logger = logging.getLogger(__name__)

router = APIRouter()


def _format_job_out(job: ReviewJob) -> AnalysisRunOut:
    return AnalysisRunOut(
        id=str(job.id),
        organization_id=str(job.organization_id),
        document_id=str(job.document_id),
        version_id=str(job.version_id),
        status=job.status,
        trigger_type=job.trigger_type,
        total_findings=job.total_findings,
        categories_analyzed=job.categories_analyzed or [],
        execution_metadata=job.execution_metadata or {},
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message
    )


def _enrich_finding_out(finding: Finding, db: Session) -> FindingOut:
    """Enrich finding with referenced Constitution metadata."""
    ref_data: Dict[str, Any] = {}
    if finding.rule_id:
        rule = db.query(BrandRule).filter(BrandRule.id == finding.rule_id).first()
        if rule:
            ref_data = {"type": "RULE", "title": rule.title, "rule_code": rule.rule_code, "category": rule.category.value}
    elif finding.fact_id:
        fact = db.query(FactRegistry).filter(FactRegistry.id == finding.fact_id).first()
        if fact:
            ref_data = {"type": "FACT", "statement": fact.statement, "fact_code": fact.fact_code, "source": fact.source_reference, "expiry": fact.expiry_date.isoformat()}
    elif finding.term_id:
        term = db.query(TermBank).filter(TermBank.id == finding.term_id).first()
        if term:
            ref_data = {"type": "TERM", "prohibited": term.prohibited_term, "preferred": term.preferred_term, "context": term.usage_context}
    elif finding.asset_id:
        asset = db.query(BrandAsset).filter(BrandAsset.id == finding.asset_id).first()
        if asset:
            ref_data = {"type": "ASSET", "name": asset.name, "asset_code": asset.asset_code, "specs": asset.specifications}

    return FindingOut(
        id=str(finding.id),
        organization_id=str(finding.organization_id),
        document_id=str(finding.document_id),
        version_id=str(finding.version_id),
        job_id=str(finding.job_id),
        category=finding.category.value,
        severity=finding.severity.value,
        confidence=float(finding.confidence),
        flagged_snippet=finding.flagged_snippet,
        char_offset_start=finding.char_offset_start,
        char_offset_end=finding.char_offset_end,
        explanation=finding.explanation,
        evidence_type=finding.evidence_type.value,
        cited_code=finding.cited_code,
        rule_id=str(finding.rule_id) if finding.rule_id else None,
        fact_id=str(finding.fact_id) if finding.fact_id else None,
        term_id=str(finding.term_id) if finding.term_id else None,
        asset_id=str(finding.asset_id) if finding.asset_id else None,
        source=finding.source.value,
        status=finding.status.value,
        segment_id=finding.segment_id,
        suggested_correction=finding.suggested_correction,
        created_at=finding.created_at,
        evidence_reference=ref_data
    )


# ---------------------------------------------------------------------------
# 1. Trigger Analysis Execution
# ---------------------------------------------------------------------------

@router.post("/documents/{document_id}/run", response_model=AnalysisRunOut, status_code=status.HTTP_201_CREATED)
def start_document_analysis(
    document_id: str,
    payload: Optional[AnalysisStartRequest] = Body(default=None),
    current_user: User = Depends(require_permission(PERM_RUN_ANALYSIS)),
    db: Session = Depends(get_db)
):
    """
    Initiate or re-run brand compliance analysis on a document.
    Enforces multi-tenant isolation and records an audit log entry.
    """
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.organization_id == current_user.organization_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    target_ver_id = payload.version_id if (payload and payload.version_id) else None
    if not target_ver_id:
        latest = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == doc.id, DocumentVersion.organization_id == current_user.organization_id)
            .order_by(desc(DocumentVersion.version_number))
            .first()
        )
        if not latest:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document has no uploaded versions.")
        target_ver_id = str(latest.id)

    engine = BrandAnalysisEngine(db=db)
    try:
        job = engine.run_analysis(
            document_id=str(doc.id),
            version_id=target_ver_id,
            organization_id=str(current_user.organization_id),
            actor_id=str(current_user.id),
            trigger_type="MANUAL"
        )
        return _format_job_out(job)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


# ---------------------------------------------------------------------------
# 2. List Analysis Runs for Document
# ---------------------------------------------------------------------------

@router.get("/documents/{document_id}/runs", response_model=List[AnalysisRunOut])
def list_document_analysis_runs(
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all compliance review jobs executed on a document."""
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.organization_id == current_user.organization_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    jobs = (
        db.query(ReviewJob)
        .filter(ReviewJob.document_id == doc.id, ReviewJob.organization_id == current_user.organization_id)
        .order_by(desc(ReviewJob.started_at))
        .all()
    )
    return [_format_job_out(j) for j in jobs]


# ---------------------------------------------------------------------------
# 3. Retrieve Analysis Run Status
# ---------------------------------------------------------------------------

@router.get("/runs/{job_id}", response_model=AnalysisRunOut)
def get_analysis_run(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retrieve execution metrics and status for a specific analysis run."""
    job = (
        db.query(ReviewJob)
        .filter(ReviewJob.id == job_id, ReviewJob.organization_id == current_user.organization_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found.")

    return _format_job_out(job)


# ---------------------------------------------------------------------------
# 4. Retrieve Findings for an Analysis Run (with Category/Severity/Status Filters)
# ---------------------------------------------------------------------------

@router.get("/runs/{job_id}/findings", response_model=List[FindingOut])
def get_run_findings(
    job_id: str,
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retrieve findings associated with an analysis run, with multi-facet filtering."""
    job = (
        db.query(ReviewJob)
        .filter(ReviewJob.id == job_id, ReviewJob.organization_id == current_user.organization_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found.")

    query = db.query(Finding).filter(
        Finding.job_id == job.id,
        Finding.organization_id == current_user.organization_id
    )

    if category:
        try:
            cat_enum = DetectionCategory(category.upper())
            query = query.filter(Finding.category == cat_enum)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid category '{category}'.")

    if severity:
        try:
            sev_enum = SeverityLevel(severity.upper())
            query = query.filter(Finding.severity == sev_enum)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid severity '{severity}'.")

    if status_filter:
        try:
            stat_enum = FindingStatus(status_filter.upper())
            query = query.filter(Finding.status == stat_enum)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status '{status_filter}'.")

    findings = query.order_by(desc(Finding.created_at)).all()
    return [_enrich_finding_out(f, db) for f in findings]


# ---------------------------------------------------------------------------
# 5. Retrieve Single Finding with Full Evidence
# ---------------------------------------------------------------------------

@router.get("/findings/{finding_id}", response_model=FindingOut)
def get_single_finding(
    finding_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retrieve full trace evidence and reference details for a finding."""
    finding = (
        db.query(Finding)
        .filter(Finding.id == finding_id, Finding.organization_id == current_user.organization_id)
        .first()
    )
    if not finding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found.")

    return _enrich_finding_out(finding, db)


# ---------------------------------------------------------------------------
# 6. Update Finding Review Status (Accept / Dispute / Dismiss)
# ---------------------------------------------------------------------------

@router.patch("/findings/{finding_id}/status", response_model=FindingOut)
def update_finding_status(
    finding_id: str,
    payload: FindingStatusUpdate,
    current_user: User = Depends(require_permission(PERM_APPROVE_FINDINGS)),
    db: Session = Depends(get_db)
):
    """Update finding resolution status (ACCEPTED, DISMISSED, DISPUTED, EDITED, NEEDS_REVIEW)."""
    finding = (
        db.query(Finding)
        .filter(Finding.id == finding_id, Finding.organization_id == current_user.organization_id)
        .first()
    )
    if not finding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found.")

    try:
        new_status = FindingStatus(payload.status.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid finding status '{payload.status}'. Valid: {[s.value for s in FindingStatus]}"
        )

    old_status = finding.status
    finding.status = new_status

    log_action(
        db=db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="FINDING_STATUS_UPDATED",
        target_entity="findings",
        target_id=finding.id,
        details={
            "old_status": old_status.value,
            "new_status": new_status.value,
            "justification": payload.justification
        }
    )

    db.commit()
    db.refresh(finding)
    return _enrich_finding_out(finding, db)


# ---------------------------------------------------------------------------
# 7. Document Compliance & Health Summary
# ---------------------------------------------------------------------------

@router.get("/documents/{document_id}/summary", response_model=DocumentAnalysisSummary)
def get_document_analysis_summary(
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Provide overall compliance health, severity breakdown, and category counts."""
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.organization_id == current_user.organization_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    latest_job = (
        db.query(ReviewJob)
        .filter(ReviewJob.document_id == doc.id, ReviewJob.organization_id == current_user.organization_id)
        .order_by(desc(ReviewJob.started_at))
        .first()
    )

    latest_version = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == doc.id, DocumentVersion.organization_id == current_user.organization_id)
        .order_by(desc(DocumentVersion.version_number))
        .first()
    )

    sev_counts = {s.value: 0 for s in SeverityLevel}
    cat_counts = {c.value: 0 for c in DetectionCategory}
    total_findings = 0

    if latest_job:
        findings = (
            db.query(Finding)
            .filter(Finding.job_id == latest_job.id, Finding.organization_id == current_user.organization_id)
            .all()
        )
        total_findings = len(findings)
        for f in findings:
            sev_counts[f.severity.value] = sev_counts.get(f.severity.value, 0) + 1
            cat_counts[f.category.value] = cat_counts.get(f.category.value, 0) + 1

    return DocumentAnalysisSummary(
        document_id=str(doc.id),
        latest_run=_format_job_out(latest_job) if latest_job else None,
        brand_health_score=float(latest_version.brand_health_score) if (latest_version and latest_version.brand_health_score is not None) else None,
        findings_count_by_severity=sev_counts,
        findings_count_by_category=cat_counts,
        total_findings=total_findings
    )

