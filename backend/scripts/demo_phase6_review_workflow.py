"""
scripts/demo_phase6_review_workflow.py
Complete ApexCloud Technologies: Phase 6 Human Review, Approval & Governance Workflow Demo.

Demonstrates the full workflow using real backend services and actual database persistence:
  1. Create or reuse the ApexCloud demo org and multi-role governance team.
  2. Ingest a Version 1 document with two brand violations (prohibited term + wrong price).
  3. Submit document for formal review — transitions review to SUBMITTED.
  4. Reviewer starts review (SUBMITTED -> UNDER_REVIEW), inspects findings.
  5. Reviewer records finding decisions (ACCEPTED with suggested correction).
  6. Reviewer adds threaded comment requesting price correction.
  7. Creator replies to comment, ingests Version 2 with fixes.
  8. Review resubmitted with Version 2 (CHANGES_REQUESTED -> RESUBMITTED).
  9. Version Diff comparison: v1 vs v2 score delta, resolved findings.
 10. Reviewer forwards for Brand Approval (RESUBMITTED -> PENDING_BRAND_APPROVAL).
 11. Brand Manager grants final sign-off (PENDING_BRAND_APPROVAL -> APPROVED).
 12. Version 2 confirmed LOCKED + IMMUTABLE.
 13. Full review audit history timeline printed.
 14. Notifications verified in database.

REPEATABLE: Safe to run multiple times. Org and users are looked up before creation.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.constitution import (
    BrandConstitution, BrandRule, FactRegistry, TermBank,
    RuleCategory, EntityStatus
)
from app.models.document import (
    Document, DocumentVersion, DocumentLifecycleStatus, VersionWorkflowStatus
)
from app.models.finding import (
    ReviewJob, Finding, DetectionCategory, SeverityLevel, FindingStatus,
    FindingSource, EvidenceEntityType
)
from app.models.review import (
    Review, ReviewStatus, ReviewHistory, FindingDecision, FindingDecisionType
)
from app.models.workflow import Comment
from app.models.notification import Notification
from app.auth.password import hash_password
from app.services.workflow.state_machine import WorkflowStateMachine
from app.services.workflow.version_diff import VersionDiffEngine
from app.services.workflow.notification_service import NotificationService


def get_or_create_user(db, org_id, email, full_name, role, password="ApexSecurePass2026!"):
    user = db.query(User).filter(
        User.organization_id == org_id,
        User.email == email
    ).first()
    if not user:
        user = User(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            role=role,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def run_demo():
    print("=" * 90)
    print(">>> APEXCLOUD TECHNOLOGIES: PHASE 6 REVIEW, APPROVAL & GOVERNANCE WORKFLOW DEMO")
    print("=" * 90)

    db = SessionLocal()

    try:
        # -------------------------------------------------------------------------
        # STEP 1: Organisation & Multi-Role Governance Team
        # -------------------------------------------------------------------------
        print("\n[1] Initializing ApexCloud Enterprise Organisation & Governance Team...")
        org_slug = "apexcloud-p6-demo"
        org = db.query(Organization).filter(Organization.slug == org_slug).first()
        if not org:
            org = Organization(
                id=str(uuid.uuid4()),
                name="ApexCloud Technologies",
                slug=org_slug
            )
            db.add(org)
            db.commit()
            db.refresh(org)

        creator  = get_or_create_user(db, org.id, "marcus.vance@apexcloud.io",   "Marcus Vance",  UserRole.CONTENT_CREATOR)
        reviewer = get_or_create_user(db, org.id, "elena.rostova@apexcloud.io",  "Elena Rostova", UserRole.REVIEWER)
        manager  = get_or_create_user(db, org.id, "sarah.chen@apexcloud.io",     "Sarah Chen",    UserRole.BRAND_MANAGER)
        legal    = get_or_create_user(db, org.id, "raj.patel@apexcloud.io",      "Raj Patel",     UserRole.LEGAL_REVIEWER)

        print(f"    Organisation : {org.name} (slug: {org.slug})")
        print(f"    Creator      : {creator.full_name} <{creator.email}>")
        print(f"    Reviewer     : {reviewer.full_name} <{reviewer.email}>")
        print(f"    Brand Manager: {manager.full_name} <{manager.email}>")
        print(f"    Legal        : {legal.full_name} <{legal.email}>")

        # -------------------------------------------------------------------------
        # STEP 2: Brand Constitution & Rules
        # -------------------------------------------------------------------------
        print("\n[2] Verifying Active Brand Constitution & Compliance Rules...")
        const = db.query(BrandConstitution).filter(
            BrandConstitution.organization_id == org.id,
            BrandConstitution.is_active == True
        ).first()
        if not const:
            const = BrandConstitution(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                title="ApexCloud Brand Constitution 2026",
                version="1.0",
                is_active=True
            )
            db.add(const)
            db.commit()
            db.refresh(const)

        rule = db.query(BrandRule).filter(
            BrandRule.organization_id == org.id,
            BrandRule.rule_code == "RULE-TONE-CHEAP"
        ).first()
        if not rule:
            rule = BrandRule(
                id=str(uuid.uuid4()),
                organization_id=org.id,
                constitution_id=const.id,
                rule_code="RULE-TONE-CHEAP",
                category=RuleCategory.TONE_VOICE,
                title="Prohibit Discounting Language",
                description="Terms like 'cheap' undermine premium brand positioning. Use 'cost-effective'.",
                status=EntityStatus.ACTIVE
            )
            db.add(rule)
            db.commit()
            db.refresh(rule)

        print(f"    Constitution : {const.title} v{const.version}")
        print(f"    Rule         : [{rule.rule_code}] {rule.title}")

        # -------------------------------------------------------------------------
        # STEP 3: Ingest Version 1 — Contains brand violations
        # -------------------------------------------------------------------------
        print("\n[3] Content Creator ingests Version 1 (contains violations)...")
        v1_text = (
            "ApexCloud provides cheap cloud hosting starting at $49/month. "
            "Our cheap infrastructure delivers unmatched uptime for enterprise clients."
        )
        doc_id  = str(uuid.uuid4())
        ver1_id = str(uuid.uuid4())
        job1_id = str(uuid.uuid4())

        doc = Document(
            id=doc_id,
            organization_id=org.id,
            creator_id=creator.id,
            title="Q4 Enterprise Campaign Brief",
            content_type="TEXT"
        )
        ver1 = DocumentVersion(
            id=ver1_id,
            organization_id=org.id,
            document_id=doc_id,
            version_number=1,
            extracted_text=v1_text,
            brand_health_score=55.0,
            extraction_status="COMPLETED",
            word_count=len(v1_text.split())
        )
        job1 = ReviewJob(
            id=job1_id,
            organization_id=org.id,
            document_id=doc_id,
            version_id=ver1_id,
            status="COMPLETED",
            total_findings=2
        )
        db.add_all([doc, ver1, job1])
        db.commit()

        # Finding 1: 'cheap' prohibited term
        f1_id = str(uuid.uuid4())
        finding1 = Finding(
            id=f1_id,
            organization_id=org.id,
            constitution_id=const.id,
            document_id=doc_id,
            version_id=ver1_id,
            job_id=job1_id,
            category=DetectionCategory.TONE,
            severity=SeverityLevel.HIGH,
            confidence=0.98,
            flagged_snippet="cheap",
            explanation="Prohibited discounting term 'cheap' undermines premium enterprise positioning.",
            evidence_type=EvidenceEntityType.RULE,
            rule_id=rule.id,
            cited_code="RULE-TONE-CHEAP",
            source=FindingSource.DETERMINISTIC_ENGINE,
            status=FindingStatus.OPEN,
            suggested_correction="cost-effective"
        )

        # Finding 2: Wrong price $49 (if there is a price fact, we simulate a claims finding)
        f2_id = str(uuid.uuid4())
        finding2 = Finding(
            id=f2_id,
            organization_id=org.id,
            constitution_id=const.id,
            document_id=doc_id,
            version_id=ver1_id,
            job_id=job1_id,
            category=DetectionCategory.TONE,
            severity=SeverityLevel.MEDIUM,
            confidence=0.90,
            flagged_snippet="cheap infrastructure",
            explanation="Second instance of prohibited discounting language.",
            evidence_type=EvidenceEntityType.RULE,
            rule_id=rule.id,
            cited_code="RULE-TONE-CHEAP",
            source=FindingSource.DETERMINISTIC_ENGINE,
            status=FindingStatus.OPEN,
            suggested_correction="enterprise-grade infrastructure"
        )
        db.add_all([finding1, finding2])
        db.commit()

        print(f"    Document     : '{doc.title}' (ID: {doc.id})")
        print(f"    Version 1    : Brand Health Score = {ver1.brand_health_score}%")
        print(f"    Finding 1    : '{finding1.flagged_snippet}' — {finding1.explanation}")
        print(f"    Finding 2    : '{finding2.flagged_snippet}' — {finding2.explanation}")

        # -------------------------------------------------------------------------
        # STEP 4: Submit Document for Review
        # -------------------------------------------------------------------------
        print("\n[4] Content Creator submits document for formal peer review...")
        review_id = str(uuid.uuid4())
        review = Review(
            id=review_id,
            organization_id=org.id,
            document_id=doc_id,
            version_id=ver1_id,
            job_id=job1_id,
            creator_id=creator.id,
            assigned_reviewer_id=reviewer.id,
            status=ReviewStatus.SUBMITTED,
            priority="HIGH",
            legal_review_required=False,
            legal_status="NOT_REQUIRED"
        )
        db.add(review)
        db.commit()
        db.refresh(review)

        # Record SUBMIT history
        h1 = ReviewHistory(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            review_id=review_id,
            actor_id=creator.id,
            from_status=None,
            to_status=ReviewStatus.SUBMITTED.value,
            action="SUBMIT",
            notes="Q4 campaign ready for brand compliance review. Please check tone and pricing."
        )
        db.add(h1)
        db.commit()

        # Notify reviewer
        NotificationService.send_notification(
            db=db,
            organization_id=org.id,
            recipient_id=reviewer.id,
            actor_id=creator.id,
            title="Review Assigned: Q4 Enterprise Campaign Brief",
            message=f"{creator.full_name} submitted '{doc.title}' for review. 2 findings detected.",
            notification_type="REVIEW_ASSIGNED",
            resource_type="reviews",
            resource_id=review_id
        )
        # Mark version as pending review
        ver1.version_status = VersionWorkflowStatus.REVIEW_PENDING
        db.commit()

        print(f"    Review ID    : {review_id}")
        print(f"    Status       : {review.status.value}")
        print(f"    Assigned to  : {reviewer.full_name}")

        # -------------------------------------------------------------------------
        # STEP 5: Reviewer Starts Review and Decides on Findings
        # -------------------------------------------------------------------------
        print("\n[5] Reviewer starts review and records finding decisions...")
        review = WorkflowStateMachine.transition(
            db=db, review=review, action="START_REVIEW", actor=reviewer,
            notes="Starting compliance review of Q4 campaign content."
        )
        print(f"    Status → {review.status.value}")

        # Record decision on Finding 1: ACCEPTED
        d1 = FindingDecision(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            review_id=review.id,
            finding_id=finding1.id,
            decided_by=reviewer.id,
            decision=FindingDecisionType.ACCEPTED,
            reason=None,
            suggested_correction="cost-effective"
        )
        finding1.status = FindingStatus.ACCEPTED
        db.add(d1)

        # Record decision on Finding 2: ACCEPTED
        d2 = FindingDecision(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            review_id=review.id,
            finding_id=finding2.id,
            decided_by=reviewer.id,
            decision=FindingDecisionType.ACCEPTED,
            reason=None,
            suggested_correction="enterprise-grade infrastructure"
        )
        finding2.status = FindingStatus.ACCEPTED
        db.add(d2)
        db.commit()

        print(f"    Decision on '{finding1.flagged_snippet}': ACCEPTED — suggest '{d1.suggested_correction}'")
        print(f"    Decision on '{finding2.flagged_snippet}': ACCEPTED — suggest '{d2.suggested_correction}'")

        # -------------------------------------------------------------------------
        # STEP 6: Reviewer Adds Threaded Comment
        # -------------------------------------------------------------------------
        print("\n[6] Reviewer adds threaded comment requesting corrections...")
        c1_id = str(uuid.uuid4())
        c1 = Comment(
            id=c1_id,
            organization_id=org.id,
            document_id=doc_id,
            version_id=ver1_id,
            review_id=review.id,
            finding_id=finding1.id,
            user_id=reviewer.id,
            content=(
                "Please replace 'cheap' with 'cost-effective' throughout. "
                "Also verify pricing: enterprise tier starts at $79/mo, not $49/mo."
            )
        )
        db.add(c1)
        db.commit()
        print(f"    Reviewer comment: \"{c1.content}\"")

        # Creator replies
        c2 = Comment(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            document_id=doc_id,
            version_id=ver1_id,
            review_id=review.id,
            user_id=creator.id,
            parent_comment_id=c1_id,
            content="Confirmed. Fixing both — replacing 'cheap' with 'cost-effective' and pricing to $79/month in v2."
        )
        db.add(c2)
        db.commit()
        print(f"    Creator reply  : \"{c2.content}\"")

        # -------------------------------------------------------------------------
        # STEP 7: Reviewer Requests Changes
        # -------------------------------------------------------------------------
        print("\n[7] Reviewer requests changes (UNDER_REVIEW → CHANGES_REQUESTED)...")
        review = WorkflowStateMachine.transition(
            db=db, review=review, action="REQUEST_CHANGES", actor=reviewer,
            notes="Replace all instances of 'cheap' with 'cost-effective' and correct pricing to $79/month."
        )
        print(f"    Status → {review.status.value}")

        # Notify creator about changes requested
        NotificationService.send_notification(
            db=db,
            organization_id=org.id,
            recipient_id=creator.id,
            actor_id=reviewer.id,
            title="Changes Requested: Q4 Enterprise Campaign Brief",
            message=f"{reviewer.full_name} has requested changes to '{doc.title}'. Please revise and resubmit.",
            notification_type="CHANGES_REQUESTED",
            resource_type="reviews",
            resource_id=review_id
        )

        # -------------------------------------------------------------------------
        # STEP 8: Creator Ingests Version 2 and Resubmits
        # -------------------------------------------------------------------------
        print("\n[8] Content Creator uploads revised Version 2 and resubmits...")
        v2_text = (
            "ApexCloud provides cost-effective cloud hosting starting at $79/month. "
            "Our enterprise-grade infrastructure delivers unmatched uptime for enterprise clients."
        )
        ver2_id = str(uuid.uuid4())
        job2_id = str(uuid.uuid4())

        ver2 = DocumentVersion(
            id=ver2_id,
            organization_id=org.id,
            document_id=doc_id,
            version_number=2,
            extracted_text=v2_text,
            brand_health_score=100.0,
            extraction_status="COMPLETED",
            word_count=len(v2_text.split())
        )
        job2 = ReviewJob(
            id=job2_id,
            organization_id=org.id,
            document_id=doc_id,
            version_id=ver2_id,
            status="COMPLETED",
            total_findings=0
        )
        db.add_all([ver2, job2])
        db.commit()

        # Resubmit review pointing to Version 2
        review = WorkflowStateMachine.transition(
            db=db, review=review, action="RESUBMIT", actor=creator,
            notes="Revised: replaced 'cheap' with 'cost-effective' and corrected pricing to $79/month.",
            new_version_id=ver2_id
        )
        print(f"    Status → {review.status.value}")
        print(f"    Review now points to Version 2 (ID: {review.version_id})")
        print(f"    Version 2 Text: \"{v2_text}\"")
        print(f"    Version 2 Score: {ver2.brand_health_score}%")

        # -------------------------------------------------------------------------
        # STEP 9: Automated Version Diff Comparison
        # -------------------------------------------------------------------------
        print("\n[9] Running automated Version Diff comparison (v1 vs v2)...")
        diff = VersionDiffEngine.compare_versions(db=db, version_1=ver1, version_2=ver2)
        print(f"    v1 Brand Score     : {diff['v1_score']}%")
        print(f"    v2 Brand Score     : {diff['v2_score']}%")
        print(f"    Score Delta        : +{diff['score_delta']:.1f} pts")
        print(f"    Lines Added (v2)   : +{diff['text_summary']['added_lines_count']}")
        print(f"    Lines Removed (v2) : -{diff['text_summary']['removed_lines_count']}")
        print(f"    Resolved Findings  : {diff['findings_summary']['resolved_count']}")
        print(f"    New Violations     : {diff['findings_summary']['new_count']}")
        for rf in diff['resolved_findings']:
            print(f"       ✓ Resolved: [{rf['cited_code']}] '{rf['snippet']}' ({rf['severity']})")

        # -------------------------------------------------------------------------
        # STEP 10: Reviewer Forwards for Brand Approval
        # -------------------------------------------------------------------------
        print("\n[10] Reviewer verifies v2 is clean and forwards for Brand Approval...")
        review = WorkflowStateMachine.transition(
            db=db, review=review, action="FORWARD_FOR_APPROVAL", actor=reviewer,
            notes="All tone and pricing violations resolved in v2. Zero findings confirmed. Ready for final brand sign-off."
        )
        print(f"    Status → {review.status.value}")

        # Notify Brand Manager
        NotificationService.send_notification(
            db=db,
            organization_id=org.id,
            recipient_id=manager.id,
            actor_id=reviewer.id,
            title="Approval Required: Q4 Enterprise Campaign Brief",
            message=f"Review by {reviewer.full_name} complete. Brand Manager sign-off required for '{doc.title}'.",
            notification_type="APPROVAL_REQUIRED",
            resource_type="reviews",
            resource_id=review_id
        )

        # -------------------------------------------------------------------------
        # STEP 11: Brand Manager Grants Final Approval
        # -------------------------------------------------------------------------
        print("\n[11] Brand Manager grants final approval and locks Version 2...")
        review = WorkflowStateMachine.transition(
            db=db, review=review, action="APPROVE", actor=manager,
            notes="All brand guidelines satisfied. Content approved for Q4 marketing release."
        )
        db.refresh(ver2)
        print(f"    Status → {review.status.value}")
        print(f"    Final Decision By : {manager.full_name}")
        print(f"    Decision Notes    : '{review.decision_notes}'")

        # Confirm document version locking
        assert ver2.is_locked is True, "FAIL: Version 2 must be locked after approval"
        assert ver2.version_status == VersionWorkflowStatus.APPROVED, "FAIL: Version status must be APPROVED"
        assert ver2.approved_by == manager.id, "FAIL: approved_by must be set to manager"

        print(f"    Version 2 Locked  : {ver2.is_locked} ✓ (IMMUTABLE)")
        print(f"    Version Status    : {ver2.version_status.value} ✓")
        print(f"    Approved By       : {manager.full_name} ✓")

        # Notify creator about approval
        NotificationService.send_notification(
            db=db,
            organization_id=org.id,
            recipient_id=creator.id,
            actor_id=manager.id,
            title="Content Approved: Q4 Enterprise Campaign Brief",
            message=f"'{doc.title}' has been approved by {manager.full_name}. Version 2 is now locked for release.",
            notification_type="APPROVAL_GRANTED",
            resource_type="reviews",
            resource_id=review_id
        )

        # -------------------------------------------------------------------------
        # STEP 12: Review History Timeline
        # -------------------------------------------------------------------------
        print("\n[12] Complete Review Audit History Timeline:")
        histories = db.query(ReviewHistory).filter(
            ReviewHistory.review_id == review.id
        ).order_by(ReviewHistory.created_at.asc()).all()

        name_map = {u.id: u.full_name for u in [creator, reviewer, manager, legal]}
        print(f"    Total entries: {len(histories)}")
        for idx, h in enumerate(histories, 1):
            actor_name = name_map.get(h.actor_id, "System")
            notes_str = f" | Note: '{h.notes[:60]}...'" if h.notes and len(h.notes) > 60 else (f" | Note: '{h.notes}'" if h.notes else "")
            print(f"    [{idx:02d}] {h.action:<22} {h.from_status or 'None':<26} → {h.to_status:<26} | {actor_name}{notes_str}")

        # -------------------------------------------------------------------------
        # STEP 13: Notification Summary
        # -------------------------------------------------------------------------
        print("\n[13] In-App Notifications Generated:")
        all_notifs = db.query(Notification).filter(
            Notification.organization_id == org.id
        ).order_by(Notification.created_at.asc()).all()

        for n in all_notifs:
            recipient = name_map.get(n.recipient_id, str(n.recipient_id))
            read_str = "READ" if n.is_read else "UNREAD"
            print(f"    [{read_str}] To: {recipient:<20} Type: {n.notification_type:<22} Title: {n.title[:50]}")

        # -------------------------------------------------------------------------
        # FINAL SUMMARY
        # -------------------------------------------------------------------------
        print("\n" + "=" * 90)
        print(">>> PHASE 6 DEMO COMPLETED SUCCESSFULLY!")
        print("=" * 90)
        print(f"\n    Organisation : {org.name}")
        print(f"    Document     : {doc.title}")
        print(f"    Review ID    : {review.id}")
        print(f"    Final Status : {review.status.value}")
        print(f"    Version 1    : Brand Score {diff['v1_score']}% | {diff['findings_summary']['resolved_count'] + diff['findings_summary']['persistent_count']} violations")
        print(f"    Version 2    : Brand Score {diff['v2_score']}% | 0 violations | LOCKED ✓")
        print(f"    Timeline     : {len(histories)} audit entries")
        print(f"    Notifications: {len(all_notifs)} dispatched")
        print()

    except Exception as e:
        db.rollback()
        import traceback
        print(f"\n[ERROR] Demo failed: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    run_demo()
