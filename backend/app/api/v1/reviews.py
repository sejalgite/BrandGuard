"""
app/api/v1/reviews.py
Human Review, Approval, Collaboration, and Governance Workflow API Endpoints (Phase 6).
Handles review lifecycle management, state machine transitions, finding decisions,
threaded comments, version comparison, and immutable audit logging.
"""
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.auth.rbac import (
    require_permission, PERM_UPLOAD_DOCS, PERM_APPROVE_DOCS, PERM_APPROVE_FINDINGS,
    PERM_APPROVE_LEGAL, PERM_ASSIGN_REVIEWERS, PERM_VIEW_ANALYTICS
)
from app.models.user import User, UserRole
from app.models.document import Document, DocumentVersion, VersionWorkflowStatus
from app.models.finding import Finding, ReviewJob, FindingStatus
from app.models.workflow import Comment, ReviewAssignment
from app.models.review import (
    Review, ReviewStatus, ReviewHistory, FindingDecision, FindingDecisionType
)
from app.schemas.review import (
    ReviewCreateRequest, ReviewAssignRequest, ReviewTransitionRequest,
    ReviewResponse, ReviewHistoryItem, FindingDecisionRequest, FindingDecisionResponse,
    CommentCreateRequest, CommentResponse
)
from app.services.workflow.state_machine import WorkflowStateMachine
from app.services.workflow.notification_service import NotificationService
from app.services.workflow.version_diff import VersionDiffEngine
from app.audit.audit_logger import log_action

router = APIRouter()


@router.post("", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def create_or_submit_review(
    req: ReviewCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a review for a document version and submit it into the workflow queue.
    Enforces tenant isolation and validates document/version ownership.
    """
    # 1. Tenant-isolated Document Verification
    doc = db.query(Document).filter(
        Document.id == req.document_id,
        Document.organization_id == current_user.organization_id
    ).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {req.document_id} not found in this organization."
        )

    # 2. Version Verification
    if req.version_id:
        version = db.query(DocumentVersion).filter(
            DocumentVersion.id == req.version_id,
            DocumentVersion.document_id == doc.id,
            DocumentVersion.organization_id == current_user.organization_id
        ).first()
    else:
        # Latest version
        version = db.query(DocumentVersion).filter(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.organization_id == current_user.organization_id
        ).order_by(desc(DocumentVersion.version_number)).first()

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document version not found."
        )

    # 3. Lookup latest analysis run for this version if available
    latest_job = db.query(ReviewJob).filter(
        ReviewJob.version_id == version.id,
        ReviewJob.organization_id == current_user.organization_id
    ).order_by(desc(ReviewJob.started_at)).first()

    # 4. Create Review entity
    review = Review(
        organization_id=current_user.organization_id,
        document_id=doc.id,
        version_id=version.id,
        job_id=latest_job.id if latest_job else None,
        creator_id=current_user.id,
        assigned_reviewer_id=req.assigned_reviewer_id,
        status=ReviewStatus.SUBMITTED,
        priority=req.priority or "NORMAL",
        due_date=req.due_date,
        legal_review_required=bool(req.legal_review_required),
        legal_status="PENDING" if req.legal_review_required else "NOT_REQUIRED",
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    # Update document version status
    version.version_status = VersionWorkflowStatus.REVIEW_PENDING
    db.commit()

    # 5. Record initial history
    history = ReviewHistory(
        organization_id=current_user.organization_id,
        review_id=review.id,
        actor_id=current_user.id,
        from_status=None,
        to_status=ReviewStatus.SUBMITTED.value,
        action="SUBMIT",
        notes=req.submission_notes or "Initial submission for review"
    )
    db.add(history)
    db.commit()

    # 6. Audit Log
    log_action(
        db=db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="REVIEW_SUBMITTED",
        target_entity="reviews",
        target_id=review.id,
        details={
            "document_id": str(doc.id),
            "version_id": str(version.id),
            "priority": review.priority,
            "assigned_reviewer_id": str(req.assigned_reviewer_id) if req.assigned_reviewer_id else None
        }
    )

    # 7. Notify Assigned Reviewer if specified
    if req.assigned_reviewer_id:
        NotificationService.send_notification(
            db=db,
            organization_id=current_user.organization_id,
            recipient_id=req.assigned_reviewer_id,
            actor_id=current_user.id,
            title="New Review Assigned",
            message=f"You have been assigned to review '{doc.title}' (Version {version.version_number}).",
            notification_type="REVIEW_ASSIGNED",
            resource_type="review",
            resource_id=review.id
        )

    return _build_review_response(db, review)


@router.get("", response_model=List[ReviewResponse])
def list_reviews(
    status_filter: Optional[str] = Query(None, alias="status"),
    assigned_to_me: Optional[bool] = False,
    document_id: Optional[uuid.UUID] = None,
    priority: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List review queue items scoped to current organization.
    Supports filtering by review status, assignment, document, and priority.
    """
    q = db.query(Review).filter(Review.organization_id == current_user.organization_id)

    if assigned_to_me:
        q = q.filter(Review.assigned_reviewer_id == current_user.id)
    if document_id:
        q = q.filter(Review.document_id == document_id)
    if priority:
        q = q.filter(Review.priority == priority.upper())
    if status_filter and status_filter.upper() != "ALL":
        q = q.filter(Review.status == status_filter.upper())

    reviews = q.order_by(desc(Review.created_at)).offset(offset).limit(limit).all()
    return [_build_review_response(db, r) for r in reviews]


@router.get("/queue/stats")
def get_queue_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get aggregated review queue metrics for the dashboard."""
    org_id = current_user.organization_id
    all_reviews = db.query(Review).filter(Review.organization_id == org_id).all()

    total = len(all_reviews)
    submitted = sum(1 for r in all_reviews if r.status == ReviewStatus.SUBMITTED)
    in_review = sum(1 for r in all_reviews if r.status == ReviewStatus.UNDER_REVIEW)
    changes_requested = sum(1 for r in all_reviews if r.status == ReviewStatus.CHANGES_REQUESTED)
    resubmitted = sum(1 for r in all_reviews if r.status == ReviewStatus.RESUBMITTED)
    pending_brand = sum(1 for r in all_reviews if r.status == ReviewStatus.PENDING_BRAND_APPROVAL)
    pending_legal = sum(1 for r in all_reviews if r.status == ReviewStatus.PENDING_LEGAL_APPROVAL)
    approved = sum(1 for r in all_reviews if r.status == ReviewStatus.APPROVED)
    rejected = sum(1 for r in all_reviews if r.status == ReviewStatus.REJECTED)

    assigned_to_user = sum(1 for r in all_reviews if r.assigned_reviewer_id == current_user.id and r.status in [ReviewStatus.SUBMITTED, ReviewStatus.UNDER_REVIEW, ReviewStatus.RESUBMITTED, ReviewStatus.PENDING_BRAND_APPROVAL])

    return {
        "total": total,
        "submitted": submitted,
        "in_review": in_review,
        "changes_requested": changes_requested,
        "resubmitted": resubmitted,
        "pending_brand": pending_brand,
        "pending_legal": pending_legal,
        "approved": approved,
        "rejected": rejected,
        "assigned_to_current_user": assigned_to_user
    }


@router.get("/{review_id}", response_model=ReviewResponse)
def get_review_detail(
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full details of a specific review, including history and finding decisions."""
    review = db.query(Review).filter(
        Review.id == review_id,
        Review.organization_id == current_user.organization_id
    ).first()
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found."
        )

    return _build_review_response(db, review)


@router.post("/{review_id}/transition", response_model=ReviewResponse)
def execute_review_transition(
    review_id: uuid.UUID,
    req: ReviewTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Execute an authorized workflow transition via the centralized state machine.
    """
    review = db.query(Review).filter(
        Review.id == review_id,
        Review.organization_id == current_user.organization_id
    ).first()
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found."
        )

    updated_review = WorkflowStateMachine.transition(
        db=db,
        review=review,
        action=req.action,
        actor=current_user,
        notes=req.notes,
        new_version_id=str(req.new_version_id) if req.new_version_id else None
    )

    # Dispatch appropriate notification
    action_upper = req.action.upper().strip()
    doc = db.query(Document).filter(Document.id == review.document_id).first()
    doc_title = doc.title if doc else "Document"

    if action_upper == "REQUEST_CHANGES":
        NotificationService.send_notification(
            db=db,
            organization_id=current_user.organization_id,
            recipient_id=review.creator_id,
            actor_id=current_user.id,
            title="Changes Requested",
            message=f"Changes requested on '{doc_title}'. Reviewer notes: {req.notes}",
            notification_type="CHANGES_REQUESTED",
            resource_type="review",
            resource_id=review.id
        )
    elif action_upper == "APPROVE":
        NotificationService.send_notification(
            db=db,
            organization_id=current_user.organization_id,
            recipient_id=review.creator_id,
            actor_id=current_user.id,
            title="Content Approved!",
            message=f"'{doc_title}' has received final brand approval.",
            notification_type="APPROVAL_GRANTED",
            resource_type="review",
            resource_id=review.id
        )
    elif action_upper == "REJECT":
        NotificationService.send_notification(
            db=db,
            organization_id=current_user.organization_id,
            recipient_id=review.creator_id,
            actor_id=current_user.id,
            title="Content Rejected",
            message=f"'{doc_title}' has been rejected. Reason: {req.notes}",
            notification_type="REVIEW_REJECTED",
            resource_type="review",
            resource_id=review.id
        )
    elif action_upper == "RESUBMIT" and review.assigned_reviewer_id:
        NotificationService.send_notification(
            db=db,
            organization_id=current_user.organization_id,
            recipient_id=review.assigned_reviewer_id,
            actor_id=current_user.id,
            title="Document Resubmitted",
            message=f"Revised version of '{doc_title}' resubmitted for review.",
            notification_type="DOCUMENT_RESUBMITTED",
            resource_type="review",
            resource_id=review.id
        )

    return _build_review_response(db, updated_review)


@router.patch("/{review_id}/assign", response_model=ReviewResponse)
def assign_reviewers(
    review_id: uuid.UUID,
    req: ReviewAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Assign or reassign reviewers (requires assign_reviewers permission or admin).
    """
    review = db.query(Review).filter(
        Review.id == review_id,
        Review.organization_id == current_user.organization_id
    ).first()
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found."
        )

    # Permission check: Brand Manager, Reviewer, or Admin
    if current_user.role not in [UserRole.BRAND_MANAGER, UserRole.ADMIN, UserRole.REVIEWER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only Brand Managers, Reviewers, and Admins can assign reviewers."
        )

    old_reviewer_id = review.assigned_reviewer_id
    if req.assigned_reviewer_id:
        # Verify user belongs to same organization
        target_user = db.query(User).filter(
            User.id == req.assigned_reviewer_id,
            User.organization_id == current_user.organization_id,
            User.is_active == True
        ).first()
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assigned user not found in organization."
            )
        review.assigned_reviewer_id = target_user.id

    if req.legal_reviewer_id:
        legal_user = db.query(User).filter(
            User.id == req.legal_reviewer_id,
            User.organization_id == current_user.organization_id,
            User.is_active == True
        ).first()
        if not legal_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assigned legal user not found in organization."
            )
        review.legal_reviewer_id = legal_user.id
        review.legal_review_required = True

    if req.due_date:
        review.due_date = req.due_date

    # Record history
    history = ReviewHistory(
        organization_id=current_user.organization_id,
        review_id=review.id,
        actor_id=current_user.id,
        from_status=review.status.value,
        to_status=review.status.value,
        action="REASSIGN" if old_reviewer_id else "ASSIGN",
        notes=req.notes or f"Review assigned to user {req.assigned_reviewer_id}"
    )
    db.add(history)

    # Audit log
    log_action(
        db=db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="REVIEW_ASSIGNED",
        target_entity="reviews",
        target_id=review.id,
        details={
            "assigned_reviewer_id": str(review.assigned_reviewer_id) if review.assigned_reviewer_id else None,
            "legal_reviewer_id": str(review.legal_reviewer_id) if review.legal_reviewer_id else None,
            "notes": req.notes
        }
    )

    db.commit()
    db.refresh(review)

    # Dispatch notification to newly assigned reviewer
    if req.assigned_reviewer_id:
        doc = db.query(Document).filter(Document.id == review.document_id).first()
        NotificationService.send_notification(
            db=db,
            organization_id=current_user.organization_id,
            recipient_id=review.assigned_reviewer_id,
            actor_id=current_user.id,
            title="Review Assigned",
            message=f"You have been assigned to review '{doc.title if doc else 'Document'}'.",
            notification_type="REVIEW_ASSIGNED",
            resource_type="review",
            resource_id=review.id
        )

    return _build_review_response(db, review)


@router.post("/{review_id}/findings/{finding_id}/decision", response_model=FindingDecisionResponse)
def record_finding_decision(
    review_id: uuid.UUID,
    finding_id: uuid.UUID,
    req: FindingDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record an explicit human review decision on an individual compliance finding.
    Supports ACCEPT, DISMISS, DISPUTE, RESOLVE, and CORRECTION_REQUESTED.
    """
    review = db.query(Review).filter(
        Review.id == review_id,
        Review.organization_id == current_user.organization_id
    ).first()
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found."
        )

    finding = db.query(Finding).filter(
        Finding.id == finding_id,
        Finding.organization_id == current_user.organization_id
    ).first()
    if not finding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding {finding_id} not found."
        )

    # Mandatory reason for DISMISS and DISPUTE
    if req.decision in [FindingDecisionType.DISMISSED, FindingDecisionType.DISPUTED]:
        if not req.reason or not req.reason.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Finding decision '{req.decision.value}' requires a mandatory reason."
            )

    # Update finding status
    status_map = {
        FindingDecisionType.ACCEPTED: FindingStatus.ACCEPTED,
        FindingDecisionType.DISMISSED: FindingStatus.DISMISSED,
        FindingDecisionType.DISPUTED: FindingStatus.DISPUTED,
        FindingDecisionType.RESOLVED: FindingStatus.ACCEPTED,
        FindingDecisionType.CORRECTION_REQUESTED: FindingStatus.NEEDS_REVIEW,
    }
    finding.status = status_map.get(req.decision, FindingStatus.OPEN)

    # Record decision
    decision_record = FindingDecision(
        organization_id=current_user.organization_id,
        review_id=review.id,
        finding_id=finding.id,
        decided_by=current_user.id,
        decision=req.decision,
        reason=req.reason,
        suggested_correction=req.suggested_correction
    )
    db.add(decision_record)

    # Audit log
    log_action(
        db=db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action=f"FINDING_{req.decision.value}",
        target_entity="findings",
        target_id=finding.id,
        details={
            "review_id": str(review.id),
            "decision": req.decision.value,
            "reason": req.reason,
            "flagged_snippet": finding.flagged_snippet[:100]
        }
    )

    db.commit()
    db.refresh(decision_record)

    return FindingDecisionResponse(
        id=decision_record.id,
        finding_id=decision_record.finding_id,
        decided_by=decision_record.decided_by,
        decider_name=current_user.full_name,
        decision=decision_record.decision.value,
        reason=decision_record.reason,
        suggested_correction=decision_record.suggested_correction,
        created_at=decision_record.created_at
    )


@router.get("/{review_id}/comments", response_model=List[CommentResponse])
def list_review_comments(
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch threaded comments for a review, preserving hierarchy."""
    review = db.query(Review).filter(
        Review.id == review_id,
        Review.organization_id == current_user.organization_id
    ).first()
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found."
        )

    # Query comments by review_id OR by (document_id, version_id)
    comments = db.query(Comment).filter(
        Comment.organization_id == current_user.organization_id,
        Comment.version_id == review.version_id
    ).order_by(Comment.created_at.asc()).all()

    # Build threaded response
    comment_map: Dict[uuid.UUID, CommentResponse] = {}
    top_level: List[CommentResponse] = []

    user_ids = {c.user_id for c in comments}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}

    for c in comments:
        u = users.get(c.user_id)
        c_resp = CommentResponse(
            id=c.id,
            organization_id=c.organization_id,
            document_id=c.document_id,
            version_id=c.version_id,
            review_id=c.review_id or review.id,
            finding_id=c.finding_id,
            user_id=c.user_id,
            user_name=u.full_name if u else "Unknown",
            user_role=u.role.value if u else None,
            parent_comment_id=c.parent_comment_id,
            content=c.content,
            created_at=c.created_at,
            replies=[]
        )
        comment_map[c.id] = c_resp

    for c in comments:
        c_resp = comment_map[c.id]
        if c.parent_comment_id and c.parent_comment_id in comment_map:
            comment_map[c.parent_comment_id].replies.append(c_resp)
        else:
            top_level.append(c_resp)

    return top_level


@router.post("/{review_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
def create_review_comment(
    review_id: uuid.UUID,
    req: CommentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a review comment or threaded reply."""
    review = db.query(Review).filter(
        Review.id == review_id,
        Review.organization_id == current_user.organization_id
    ).first()
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review {review_id} not found."
        )

    # If replying to a parent comment, verify it belongs to this review
    if req.parent_comment_id:
        parent = db.query(Comment).filter(
            Comment.id == req.parent_comment_id,
            Comment.organization_id == current_user.organization_id,
            Comment.version_id == review.version_id
        ).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent comment not found in this review thread."
            )

    comment_id = uuid.uuid4()
    comment = Comment(
        id=comment_id,
        organization_id=current_user.organization_id,
        document_id=review.document_id,
        version_id=review.version_id,
        review_id=review.id,
        finding_id=req.finding_id,
        user_id=current_user.id,
        parent_comment_id=req.parent_comment_id,
        content=req.content.strip()
    )
    db.add(comment)

    # Audit log — use pre-assigned comment_id so target_id is never null
    log_action(
        db=db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="COMMENT_ADDED",
        target_entity="comments",
        target_id=comment_id,
        details={
            "review_id": str(review.id),
            "finding_id": str(req.finding_id) if req.finding_id else None,
            "parent_comment_id": str(req.parent_comment_id) if req.parent_comment_id else None
        }
    )

    db.commit()
    db.refresh(comment)

    # Notify creator or reviewer about new comment
    recipient = review.creator_id if current_user.id != review.creator_id else review.assigned_reviewer_id
    if recipient:
        doc = db.query(Document).filter(Document.id == review.document_id).first()
        NotificationService.send_notification(
            db=db,
            organization_id=current_user.organization_id,
            recipient_id=recipient,
            actor_id=current_user.id,
            title="New Review Comment",
            message=f"{current_user.full_name} commented on '{doc.title if doc else 'Document'}'.",
            notification_type="COMMENT_RECEIVED",
            resource_type="review",
            resource_id=review.id
        )

    return CommentResponse(
        id=comment.id,
        organization_id=comment.organization_id,
        document_id=comment.document_id,
        version_id=comment.version_id,
        review_id=comment.review_id,
        finding_id=comment.finding_id,
        user_id=comment.user_id,
        user_name=current_user.full_name,
        user_role=current_user.role.value,
        parent_comment_id=comment.parent_comment_id,
        content=comment.content,
        created_at=comment.created_at,
        replies=[]
    )


@router.get("/documents/{document_id}/compare")
def compare_document_versions(
    document_id: uuid.UUID,
    v1: uuid.UUID = Query(..., description="Base version ID"),
    v2: uuid.UUID = Query(..., description="Revised version ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compare text and compliance findings between two document versions.
    Identifies additions, deletions, score delta, and new/resolved findings.
    """
    ver_1 = db.query(DocumentVersion).filter(
        DocumentVersion.id == v1,
        DocumentVersion.document_id == document_id,
        DocumentVersion.organization_id == current_user.organization_id
    ).first()
    ver_2 = db.query(DocumentVersion).filter(
        DocumentVersion.id == v2,
        DocumentVersion.document_id == document_id,
        DocumentVersion.organization_id == current_user.organization_id
    ).first()

    if not ver_1 or not ver_2:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both document versions not found in organization."
        )

    return VersionDiffEngine.compare_versions(db=db, version_1=ver_1, version_2=ver_2)


# --- Helper ---

def _build_review_response(db: Session, review: Review) -> ReviewResponse:
    """Helper to assemble a complete ReviewResponse with relationships."""
    doc = db.query(Document).filter(Document.id == review.document_id).first()
    version = db.query(DocumentVersion).filter(DocumentVersion.id == review.version_id).first()
    creator = db.query(User).filter(User.id == review.creator_id).first()
    reviewer = db.query(User).filter(User.id == review.assigned_reviewer_id).first() if review.assigned_reviewer_id else None
    legal = db.query(User).filter(User.id == review.legal_reviewer_id).first() if review.legal_reviewer_id else None

    # History
    history_items = db.query(ReviewHistory).filter(ReviewHistory.review_id == review.id).order_by(ReviewHistory.created_at.asc()).all()
    history_actors = {u.id: u for u in db.query(User).filter(User.id.in_([h.actor_id for h in history_items])).all()}

    history_resp = [
        ReviewHistoryItem(
            id=h.id,
            actor_id=h.actor_id,
            actor_name=history_actors.get(h.actor_id).full_name if history_actors.get(h.actor_id) else None,
            actor_role=history_actors.get(h.actor_id).role.value if history_actors.get(h.actor_id) else None,
            from_status=h.from_status,
            to_status=h.to_status,
            action=h.action,
            notes=h.notes,
            created_at=h.created_at
        )
        for h in history_items
    ]

    # Decisions
    decisions = db.query(FindingDecision).filter(FindingDecision.review_id == review.id).all()
    deciders = {u.id: u for u in db.query(User).filter(User.id.in_([d.decided_by for d in decisions])).all()}

    decisions_resp = [
        FindingDecisionResponse(
            id=d.id,
            finding_id=d.finding_id,
            decided_by=d.decided_by,
            decider_name=deciders.get(d.decided_by).full_name if deciders.get(d.decided_by) else None,
            decision=d.decision.value,
            reason=d.reason,
            suggested_correction=d.suggested_correction,
            created_at=d.created_at
        )
        for d in decisions
    ]

    total_findings = db.query(Finding).filter(
        Finding.version_id == review.version_id,
        Finding.organization_id == review.organization_id
    ).count()

    return ReviewResponse(
        id=review.id,
        organization_id=review.organization_id,
        document_id=review.document_id,
        document_title=doc.title if doc else None,
        version_id=review.version_id,
        version_number=version.version_number if version else None,
        job_id=review.job_id,
        creator_id=review.creator_id,
        creator_name=creator.full_name if creator else None,
        assigned_reviewer_id=review.assigned_reviewer_id,
        assigned_reviewer_name=reviewer.full_name if reviewer else None,
        legal_reviewer_id=review.legal_reviewer_id,
        legal_reviewer_name=legal.full_name if legal else None,
        status=review.status.value,
        priority=review.priority,
        due_date=review.due_date,
        legal_review_required=review.legal_review_required,
        legal_status=review.legal_status,
        final_decision_by=review.final_decision_by,
        final_decision_at=review.final_decision_at,
        decision_notes=review.decision_notes,
        brand_health_score=float(version.brand_health_score) if version and version.brand_health_score is not None else None,
        total_findings=total_findings,
        created_at=review.created_at,
        updated_at=review.updated_at,
        history=history_resp,
        finding_decisions=decisions_resp
    )

