"""
app/services/workflow/state_machine.py
Centralized Workflow State Machine for Human Review & Approval Governance (Phase 6).
Enforces valid state transitions, RBAC permissions, self-approval prevention,
and immutable document version locking upon final approval.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.review import Review, ReviewStatus, ReviewHistory
from app.models.document import Document, DocumentVersion, DocumentLifecycleStatus, VersionWorkflowStatus
from app.models.user import User, UserRole
from app.models.notification import Notification
from app.audit.audit_logger import log_action

# Valid transitions matrix: (from_status, action) -> to_status
# Only transitions explicitly listed here are mathematically valid
VALID_TRANSITIONS: Dict[Tuple[ReviewStatus, str], ReviewStatus] = {
    # From DRAFT
    (ReviewStatus.DRAFT, "SUBMIT"): ReviewStatus.SUBMITTED,
    (ReviewStatus.DRAFT, "WITHDRAW"): ReviewStatus.WITHDRAWN,

    # From SUBMITTED
    (ReviewStatus.SUBMITTED, "START_REVIEW"): ReviewStatus.UNDER_REVIEW,
    (ReviewStatus.SUBMITTED, "WITHDRAW"): ReviewStatus.WITHDRAWN,
    (ReviewStatus.SUBMITTED, "REJECT"): ReviewStatus.REJECTED,

    # From UNDER_REVIEW
    (ReviewStatus.UNDER_REVIEW, "REQUEST_CHANGES"): ReviewStatus.CHANGES_REQUESTED,
    (ReviewStatus.UNDER_REVIEW, "FORWARD_FOR_APPROVAL"): ReviewStatus.PENDING_BRAND_APPROVAL,
    (ReviewStatus.UNDER_REVIEW, "REQUEST_LEGAL"): ReviewStatus.PENDING_LEGAL_APPROVAL,
    (ReviewStatus.UNDER_REVIEW, "APPROVE"): ReviewStatus.APPROVED,
    (ReviewStatus.UNDER_REVIEW, "REJECT"): ReviewStatus.REJECTED,

    # From CHANGES_REQUESTED
    (ReviewStatus.CHANGES_REQUESTED, "RESUBMIT"): ReviewStatus.RESUBMITTED,
    (ReviewStatus.CHANGES_REQUESTED, "WITHDRAW"): ReviewStatus.WITHDRAWN,

    # From RESUBMITTED
    (ReviewStatus.RESUBMITTED, "START_REVIEW"): ReviewStatus.UNDER_REVIEW,
    (ReviewStatus.RESUBMITTED, "REQUEST_CHANGES"): ReviewStatus.CHANGES_REQUESTED,
    (ReviewStatus.RESUBMITTED, "FORWARD_FOR_APPROVAL"): ReviewStatus.PENDING_BRAND_APPROVAL,
    (ReviewStatus.RESUBMITTED, "REQUEST_LEGAL"): ReviewStatus.PENDING_LEGAL_APPROVAL,
    (ReviewStatus.RESUBMITTED, "APPROVE"): ReviewStatus.APPROVED,
    (ReviewStatus.RESUBMITTED, "REJECT"): ReviewStatus.REJECTED,

    # From PENDING_BRAND_APPROVAL
    (ReviewStatus.PENDING_BRAND_APPROVAL, "APPROVE"): ReviewStatus.APPROVED,
    (ReviewStatus.PENDING_BRAND_APPROVAL, "REQUEST_CHANGES"): ReviewStatus.CHANGES_REQUESTED,
    (ReviewStatus.PENDING_BRAND_APPROVAL, "REQUEST_LEGAL"): ReviewStatus.PENDING_LEGAL_APPROVAL,
    (ReviewStatus.PENDING_BRAND_APPROVAL, "REJECT"): ReviewStatus.REJECTED,

    # From PENDING_LEGAL_APPROVAL
    (ReviewStatus.PENDING_LEGAL_APPROVAL, "APPROVE_LEGAL"): ReviewStatus.PENDING_BRAND_APPROVAL,
    (ReviewStatus.PENDING_LEGAL_APPROVAL, "REQUEST_CHANGES"): ReviewStatus.CHANGES_REQUESTED,
    (ReviewStatus.PENDING_LEGAL_APPROVAL, "REJECT"): ReviewStatus.REJECTED,
}

# Roles permitted to execute each action
ACTION_PERMITTED_ROLES = {
    "SUBMIT": {UserRole.CONTENT_CREATOR, UserRole.EXTERNAL_AGENCY, UserRole.REVIEWER, UserRole.BRAND_MANAGER, UserRole.ADMIN},
    "WITHDRAW": {UserRole.CONTENT_CREATOR, UserRole.EXTERNAL_AGENCY, UserRole.BRAND_MANAGER, UserRole.ADMIN},
    "START_REVIEW": {UserRole.REVIEWER, UserRole.BRAND_MANAGER, UserRole.LEGAL_REVIEWER, UserRole.ADMIN},
    "REQUEST_CHANGES": {UserRole.REVIEWER, UserRole.BRAND_MANAGER, UserRole.LEGAL_REVIEWER, UserRole.ADMIN},
    "RESUBMIT": {UserRole.CONTENT_CREATOR, UserRole.EXTERNAL_AGENCY, UserRole.ADMIN},
    "FORWARD_FOR_APPROVAL": {UserRole.REVIEWER, UserRole.BRAND_MANAGER, UserRole.ADMIN},
    "REQUEST_LEGAL": {UserRole.REVIEWER, UserRole.BRAND_MANAGER, UserRole.ADMIN},
    "APPROVE_LEGAL": {UserRole.LEGAL_REVIEWER, UserRole.ADMIN},
    "APPROVE": {UserRole.BRAND_MANAGER, UserRole.ADMIN},
    "REJECT": {UserRole.REVIEWER, UserRole.BRAND_MANAGER, UserRole.LEGAL_REVIEWER, UserRole.ADMIN},
}


class WorkflowStateMachine:
    """Central authority for governing review lifecycle transitions."""

    @staticmethod
    def transition(
        db: Session,
        review: Review,
        action: str,
        actor: User,
        notes: Optional[str] = None,
        new_version_id: Optional[str] = None
    ) -> Review:
        """
        Execute an authorized workflow transition.

        Validates:
        1. Action is permitted for the actor's role.
        2. Transition from current review status via action is valid.
        3. Mandatory notes for rejection, change request, or dismissal.
        4. Self-approval prevention (Content Creator cannot approve their own submission).
        5. Legal review completion check prior to final approval if required.
        6. Locking of document version upon approval.
        7. Logging of immutable review_history and system audit_log.
        """
        action = action.upper().strip()
        from_status = review.status

        # 1. Role Authorization
        allowed_roles = ACTION_PERMITTED_ROLES.get(action)
        if not allowed_roles or actor.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{actor.role.value}' is not authorized to execute review action '{action}'."
            )

        # 2. Valid Transition State Check
        key = (from_status, action)
        if key not in VALID_TRANSITIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid workflow transition: Cannot execute action '{action}' from status '{from_status.value}'."
            )
        to_status = VALID_TRANSITIONS[key]

        # 3. Mandatory Reason / Notes Checks
        if action in ["REQUEST_CHANGES", "REJECT"] and (not notes or not notes.strip()):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Action '{action}' requires a mandatory explanation/reason in notes."
            )

        # 4. Self-Approval Guardrail
        # A creator cannot approve their own submission unless they are an Administrator
        if action == "APPROVE":
            if review.creator_id == actor.id and actor.role != UserRole.ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Self-approval violation: Creators are strictly prohibited from approving their own submitted content."
                )

        # 5. Legal Review Requirement Guardrail
        if action == "APPROVE" and review.legal_review_required:
            if review.legal_status != "APPROVED" and actor.role != UserRole.ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot grant final approval: Mandatory legal review has not been approved."
                )

        # 6. Apply Transition Side-Effects
        review.status = to_status
        review.updated_at = datetime.now(timezone.utc)

        # Handle specific actions
        if action == "APPROVE_LEGAL":
            review.legal_status = "APPROVED"
        elif action == "REQUEST_LEGAL":
            review.legal_review_required = True
            review.legal_status = "PENDING"
        elif action == "RESUBMIT":
            # If a new version was uploaded as part of the resubmission, update review.version_id
            if new_version_id:
                review.version_id = new_version_id
        elif action == "APPROVE":
            review.final_decision_by = actor.id
            review.final_decision_at = datetime.now(timezone.utc)
            review.decision_notes = notes

            # Lock the document version so it becomes immutable
            doc_ver = db.query(DocumentVersion).filter(
                DocumentVersion.id == review.version_id,
                DocumentVersion.organization_id == review.organization_id
            ).first()
            if doc_ver:
                doc_ver.is_locked = True
                doc_ver.version_status = VersionWorkflowStatus.APPROVED
                doc_ver.approved_at = datetime.now(timezone.utc)
                doc_ver.approved_by = actor.id

            # Update document lifecycle
            doc = db.query(Document).filter(
                Document.id == review.document_id,
                Document.organization_id == review.organization_id
            ).first()
            if doc:
                doc.lifecycle_status = DocumentLifecycleStatus.APPROVED

        elif action == "REQUEST_CHANGES":
            doc_ver = db.query(DocumentVersion).filter(
                DocumentVersion.id == review.version_id,
                DocumentVersion.organization_id == review.organization_id
            ).first()
            if doc_ver:
                doc_ver.version_status = VersionWorkflowStatus.CHANGES_REQUIRED

        elif action == "REJECT":
            review.final_decision_by = actor.id
            review.final_decision_at = datetime.now(timezone.utc)
            review.decision_notes = notes
            doc_ver = db.query(DocumentVersion).filter(
                DocumentVersion.id == review.version_id,
                DocumentVersion.organization_id == review.organization_id
            ).first()
            if doc_ver:
                doc_ver.version_status = VersionWorkflowStatus.REJECTED

        # 7. Record Immutable Review History
        history = ReviewHistory(
            organization_id=review.organization_id,
            review_id=review.id,
            actor_id=actor.id,
            from_status=from_status.value,
            to_status=to_status.value,
            action=action,
            notes=notes
        )
        db.add(history)

        # 8. Record Immutable Audit Log
        log_action(
            db=db,
            organization_id=review.organization_id,
            actor_id=actor.id,
            action=f"REVIEW_{action}",
            target_entity="reviews",
            target_id=review.id,
            details={
                "from_status": from_status.value,
                "to_status": to_status.value,
                "action": action,
                "document_id": str(review.document_id),
                "version_id": str(review.version_id),
                "notes": notes
            }
        )

        db.commit()
        db.refresh(review)
        return review

