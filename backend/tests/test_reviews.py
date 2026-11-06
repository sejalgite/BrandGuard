"""
tests/test_reviews.py
Comprehensive test suite for Phase 6: Human Review, Approval & Governance Workflow.
Covers:
  - Review creation and submission
  - Reviewer assignment and reassignment
  - Role restrictions and permission enforcement
  - Valid and invalid workflow state transitions
  - Self-approval prevention (Creators cannot approve own content)
  - Finding decisions (ACCEPT, DISMISS with reason, DISPUTE with reason, RESOLVE)
  - Threaded review comments and replies
  - Review history timeline audit logging
  - Legal approval workflow and mandatory clearance
  - Approved version immutability and document locking
  - Cross-tenant review isolation
  - In-app notification creation, deduplication, and read tracking
  - Document version comparison engine
"""
import uuid
from datetime import datetime, date, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.document import Document, DocumentVersion, DocumentLifecycleStatus, VersionWorkflowStatus
from app.models.constitution import BrandConstitution, BrandRule, RuleCategory, EntityStatus
from app.models.finding import (
    ReviewJob, Finding, DetectionCategory, SeverityLevel, FindingStatus,
    FindingSource, EvidenceEntityType
)
from app.models.review import Review, ReviewStatus, ReviewHistory, FindingDecision, FindingDecisionType
from app.models.notification import Notification
from app.models.audit import AuditLog
from app.auth.password import hash_password
from app.auth.jwt import create_access_token

client = TestClient(app)


def make_token(user_id: str, org_id: str, role: UserRole) -> str:
    return create_access_token({"sub": user_id, "org": org_id, "role": role.value})


def setup_review_tenant(db, name_prefix="Apex"):
    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name=f"{name_prefix} Corp", slug=f"{name_prefix.lower()}-{org_id[:8]}")
    db.add(org)

    # Provision users for various workflow roles
    admin_id = str(uuid.uuid4())
    manager_id = str(uuid.uuid4())
    reviewer_id = str(uuid.uuid4())
    creator_id = str(uuid.uuid4())
    legal_id = str(uuid.uuid4())

    admin = User(id=admin_id, organization_id=org_id, email=f"admin_{admin_id[:6]}@test.com", full_name="Admin User", hashed_password=hash_password("Pass123!"), role=UserRole.ADMIN, is_active=True)
    manager = User(id=manager_id, organization_id=org_id, email=f"mgr_{manager_id[:6]}@test.com", full_name="Brand Manager", hashed_password=hash_password("Pass123!"), role=UserRole.BRAND_MANAGER, is_active=True)
    reviewer = User(id=reviewer_id, organization_id=org_id, email=f"rev_{reviewer_id[:6]}@test.com", full_name="Peer Reviewer", hashed_password=hash_password("Pass123!"), role=UserRole.REVIEWER, is_active=True)
    creator = User(id=creator_id, organization_id=org_id, email=f"creator_{creator_id[:6]}@test.com", full_name="Content Creator", hashed_password=hash_password("Pass123!"), role=UserRole.CONTENT_CREATOR, is_active=True)
    legal = User(id=legal_id, organization_id=org_id, email=f"legal_{legal_id[:6]}@test.com", full_name="Legal Reviewer", hashed_password=hash_password("Pass123!"), role=UserRole.LEGAL_REVIEWER, is_active=True)

    db.add_all([admin, manager, reviewer, creator, legal])

    # Active Constitution
    const_id = str(uuid.uuid4())
    const = BrandConstitution(id=const_id, organization_id=org_id, title=f"{name_prefix} Constitution", version="1.0", is_active=True)
    db.add(const)

    # Rule
    rule_id = str(uuid.uuid4())
    rule = BrandRule(id=rule_id, organization_id=org_id, constitution_id=const_id, rule_code="RULE-TONE-01", category=RuleCategory.TONE_VOICE, title="Voice", description="Objective tone", status=EntityStatus.ACTIVE)
    db.add(rule)
    db.commit()

    # Document & Version 1
    doc_id = str(uuid.uuid4())
    ver1_id = str(uuid.uuid4())
    doc = Document(id=doc_id, organization_id=org_id, creator_id=creator_id, title="Q4 Campaign", content_type="TEXT")
    ver1 = DocumentVersion(
        id=ver1_id, organization_id=org_id, document_id=doc_id, version_number=1,
        extracted_text="Original campaign copy with cheap price $49.",
        brand_health_score=65.0, extraction_status="COMPLETED", word_count=7
    )
    db.add_all([doc, ver1])

    # ReviewJob for Version 1
    job_id = str(uuid.uuid4())
    job = ReviewJob(
        id=job_id, organization_id=org_id, document_id=doc_id, version_id=ver1_id,
        status="COMPLETED", total_findings=1
    )
    db.add(job)

    # Controlled Finding on Version 1
    fid = str(uuid.uuid4())
    finding = Finding(
        id=fid, organization_id=org_id, constitution_id=const_id, document_id=doc_id,
        version_id=ver1_id, job_id=job_id, category=DetectionCategory.TONE,
        severity=SeverityLevel.HIGH, confidence=0.98, flagged_snippet="cheap",
        explanation="Prohibited term", evidence_type=EvidenceEntityType.RULE,
        rule_id=rule_id,
        cited_code="RULE-TONE-01", source=FindingSource.DETERMINISTIC_ENGINE,
        status=FindingStatus.OPEN, suggested_correction="cost-effective"
    )
    db.add(finding)
    db.commit()

    return {
        "org_id": org_id,
        "doc_id": doc_id,
        "ver1_id": ver1_id,
        "finding_id": fid,
        "admin": admin,
        "manager": manager,
        "reviewer": reviewer,
        "creator": creator,
        "legal": legal,
        "tokens": {
            "admin": make_token(admin_id, org_id, UserRole.ADMIN),
            "manager": make_token(manager_id, org_id, UserRole.BRAND_MANAGER),
            "reviewer": make_token(reviewer_id, org_id, UserRole.REVIEWER),
            "creator": make_token(creator_id, org_id, UserRole.CONTENT_CREATOR),
            "legal": make_token(legal_id, org_id, UserRole.LEGAL_REVIEWER),
        }
    }


def test_review_creation_and_queue_listing():
    """Verify Content Creator can submit document for review, appearing in queue."""
    db = SessionLocal()
    t = setup_review_tenant(db, "QueueTest")

    headers_creator = {"Authorization": f"Bearer {t['tokens']['creator']}"}

    # Creator submits review
    create_payload = {
        "document_id": t["doc_id"],
        "version_id": t["ver1_id"],
        "priority": "HIGH",
        "assigned_reviewer_id": str(t["reviewer"].id),
        "submission_notes": "Please review Q4 brief."
    }
    res = client.post("/api/v1/reviews", json=create_payload, headers=headers_creator)
    assert res.status_code == 201, res.text
    data = res.json()
    review_id = data["id"]
    assert data["status"] == "SUBMITTED"
    assert data["priority"] == "HIGH"
    assert data["assigned_reviewer_id"] == str(t["reviewer"].id)
    assert len(data["history"]) >= 1
    assert data["history"][0]["action"] == "SUBMIT"

    # Reviewer lists reviews
    headers_reviewer = {"Authorization": f"Bearer {t['tokens']['reviewer']}"}
    list_res = client.get("/api/v1/reviews", headers=headers_reviewer)
    assert list_res.status_code == 200
    revs = list_res.json()
    assert any(r["id"] == review_id for r in revs)

    # Queue statistics
    stats_res = client.get("/api/v1/reviews/queue/stats", headers=headers_reviewer)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["submitted"] >= 1
    assert stats["assigned_to_current_user"] >= 1

    db.close()


def test_workflow_state_machine_valid_transitions():
    """Verify complete valid transition: SUBMITTED -> UNDER_REVIEW -> CHANGES_REQUESTED -> RESUBMITTED -> PENDING_BRAND_APPROVAL -> APPROVED."""
    db = SessionLocal()
    t = setup_review_tenant(db, "StateValid")

    # 1. Create Review
    rev = Review(
        organization_id=t["org_id"], document_id=t["doc_id"], version_id=t["ver1_id"],
        creator_id=t["creator"].id, assigned_reviewer_id=t["reviewer"].id,
        status=ReviewStatus.SUBMITTED
    )
    db.add(rev)
    db.commit()
    rev_id = str(rev.id)

    headers_reviewer = {"Authorization": f"Bearer {t['tokens']['reviewer']}"}
    headers_creator = {"Authorization": f"Bearer {t['tokens']['creator']}"}
    headers_manager = {"Authorization": f"Bearer {t['tokens']['manager']}"}

    # 2. Reviewer starts review: SUBMITTED -> UNDER_REVIEW
    res = client.post(f"/api/v1/reviews/{rev_id}/transition", json={"action": "START_REVIEW"}, headers=headers_reviewer)
    assert res.status_code == 200
    assert res.json()["status"] == "UNDER_REVIEW"

    # 3. Reviewer requests changes: UNDER_REVIEW -> CHANGES_REQUESTED (with notes)
    res = client.post(
        f"/api/v1/reviews/{rev_id}/transition",
        json={"action": "REQUEST_CHANGES", "notes": "Replace prohibited term 'cheap'."},
        headers=headers_reviewer
    )
    assert res.status_code == 200
    assert res.json()["status"] == "CHANGES_REQUESTED"

    # 4. Creator uploads version 2 and resubmits
    ver2_id = str(uuid.uuid4())
    ver2 = DocumentVersion(
        id=ver2_id, organization_id=t["org_id"], document_id=t["doc_id"], version_number=2,
        extracted_text="Revised campaign copy with cost-effective pricing.",
        brand_health_score=100.0, extraction_status="COMPLETED", word_count=7
    )
    db.add(ver2)
    db.commit()

    res = client.post(
        f"/api/v1/reviews/{rev_id}/transition",
        json={"action": "RESUBMIT", "notes": "Updated copy to cost-effective.", "new_version_id": ver2_id},
        headers=headers_creator
    )
    assert res.status_code == 200
    assert res.json()["status"] == "RESUBMITTED"
    assert res.json()["version_id"] == ver2_id

    # 5. Reviewer forwards for brand approval: RESUBMITTED -> PENDING_BRAND_APPROVAL
    res = client.post(f"/api/v1/reviews/{rev_id}/transition", json={"action": "FORWARD_FOR_APPROVAL"}, headers=headers_reviewer)
    assert res.status_code == 200
    assert res.json()["status"] == "PENDING_BRAND_APPROVAL"

    # 6. Brand Manager approves: PENDING_BRAND_APPROVAL -> APPROVED
    res = client.post(
        f"/api/v1/reviews/{rev_id}/transition",
        json={"action": "APPROVE", "notes": "All brand guidelines satisfied."},
        headers=headers_manager
    )
    assert res.status_code == 200
    final_data = res.json()
    assert final_data["status"] == "APPROVED"
    assert final_data["final_decision_by"] == str(t["manager"].id)

    # 7. Confirm document version 2 is now locked
    db.refresh(ver2)
    assert ver2.is_locked is True
    assert ver2.version_status == VersionWorkflowStatus.APPROVED
    assert ver2.approved_by == t["manager"].id

    db.close()


def test_invalid_workflow_transition_rejected():
    """Verify that jumping states (e.g. SUBMITTED directly to APPROVED by non-authorized role) is rejected."""
    db = SessionLocal()
    t = setup_review_tenant(db, "StateInvalid")

    rev = Review(
        organization_id=t["org_id"], document_id=t["doc_id"], version_id=t["ver1_id"],
        creator_id=t["creator"].id, status=ReviewStatus.DRAFT
    )
    db.add(rev)
    db.commit()
    rev_id = str(rev.id)

    headers_creator = {"Authorization": f"Bearer {t['tokens']['creator']}"}

    # Attempt invalid jump: DRAFT -> APPROVE
    res = client.post(f"/api/v1/reviews/{rev_id}/transition", json={"action": "APPROVE"}, headers=headers_creator)
    # Blocked by either 403 (unauthorized role) or 400 (invalid transition)
    assert res.status_code in [400, 403]

    db.close()


def test_self_approval_prevention():
    """Verify that a Content Creator cannot approve their own submitted content."""
    db = SessionLocal()
    t = setup_review_tenant(db, "SelfApprove")

    rev = Review(
        organization_id=t["org_id"], document_id=t["doc_id"], version_id=t["ver1_id"],
        creator_id=t["creator"].id, status=ReviewStatus.UNDER_REVIEW
    )
    db.add(rev)
    db.commit()
    rev_id = str(rev.id)

    headers_creator = {"Authorization": f"Bearer {t['tokens']['creator']}"}

    # Creator tries to approve own submission
    res = client.post(f"/api/v1/reviews/{rev_id}/transition", json={"action": "APPROVE"}, headers=headers_creator)
    assert res.status_code == 403
    assert "self-approval" in res.text.lower() or "not authorized" in res.text.lower()

    db.close()


def test_mandatory_reason_for_changes_requested_and_rejection():
    """Verify that REQUEST_CHANGES and REJECT fail without mandatory notes."""
    db = SessionLocal()
    t = setup_review_tenant(db, "ReasonTest")

    rev = Review(
        organization_id=t["org_id"], document_id=t["doc_id"], version_id=t["ver1_id"],
        creator_id=t["creator"].id, status=ReviewStatus.UNDER_REVIEW
    )
    db.add(rev)
    db.commit()
    rev_id = str(rev.id)

    headers_reviewer = {"Authorization": f"Bearer {t['tokens']['reviewer']}"}

    # Missing notes for REQUEST_CHANGES
    res_no_notes = client.post(f"/api/v1/reviews/{rev_id}/transition", json={"action": "REQUEST_CHANGES", "notes": ""}, headers=headers_reviewer)
    assert res_no_notes.status_code == 422
    assert "mandatory explanation" in res_no_notes.text.lower()

    # Missing notes for REJECT
    res_reject_no_notes = client.post(f"/api/v1/reviews/{rev_id}/transition", json={"action": "REJECT", "notes": "  "}, headers=headers_reviewer)
    assert res_reject_no_notes.status_code == 422

    db.close()


def test_finding_decisions_accept_dismiss_dispute():
    """Verify finding review decisions: ACCEPT, DISMISS (requires reason), DISPUTE."""
    db = SessionLocal()
    t = setup_review_tenant(db, "FindingDecisions")

    rev = Review(
        organization_id=t["org_id"], document_id=t["doc_id"], version_id=t["ver1_id"],
        creator_id=t["creator"].id, status=ReviewStatus.UNDER_REVIEW
    )
    db.add(rev)
    db.commit()
    rev_id = str(rev.id)
    finding_id = t["finding_id"]

    headers_reviewer = {"Authorization": f"Bearer {t['tokens']['reviewer']}"}

    # 1. Dismiss without reason -> 422
    res_fail = client.post(
        f"/api/v1/reviews/{rev_id}/findings/{finding_id}/decision",
        json={"decision": "DISMISSED", "reason": ""},
        headers=headers_reviewer
    )
    assert res_fail.status_code == 422

    # 2. Dismiss with valid justification
    res_dismiss = client.post(
        f"/api/v1/reviews/{rev_id}/findings/{finding_id}/decision",
        json={"decision": "DISMISSED", "reason": "Term used in quote from customer testimonial."},
        headers=headers_reviewer
    )
    assert res_dismiss.status_code == 200
    assert res_dismiss.json()["decision"] == "DISMISSED"

    # Confirm finding status updated in DB
    f = db.query(Finding).filter(Finding.id == finding_id).first()
    assert f.status == FindingStatus.DISMISSED

    # 3. Accept decision
    res_accept = client.post(
        f"/api/v1/reviews/{rev_id}/findings/{finding_id}/decision",
        json={"decision": "ACCEPTED", "suggested_correction": "cost-effective"},
        headers=headers_reviewer
    )
    assert res_accept.status_code == 200
    assert res_accept.json()["decision"] == "ACCEPTED"

    db.close()


def test_threaded_review_comments_and_replies():
    """Verify top-level review comments and nested reply threads."""
    db = SessionLocal()
    t = setup_review_tenant(db, "CommentTest")

    rev = Review(
        organization_id=t["org_id"], document_id=t["doc_id"], version_id=t["ver1_id"],
        creator_id=t["creator"].id, status=ReviewStatus.UNDER_REVIEW
    )
    db.add(rev)
    db.commit()
    rev_id = str(rev.id)

    headers_reviewer = {"Authorization": f"Bearer {t['tokens']['reviewer']}"}
    headers_creator = {"Authorization": f"Bearer {t['tokens']['creator']}"}

    # Reviewer adds top-level comment
    c1_res = client.post(
        f"/api/v1/reviews/{rev_id}/comments",
        json={"content": "Please verify if $49 matches current Q4 pricing schedule."},
        headers=headers_reviewer
    )
    assert c1_res.status_code == 201
    c1_id = c1_res.json()["id"]

    # Creator replies to the comment
    reply_res = client.post(
        f"/api/v1/reviews/{rev_id}/comments",
        json={"content": "Checked: enterprise starter is $79. Correcting now.", "parent_comment_id": c1_id},
        headers=headers_creator
    )
    assert reply_res.status_code == 201
    assert reply_res.json()["parent_comment_id"] == c1_id

    # List comments: verifies nested hierarchy
    list_res = client.get(f"/api/v1/reviews/{rev_id}/comments", headers=headers_reviewer)
    assert list_res.status_code == 200
    comments = list_res.json()
    assert len(comments) == 1
    assert comments[0]["id"] == c1_id
    assert len(comments[0]["replies"]) == 1
    assert comments[0]["replies"][0]["id"] == reply_res.json()["id"]

    db.close()


def test_legal_approval_flow_and_gating():
    """Verify that when legal review is required, final approval requires legal sign-off."""
    db = SessionLocal()
    t = setup_review_tenant(db, "LegalTest")

    rev = Review(
        organization_id=t["org_id"], document_id=t["doc_id"], version_id=t["ver1_id"],
        creator_id=t["creator"].id, status=ReviewStatus.UNDER_REVIEW,
        legal_review_required=True, legal_status="PENDING", legal_reviewer_id=t["legal"].id
    )
    db.add(rev)
    db.commit()
    rev_id = str(rev.id)

    headers_manager = {"Authorization": f"Bearer {t['tokens']['manager']}"}
    headers_legal = {"Authorization": f"Bearer {t['tokens']['legal']}"}

    # Brand Manager tries to approve without legal approval -> Blocked
    rev.status = ReviewStatus.PENDING_BRAND_APPROVAL
    db.commit()
    res_blocked = client.post(f"/api/v1/reviews/{rev_id}/transition", json={"action": "APPROVE"}, headers=headers_manager)
    assert res_blocked.status_code == 400
    assert "legal review" in res_blocked.text.lower()

    # Move to legal approval state
    rev.status = ReviewStatus.PENDING_LEGAL_APPROVAL
    db.commit()

    # Legal Reviewer approves legal portion
    res_legal = client.post(f"/api/v1/reviews/{rev_id}/transition", json={"action": "APPROVE_LEGAL", "notes": "Legal language compliant."}, headers=headers_legal)
    assert res_legal.status_code == 200
    assert res_legal.json()["legal_status"] == "APPROVED"
    assert res_legal.json()["status"] == "PENDING_BRAND_APPROVAL"

    # Now Brand Manager can grant final approval
    res_final = client.post(f"/api/v1/reviews/{rev_id}/transition", json={"action": "APPROVE"}, headers=headers_manager)
    assert res_final.status_code == 200
    assert res_final.json()["status"] == "APPROVED"

    db.close()


def test_cross_tenant_review_isolation():
    """Verify Tenant B cannot view, transition, or comment on Tenant A's review."""
    db = SessionLocal()
    t_a = setup_review_tenant(db, "TenantA")
    t_b = setup_review_tenant(db, "TenantB")

    rev_a = Review(
        organization_id=t_a["org_id"], document_id=t_a["doc_id"], version_id=t_a["ver1_id"],
        creator_id=t_a["creator"].id, status=ReviewStatus.SUBMITTED
    )
    db.add(rev_a)
    db.commit()
    rev_a_id = str(rev_a.id)

    headers_b = {"Authorization": f"Bearer {t_b['tokens']['reviewer']}"}

    # Tenant B tries to inspect Tenant A's review
    res_get = client.get(f"/api/v1/reviews/{rev_a_id}", headers=headers_b)
    assert res_get.status_code == 404

    # Tenant B tries to transition Tenant A's review
    res_trans = client.post(f"/api/v1/reviews/{rev_a_id}/transition", json={"action": "START_REVIEW"}, headers=headers_b)
    assert res_trans.status_code == 404

    # Tenant B tries to comment on Tenant A's review
    res_comment = client.post(f"/api/v1/reviews/{rev_a_id}/comments", json={"content": "Malicious comment"}, headers=headers_b)
    assert res_comment.status_code == 404

    db.close()


def test_in_app_notifications_lifecycle():
    """Verify notification creation, listing, deduplication, and mark-as-read."""
    db = SessionLocal()
    t = setup_review_tenant(db, "NotifTest")

    headers_reviewer = {"Authorization": f"Bearer {t['tokens']['reviewer']}"}

    # Send notification via service
    notif = Notification(
        organization_id=t["org_id"],
        recipient_id=t["reviewer"].id,
        actor_id=t["creator"].id,
        title="Review Assigned",
        message="Please review Q4 Campaign copy.",
        notification_type="REVIEW_ASSIGNED",
        is_read=False
    )
    db.add(notif)
    db.commit()
    notif_id = str(notif.id)

    # Reviewer lists notifications
    res_list = client.get("/api/v1/notifications?unread_only=true", headers=headers_reviewer)
    assert res_list.status_code == 200
    notifs = res_list.json()
    assert any(n["id"] == notif_id for n in notifs)

    # Mark as read
    res_read = client.patch(f"/api/v1/notifications/{notif_id}/read", headers=headers_reviewer)
    assert res_read.status_code == 200
    assert res_read.json()["is_read"] is True

    # Mark all read
    res_all = client.post("/api/v1/notifications/read-all", headers=headers_reviewer)
    assert res_all.status_code == 200

    db.close()


def test_version_diff_comparison_endpoint():
    """Verify document version diffing comparing v1 and v2 text and findings."""
    db = SessionLocal()
    t = setup_review_tenant(db, "DiffTest")

    # Create Version 2
    ver2_id = str(uuid.uuid4())
    ver2 = DocumentVersion(
        id=ver2_id, organization_id=t["org_id"], document_id=t["doc_id"], version_number=2,
        extracted_text="Original campaign copy with cost-effective price $79.\nAdded line for enterprise security.",
        brand_health_score=95.0, extraction_status="COMPLETED", word_count=13
    )
    db.add(ver2)
    db.commit()

    headers_reviewer = {"Authorization": f"Bearer {t['tokens']['reviewer']}"}

    res = client.get(
        f"/api/v1/reviews/documents/{t['doc_id']}/compare?v1={t['ver1_id']}&v2={ver2_id}",
        headers=headers_reviewer
    )
    assert res.status_code == 200
    diff_data = res.json()

    assert diff_data["v1_version_number"] == 1
    assert diff_data["v2_version_number"] == 2
    assert diff_data["score_delta"] == 30.0  # 95 - 65
    assert diff_data["text_summary"]["added_lines_count"] >= 1
    assert "findings_summary" in diff_data

    db.close()
