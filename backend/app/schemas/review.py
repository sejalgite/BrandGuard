"""
app/schemas/review.py
Pydantic validation schemas for Human Review & Approval Governance (Phase 6).
"""
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from app.models.review import ReviewStatus, FindingDecisionType
from app.models.user import UserRole


class ReviewCreateRequest(BaseModel):
    document_id: uuid.UUID
    version_id: Optional[uuid.UUID] = None
    priority: Optional[str] = "NORMAL"
    due_date: Optional[datetime] = None
    assigned_reviewer_id: Optional[uuid.UUID] = None
    legal_review_required: Optional[bool] = False
    submission_notes: Optional[str] = None


class ReviewAssignRequest(BaseModel):
    assigned_reviewer_id: Optional[uuid.UUID] = None
    legal_reviewer_id: Optional[uuid.UUID] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = None


class ReviewTransitionRequest(BaseModel):
    action: str = Field(..., description="Workflow action: SUBMIT, START_REVIEW, REQUEST_CHANGES, RESUBMIT, FORWARD_FOR_APPROVAL, REQUEST_LEGAL, APPROVE_LEGAL, APPROVE, REJECT, WITHDRAW")
    notes: Optional[str] = Field(None, description="Explanation or comments; mandatory for changes requested and rejection")
    new_version_id: Optional[uuid.UUID] = Field(None, description="Required when resubmitting a revised version")


class FindingDecisionRequest(BaseModel):
    decision: FindingDecisionType
    reason: Optional[str] = Field(None, description="Justification reason; mandatory for DISMISSED and DISPUTED")
    suggested_correction: Optional[str] = None


class CommentCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    finding_id: Optional[uuid.UUID] = None
    parent_comment_id: Optional[uuid.UUID] = None


# --- Response Schemas ---

class ReviewHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    from_status: Optional[str] = None
    to_status: str
    action: str
    notes: Optional[str] = None
    created_at: datetime


class FindingDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    finding_id: uuid.UUID
    decided_by: uuid.UUID
    decider_name: Optional[str] = None
    decision: str
    reason: Optional[str] = None
    suggested_correction: Optional[str] = None
    created_at: datetime


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    review_id: Optional[uuid.UUID] = None
    finding_id: Optional[uuid.UUID] = None
    user_id: uuid.UUID
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    parent_comment_id: Optional[uuid.UUID] = None
    content: str
    created_at: datetime
    replies: List["CommentResponse"] = []


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    document_id: uuid.UUID
    document_title: Optional[str] = None
    version_id: uuid.UUID
    version_number: Optional[int] = None
    job_id: Optional[uuid.UUID] = None
    creator_id: uuid.UUID
    creator_name: Optional[str] = None
    assigned_reviewer_id: Optional[uuid.UUID] = None
    assigned_reviewer_name: Optional[str] = None
    legal_reviewer_id: Optional[uuid.UUID] = None
    legal_reviewer_name: Optional[str] = None
    status: str
    priority: str
    due_date: Optional[datetime] = None
    legal_review_required: bool
    legal_status: str
    final_decision_by: Optional[uuid.UUID] = None
    final_decision_at: Optional[datetime] = None
    decision_notes: Optional[str] = None
    brand_health_score: Optional[float] = None
    total_findings: Optional[int] = 0
    created_at: datetime
    updated_at: datetime

    history: List[ReviewHistoryItem] = []
    finding_decisions: List[FindingDecisionResponse] = []


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    message: str
    notification_type: str
    resource_type: Optional[str] = None
    resource_id: Optional[uuid.UUID] = None
    is_read: bool
    created_at: datetime

