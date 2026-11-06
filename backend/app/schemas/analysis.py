"""
app/schemas/analysis.py
Pydantic schemas for Brand Analysis Runs and Findings.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class AnalysisRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    document_id: str
    version_id: str
    status: str
    trigger_type: str
    total_findings: int = 0
    categories_analyzed: List[str] = []
    execution_metadata: Dict[str, Any] = {}
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    document_id: str
    version_id: str
    job_id: str
    category: str
    severity: str
    confidence: float
    flagged_snippet: str
    char_offset_start: Optional[int] = None
    char_offset_end: Optional[int] = None
    explanation: str
    evidence_type: str
    cited_code: str
    rule_id: Optional[str] = None
    fact_id: Optional[str] = None
    term_id: Optional[str] = None
    asset_id: Optional[str] = None
    source: str
    status: str
    segment_id: Optional[str] = None
    suggested_correction: Optional[str] = None
    created_at: datetime
    evidence_reference: Optional[Dict[str, Any]] = None


class FindingStatusUpdate(BaseModel):
    status: str
    justification: Optional[str] = None


class AnalysisStartRequest(BaseModel):
    version_id: Optional[str] = None


class DocumentAnalysisSummary(BaseModel):
    document_id: str
    latest_run: Optional[AnalysisRunOut] = None
    brand_health_score: Optional[float] = None
    findings_count_by_severity: Dict[str, int] = {}
    findings_count_by_category: Dict[str, int] = {}
    total_findings: int = 0

