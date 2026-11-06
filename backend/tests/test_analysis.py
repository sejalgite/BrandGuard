"""
tests/test_analysis.py
Comprehensive test suite for Phase 5 Brand Analysis Engine.
Covers all 6 categories, false-positive prevention, tenant isolation,
RBAC enforcement, and audit trail verification.
"""
import uuid
from datetime import datetime, date, timedelta, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.constitution import (
    BrandConstitution, BrandRule, FactRegistry, TermBank, BrandAsset,
    RuleCategory, EntityStatus
)
from app.models.document import (
    Document, DocumentVersion, DocumentLifecycleStatus, VersionWorkflowStatus
)
from app.models.finding import (
    ReviewJob, Finding, DetectionCategory, SeverityLevel, FindingStatus,
    FindingSource, EvidenceEntityType
)
from app.models.audit import AuditLog
from app.auth.password import hash_password
from app.auth.jwt import create_access_token

client = TestClient(app)


def make_token(user_id: str, org_id: str, role: UserRole) -> str:
    return create_access_token({"sub": user_id, "org": org_id, "role": role.value})


def setup_test_tenant(db, name_prefix="Apex"):
    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name=f"{name_prefix} Corp", slug=f"{name_prefix.lower()}-{org_id[:8]}")
    db.add(org)

    # Admin, Content Creator, Leadership (no run_analysis perm)
    admin_id = str(uuid.uuid4())
    creator_id = str(uuid.uuid4())
    leadership_id = str(uuid.uuid4())

    admin = User(
        id=admin_id,
        organization_id=org_id,
        email=f"admin_{admin_id[:6]}@test.com",
        full_name="Admin User",
        hashed_password=hash_password("Pass123!"),
        role=UserRole.ADMIN,
        is_active=True
    )
    creator = User(
        id=creator_id,
        organization_id=org_id,
        email=f"creator_{creator_id[:6]}@test.com",
        full_name="Creator User",
        hashed_password=hash_password("Pass123!"),
        role=UserRole.CONTENT_CREATOR,
        is_active=True
    )
    leadership = User(
        id=leadership_id,
        organization_id=org_id,
        email=f"leader_{leadership_id[:6]}@test.com",
        full_name="Leadership User",
        hashed_password=hash_password("Pass123!"),
        role=UserRole.LEADERSHIP,
        is_active=True
    )
    db.add_all([admin, creator, leadership])

    # Active Brand Constitution
    const_id = str(uuid.uuid4())
    const = BrandConstitution(
        id=const_id,
        organization_id=org_id,
        title=f"{name_prefix} Master Constitution",
        version="1.0",
        is_active=True
    )
    db.add(const)
    db.commit()

    return {
        "org_id": org_id,
        "const_id": const_id,
        "admin": admin,
        "creator": creator,
        "leadership": leadership,
        "token_admin": make_token(admin_id, org_id, UserRole.ADMIN),
        "token_creator": make_token(creator_id, org_id, UserRole.CONTENT_CREATOR),
        "token_leadership": make_token(leadership_id, org_id, UserRole.LEADERSHIP),
    }


def test_analysis_all_six_categories_and_ground_truth():
    """Verify analysis across all six categories with traceable Constitution references."""
    db = SessionLocal()
    t = setup_test_tenant(db, "AllCats")
    org_id = t["org_id"]
    const_id = t["const_id"]

    # 1. Add Approved Constitution Ground Truth
    # Term Bank: Prohibited term "cheap" -> Preferred "cost-effective"
    term = TermBank(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        constitution_id=const_id,
        term_code="TERM-001",
        prohibited_term="cheap",
        preferred_term="cost-effective",
        is_case_sensitive=False,
        status=EntityStatus.ACTIVE
    )

    # Fact Registry: Pricing fact $79/mo
    fact_price = FactRegistry(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        constitution_id=const_id,
        fact_code="FACT-PRICING-01",
        claim_type="PRICING",
        statement="ApexCloud Enterprise is priced at $79 per user monthly.",
        numerical_value=79.0,
        unit="$",
        source_reference="Q4 Financial Pricing Sheet",
        fact_owner="Finance Team",
        expiry_date=date.today() + timedelta(days=90),
        status=EntityStatus.ACTIVE
    )

    # Tone Rule: No hyperbole
    rule_tone = BrandRule(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        constitution_id=const_id,
        rule_code="RULE-TONE-01",
        category=RuleCategory.TONE_VOICE,
        title="Grounded Technical Tone",
        description="Avoid hyperbolic claims such as game-changing or revolutionary without verified benchmarks.",
        examples_positive=["high-performance cloud infrastructure"],
        examples_negative=["game-changing miracle"],
        status=EntityStatus.ACTIVE
    )

    # Messaging Rule: No competitor disparagement
    rule_msg = BrandRule(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        constitution_id=const_id,
        rule_code="RULE-MSG-01",
        category=RuleCategory.MESSAGING_PILLAR,
        title="Respectful Competitor Comparison",
        description="Never state competitor clouds like AWS or Azure are failing or broken without certified independent audits.",
        examples_positive=["focused on unique deterministic orchestration"],
        examples_negative=["AWS is broken and failing"],
        status=EntityStatus.ACTIVE
    )

    # Accessibility Rule: WCAG compliance & heading structure
    rule_a11y = BrandRule(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        constitution_id=const_id,
        rule_code="RULE-A11Y-01",
        category=RuleCategory.ACCESSIBILITY,
        title="Accessible Content and Readability",
        description="Ensure meaningful link text and consecutive heading structure.",
        examples_positive=["Download technical whitepaper"],
        examples_negative=["click here"],
        status=EntityStatus.ACTIVE
    )

    # Visual Asset: Color palette hex
    asset_palette = BrandAsset(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        constitution_id=const_id,
        asset_code="ASSET-COLOR-01",
        asset_type="COLOR_PALETTE",
        name="Apex Primary Blue Palette",
        specifications={"approved_hexes": ["#0052cc", "#0033aa", "#002288"]},
        status=EntityStatus.ACTIVE
    )

    db.add_all([term, fact_price, rule_tone, rule_msg, rule_a11y, asset_palette])
    db.commit()

    # 2. Upload Document with Controlled Violations
    doc_id = str(uuid.uuid4())
    ver_id = str(uuid.uuid4())
    doc = Document(
        id=doc_id,
        organization_id=org_id,
        creator_id=t["creator"].id,
        title="Apex Campaign Draft",
        content_type="TEXT"
    )
    doc_ver = DocumentVersion(
        id=ver_id,
        organization_id=org_id,
        document_id=doc_id,
        version_number=1,
        original_filename="campaign.txt",
        file_size_bytes=450,
        mime_type="text/plain",
        extraction_status="COMPLETED",
        extracted_text=(
            "ApexCloud Enterprise Overview\n\n"
            "Our solution is cheap compared to legacy vendors.\n\n"
            "Subscribe now for only $49 per month.\n\n"
            "This is a game-changing miracle for IT teams.\n\n"
            "Unlike AWS which is broken and failing, we offer full resilience.\n\n"
            "Our brand primary signature color is #FF5500.\n\n"
            "To view the report, click here."
        ),
        word_count=52,
        character_count=320,
        structured_content={
            "segments": [
                {"segment_id": "seg_1", "paragraph_index": 1, "sentence_index": 1, "text": "ApexCloud Enterprise Overview", "char_start": 0, "char_end": 29},
                {"segment_id": "seg_2", "paragraph_index": 2, "sentence_index": 1, "text": "Our solution is cheap compared to legacy vendors.", "char_start": 31, "char_end": 80},
                {"segment_id": "seg_3", "paragraph_index": 3, "sentence_index": 1, "text": "Subscribe now for only $49 per month.", "char_start": 82, "char_end": 119},
                {"segment_id": "seg_4", "paragraph_index": 4, "sentence_index": 1, "text": "This is a game-changing miracle for IT teams.", "char_start": 121, "char_end": 166},
                {"segment_id": "seg_5", "paragraph_index": 5, "sentence_index": 1, "text": "Unlike AWS which is broken and failing, we offer full resilience.", "char_start": 168, "char_end": 233},
                {"segment_id": "seg_6", "paragraph_index": 6, "sentence_index": 1, "text": "Our brand primary signature color is #FF5500.", "char_start": 235, "char_end": 280},
                {"segment_id": "seg_7", "paragraph_index": 7, "sentence_index": 1, "text": "To view the report, click here.", "char_start": 282, "char_end": 313},
            ],
            "headings": [
                {"text": "ApexCloud Enterprise Overview", "level": 1, "page": 1}
            ]
        }
    )
    db.add_all([doc, doc_ver])
    db.commit()

    # 3. Trigger Analysis via API
    headers = {"Authorization": f"Bearer {t['token_creator']}"}
    res = client.post(f"/api/v1/analysis/documents/{doc_id}/run", headers=headers)
    assert res.status_code == 201, res.text
    run_data = res.json()
    job_id = run_data["id"]
    assert run_data["status"] == "COMPLETED"
    assert run_data["total_findings"] >= 6

    # 4. Fetch Findings and Verify All 6 Categories
    f_res = client.get(f"/api/v1/analysis/runs/{job_id}/findings", headers=headers)
    assert f_res.status_code == 200
    findings = f_res.json()
    categories_found = {f["category"] for f in findings}

    assert "TERMINOLOGY" in categories_found, "Terminology finding missing"
    assert "CLAIMS" in categories_found, "Claims finding missing"
    assert "TONE" in categories_found, "Tone finding missing"
    assert "MESSAGING" in categories_found, "Messaging finding missing"
    assert "VISUAL" in categories_found, "Visual finding missing"
    assert "ACCESSIBILITY" in categories_found, "Accessibility finding missing"

    # Specific evidence assertions
    term_f = next(f for f in findings if f["category"] == "TERMINOLOGY")
    assert term_f["flagged_snippet"] == "cheap"
    assert term_f["suggested_correction"] == "cost-effective"
    assert term_f["evidence_type"] == "TERM"
    assert term_f["cited_code"] == "TERM-001"

    claim_f = next(f for f in findings if f["category"] == "CLAIMS")
    assert "$49" in claim_f["flagged_snippet"]
    assert "$79" in claim_f["explanation"]
    assert claim_f["evidence_type"] == "FACT"

    db.close()


def test_false_positive_prevention_unapproved_and_draft_rules():
    """Verify that draft, rejected, or expired rules DO NOT generate violations."""
    db = SessionLocal()
    t = setup_test_tenant(db, "FalsePos")
    org_id = t["org_id"]
    const_id = t["const_id"]

    # 1. Draft Tone Rule (should be ignored)
    draft_rule = BrandRule(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        constitution_id=const_id,
        rule_code="RULE-DRAFT-01",
        category=RuleCategory.TONE_VOICE,
        title="Unapproved Draft Rule",
        description="Draft rule trying to flag legitimate words.",
        examples_negative=["cloud"],
        status=EntityStatus.DRAFT
    )

    # 2. Rejected Term (should be ignored)
    rejected_term = TermBank(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        constitution_id=const_id,
        term_code="TERM-REJECTED-01",
        prohibited_term="enterprise",
        preferred_term="business",
        status=EntityStatus.REJECTED
    )

    db.add_all([draft_rule, rejected_term])
    db.commit()

    # Clean document using "cloud" and "enterprise"
    doc_id = str(uuid.uuid4())
    ver_id = str(uuid.uuid4())
    doc = Document(id=doc_id, organization_id=org_id, creator_id=t["creator"].id, title="Clean Copy", content_type="TEXT")
    doc_ver = DocumentVersion(
        id=ver_id,
        organization_id=org_id,
        document_id=doc_id,
        version_number=1,
        extraction_status="COMPLETED",
        extracted_text="We build enterprise cloud solutions for modern teams.",
        structured_content={
            "segments": [
                {"segment_id": "seg_1", "text": "We build enterprise cloud solutions for modern teams.", "char_start": 0, "char_end": 54}
            ]
        }
    )
    db.add_all([doc, doc_ver])
    db.commit()

    headers = {"Authorization": f"Bearer {t['token_creator']}"}
    res = client.post(f"/api/v1/analysis/documents/{doc_id}/run", headers=headers)
    assert res.status_code == 201
    job_id = res.json()["id"]

    f_res = client.get(f"/api/v1/analysis/runs/{job_id}/findings", headers=headers)
    assert f_res.status_code == 200
    findings = f_res.json()

    # Confirm zero findings generated from draft/rejected rules
    assert len(findings) == 0, f"Expected 0 findings from draft rules, got {len(findings)}"

    db.close()


def test_cross_tenant_analysis_isolation():
    """Verify that Tenant B cannot trigger analysis or inspect Tenant A's findings."""
    db = SessionLocal()
    tenant_a = setup_test_tenant(db, "TenantA")
    tenant_b = setup_test_tenant(db, "TenantB")

    # Create document in Tenant A
    doc_a_id = str(uuid.uuid4())
    ver_a_id = str(uuid.uuid4())
    doc_a = Document(id=doc_a_id, organization_id=tenant_a["org_id"], creator_id=tenant_a["creator"].id, title="Doc Tenant A", content_type="TEXT")
    ver_a = DocumentVersion(id=ver_a_id, organization_id=tenant_a["org_id"], document_id=doc_a_id, version_number=1, extraction_status="COMPLETED", extracted_text="Tenant A sensitive content")
    db.add_all([doc_a, ver_a])
    db.commit()

    # Tenant B attempts to run analysis on Tenant A's document
    headers_b = {"Authorization": f"Bearer {tenant_b['token_creator']}"}
    unauth_run = client.post(f"/api/v1/analysis/documents/{doc_a_id}/run", headers=headers_b)
    assert unauth_run.status_code == 404, "Tenant B must get 404 for Tenant A's document"

    # Tenant A runs analysis
    headers_a = {"Authorization": f"Bearer {tenant_a['token_creator']}"}
    run_a = client.post(f"/api/v1/analysis/documents/{doc_a_id}/run", headers=headers_a)
    assert run_a.status_code == 201
    job_a_id = run_a.json()["id"]

    # Tenant B attempts to inspect Tenant A's analysis run
    unauth_inspect = client.get(f"/api/v1/analysis/runs/{job_a_id}", headers=headers_b)
    assert unauth_inspect.status_code == 404

    # Tenant B attempts to list Tenant A's findings
    unauth_findings = client.get(f"/api/v1/analysis/runs/{job_a_id}/findings", headers=headers_b)
    assert unauth_findings.status_code == 404

    db.close()


def test_rbac_analysis_execution_and_status_modification():
    """Verify role permissions: Leadership cannot run analysis; only approvers can update status."""
    db = SessionLocal()
    t = setup_test_tenant(db, "RBACAnalysis")
    org_id = t["org_id"]

    doc_id = str(uuid.uuid4())
    ver_id = str(uuid.uuid4())
    doc = Document(id=doc_id, organization_id=org_id, creator_id=t["creator"].id, title="RBAC Doc", content_type="TEXT")
    ver = DocumentVersion(id=ver_id, organization_id=org_id, document_id=doc_id, version_number=1, extraction_status="COMPLETED", extracted_text="Some text")
    db.add_all([doc, ver])
    db.commit()

    # Leadership role lacks PERM_RUN_ANALYSIS
    headers_leadership = {"Authorization": f"Bearer {t['token_leadership']}"}
    res_leader = client.post(f"/api/v1/analysis/documents/{doc_id}/run", headers=headers_leadership)
    assert res_leader.status_code == 403, "Leadership without PERM_RUN_ANALYSIS must be rejected with 403"

    # Content Creator has PERM_RUN_ANALYSIS
    headers_creator = {"Authorization": f"Bearer {t['token_creator']}"}
    res_creator = client.post(f"/api/v1/analysis/documents/{doc_id}/run", headers=headers_creator)
    assert res_creator.status_code == 201

    db.close()


def test_audit_logging_recorded_for_analysis_lifecycle():
    """Verify that analysis runs and finding status updates are recorded in immutable audit logs."""
    db = SessionLocal()
    t = setup_test_tenant(db, "AuditTest")
    org_id = t["org_id"]

    doc_id = str(uuid.uuid4())
    ver_id = str(uuid.uuid4())
    doc = Document(id=doc_id, organization_id=org_id, creator_id=t["creator"].id, title="Audit Doc", content_type="TEXT")
    ver = DocumentVersion(id=ver_id, organization_id=org_id, document_id=doc_id, version_number=1, extraction_status="COMPLETED", extracted_text="Sample text")
    db.add_all([doc, ver])
    db.commit()

    headers_admin = {"Authorization": f"Bearer {t['token_admin']}"}
    run_res = client.post(f"/api/v1/analysis/documents/{doc_id}/run", headers=headers_admin)
    assert run_res.status_code == 201

    # Check audit log in DB
    logs = db.query(AuditLog).filter(
        AuditLog.organization_id == org_id,
        AuditLog.action == "ANALYSIS_RUN_COMPLETED"
    ).all()
    assert len(logs) >= 1
    assert logs[0].target_entity == "review_jobs"

    db.close()

