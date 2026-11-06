"""
tests/test_constitution.py
Automated acceptance test suite for BrandGuard Phase 3: Brand Constitution & Fact Registry.
Validates:
1. Authorized users can create and edit draft brand rules.
2. Unauthorized users cannot approve rules (RBAC).
3. Approved rules are visible as active and have approved_by populated.
4. Pending or rejected rules are not treated as active.
5. Users can create, update, and search facts.
6. Expired facts are correctly identified and distinguished.
7. Conflicting facts are surfaced and preserved rather than silently overwritten.
8. Term Bank supports preferred and prohibited terms.
9. Authorized users can upload and manage brand assets.
10. Invalid file extensions are rejected.
11. Users cannot access another organisation's Constitution data (Multi-tenant isolation).
12. Important changes are recorded in the audit log.
"""
import io
import uuid
from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.constitution import RuleCategory, EntityStatus
from app.models.audit import AuditLog

client = TestClient(app)


def _unique_slug(prefix: str = "const") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _create_org_and_tokens(role: str = "ADMIN") -> dict:
    slug = _unique_slug()
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": f"Org {slug}",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin",
    }).json()
    admin_token = boot["access_token"]
    org_id = boot["user"]["organization_id"]

    if role == "ADMIN":
        return {"token": admin_token, "org_id": org_id, "user_id": boot["user"]["id"]}

    # Provision user with target role
    member_email = f"mem_{role.lower()}_{uuid.uuid4().hex[:4]}@example.com"
    member = client.post(
        "/api/v1/users",
        json={
            "email": member_email,
            "password": "Password123!",
            "full_name": f"{role} Member",
            "role": role,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    user_token = client.post("/api/v1/auth/login", json={
        "email": member_email,
        "password": "Password123!",
        "organization_id": org_id,
    }).json()["access_token"]

    return {"token": user_token, "admin_token": admin_token, "org_id": org_id, "user_id": member["id"]}


# ---------------------------------------------------------------------------
# 1. Brand Rules Acceptance Tests
# ---------------------------------------------------------------------------

def test_create_and_edit_draft_brand_rule(db_session: Session):
    session = _create_org_and_tokens("ADMIN")
    headers = {"Authorization": f"Bearer {session['token']}"}

    # 1. Create draft rule
    create_res = client.post(
        "/api/v1/constitution/rules",
        json={
            "rule_code": "TONE-01",
            "category": "TONE_VOICE",
            "title": "Clear and Direct Voice",
            "description": "Never use buzzwords without clear technical explanation.",
            "examples_positive": ["Our Kubernetes cluster self-heals in 2 seconds."],
            "examples_negative": ["We have synergy-driven cloud magic."],
            "status": "DRAFT",
        },
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    rule_data = create_res.json()
    assert rule_data["rule_code"] == "TONE-01"
    assert rule_data["status"] == "DRAFT"
    rule_id = rule_data["id"]

    # 2. Edit draft rule
    edit_res = client.put(
        f"/api/v1/constitution/rules/{rule_id}",
        json={"title": "Clear, Confident, and Direct Voice"},
        headers=headers,
    )
    assert edit_res.status_code == 200
    assert edit_res.json()["title"] == "Clear, Confident, and Direct Voice"

    # Verify audit log was written
    audit = db_session.query(AuditLog).filter(
        AuditLog.target_id == uuid.UUID(rule_id),
        AuditLog.action == "RULE_CREATED",
    ).first()
    assert audit is not None


def test_unauthorized_user_cannot_approve_rule():
    """
    Requirement 2: Non-admin/non-brand-manager cannot approve rules.
    """
    session = _create_org_and_tokens("CONTENT_CREATOR")
    creator_headers = {"Authorization": f"Bearer {session['token']}"}
    admin_headers = {"Authorization": f"Bearer {session['admin_token']}"}

    # Creator creates rule
    rule = client.post(
        "/api/v1/constitution/rules",
        json={
            "rule_code": "STYLE-10",
            "category": "WRITING_STYLE",
            "title": "Active Voice Rule",
            "description": "Write in active voice.",
        },
        headers=creator_headers,
    ).json()

    # Creator submits rule
    submit_res = client.post(f"/api/v1/constitution/rules/{rule['id']}/submit", headers=creator_headers)
    assert submit_res.status_code == 200
    assert submit_res.json()["status"] == "PENDING_APPROVAL"

    # Creator tries to APPROVE: MUST BE REJECTED WITH 403 FORBIDDEN
    approve_res_hack = client.post(f"/api/v1/constitution/rules/{rule['id']}/approve", headers=creator_headers)
    assert approve_res_hack.status_code == 403

    # Admin approves: SUCCEEDS
    approve_res_admin = client.post(f"/api/v1/constitution/rules/{rule['id']}/approve", headers=admin_headers)
    assert approve_res_admin.status_code == 200
    assert approve_res_admin.json()["status"] == "ACTIVE"
    assert approve_res_admin.json()["approved_by"] is not None


def test_approved_and_pending_rules_filtered():
    session = _create_org_and_tokens("ADMIN")
    headers = {"Authorization": f"Bearer {session['token']}"}

    # Create one draft rule, one active rule
    client.post("/api/v1/constitution/rules", json={
        "rule_code": "R-DRAFT", "category": "VISUAL", "title": "Draft Visual", "description": "D", "status": "DRAFT",
    }, headers=headers)

    client.post("/api/v1/constitution/rules", json={
        "rule_code": "R-ACTIVE", "category": "VISUAL", "title": "Active Visual", "description": "A", "status": "ACTIVE",
    }, headers=headers)

    # Filter by ACTIVE only
    res = client.get("/api/v1/constitution/rules?status_filter=ACTIVE", headers=headers)
    assert res.status_code == 200
    codes = [r["rule_code"] for r in res.json()]
    assert "R-ACTIVE" in codes
    assert "R-DRAFT" not in codes


# ---------------------------------------------------------------------------
# 2. Fact Registry Acceptance Tests
# ---------------------------------------------------------------------------

def test_fact_creation_search_and_expiration(db_session: Session):
    session = _create_org_and_tokens("ADMIN")
    headers = {"Authorization": f"Bearer {session['token']}"}

    # 1. Create a current approved fact
    client.post("/api/v1/constitution/facts", json={
        "fact_code": "FACT-UCC-01",
        "claim_type": "Throughput",
        "statement": "ApexCloud processes 50,000 requests per second.",
        "numerical_value": 50000,
        "unit": "req/sec",
        "source_reference": "Benchmark Report 2026",
        "fact_owner": "Lead Infrastructure Architect",
        "expiry_date": (date.today() + timedelta(days=365)).isoformat(),
        "status": "ACTIVE",
    }, headers=headers)

    # 2. Create an EXPIRED fact (past expiry date)
    client.post("/api/v1/constitution/facts", json={
        "fact_code": "FACT-OLD-02",
        "claim_type": "Legacy Pricing",
        "statement": "ApexCloud 2020 Beta tier was $10/month.",
        "numerical_value": 10,
        "unit": "USD/mo",
        "source_reference": "Deprecated 2020 Tariff",
        "fact_owner": "Marketing",
        "expiry_date": (date.today() - timedelta(days=30)).isoformat(),
        "status": "ACTIVE",
    }, headers=headers)

    # Search facts for 'requests'
    search_res = client.get("/api/v1/constitution/facts?search=requests", headers=headers)
    assert search_res.status_code == 200
    results = search_res.json()
    assert len(results) == 1
    assert results[0]["fact_code"] == "FACT-UCC-01"
    assert results[0]["is_expired"] is False

    # Check expired fact list
    all_facts = client.get("/api/v1/constitution/facts", headers=headers).json()
    old_fact = next(f for f in all_facts if f["fact_code"] == "FACT-OLD-02")
    assert old_fact["is_expired"] is True
    assert old_fact["status"] == "EXPIRED"


def test_conflicting_facts_detection():
    """
    Requirement 7: Contradictory facts on the same claim type are surfaced.
    """
    session = _create_org_and_tokens("ADMIN")
    headers = {"Authorization": f"Bearer {session['token']}"}

    # Create two facts with identical claim_type but different numerical values
    client.post("/api/v1/constitution/facts", json={
        "fact_code": "FACT-SLA-A",
        "claim_type": "SLA Uptime",
        "statement": "Uptime guarantee is 99.9%.",
        "numerical_value": 99.9,
        "unit": "percent",
        "source_reference": "Ref A",
        "fact_owner": "Owner A",
        "expiry_date": (date.today() + timedelta(days=100)).isoformat(),
        "status": "ACTIVE",
    }, headers=headers)

    client.post("/api/v1/constitution/facts", json={
        "fact_code": "FACT-SLA-B",
        "claim_type": "SLA Uptime",
        "statement": "Uptime guarantee is 99.99%.",
        "numerical_value": 99.99,
        "unit": "percent",
        "source_reference": "Ref B",
        "fact_owner": "Owner B",
        "expiry_date": (date.today() + timedelta(days=100)).isoformat(),
        "status": "ACTIVE",
    }, headers=headers)

    # Detect conflicts endpoint
    conflict_res = client.get("/api/v1/constitution/facts/conflicts/detect", headers=headers)
    assert conflict_res.status_code == 200
    conflicts = conflict_res.json()
    assert len(conflicts) >= 1
    sla_conflict = next(c for c in conflicts if c["claim_type"] == "sla uptime")
    assert len(sla_conflict["conflicting_facts"]) == 2
    assert "conflicting numerical values" in sla_conflict["conflict_reason"]


# ---------------------------------------------------------------------------
# 3. Term Bank Acceptance Tests
# ---------------------------------------------------------------------------

def test_term_bank_prohibited_and_preferred():
    session = _create_org_and_tokens("ADMIN")
    headers = {"Authorization": f"Bearer {session['token']}"}

    create_res = client.post(
        "/api/v1/constitution/terms",
        json={
            "term_code": "TERM-SEC-01",
            "prohibited_term": "100% unhackable",
            "preferred_term": "defense-in-depth zero-trust architecture",
            "usage_context": "Never claim absolute immunity to attacks; highlight security architecture.",
            "is_case_sensitive": False,
            "status": "ACTIVE",
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    term_data = create_res.json()
    assert term_data["prohibited_term"] == "100% unhackable"
    assert term_data["preferred_term"] == "defense-in-depth zero-trust architecture"

    # Search term
    search_res = client.get("/api/v1/constitution/terms?search=unhackable", headers=headers)
    assert search_res.status_code == 200
    assert len(search_res.json()) == 1


# ---------------------------------------------------------------------------
# 4. Brand Asset Management & Safe Upload
# ---------------------------------------------------------------------------

def test_brand_assets_specification_and_file_upload():
    session = _create_org_and_tokens("ADMIN")
    headers = {"Authorization": f"Bearer {session['token']}"}

    # 1. Create brand color token
    color_res = client.post(
        "/api/v1/constitution/assets",
        json={
            "asset_code": "COLOR-NAVY",
            "asset_type": "COLOR",
            "name": "Apex Navy",
            "specifications": {"hex": "#0F172A", "usage": "Executive Header Background"},
            "status": "ACTIVE",
        },
        headers=headers,
    )
    assert color_res.status_code == 201
    assert color_res.json()["specifications"]["hex"] == "#0F172A"

    # 2. Upload valid PNG image asset
    file_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    upload_res = client.post(
        "/api/v1/constitution/assets/upload",
        data={"asset_code": "LOGO-MAIN", "asset_type": "LOGO", "name": "Primary Wordmark"},
        files={"file": ("logo.png", io.BytesIO(file_bytes), "image/png")},
        headers=headers,
    )
    assert upload_res.status_code == 201
    asset_data = upload_res.json()
    assert asset_data["asset_code"] == "LOGO-MAIN"
    assert asset_data["file_path"] is not None

    # 3. Upload disallowed file extension (.exe): MUST BE REJECTED with 400
    bad_upload = client.post(
        "/api/v1/constitution/assets/upload",
        data={"asset_code": "MALICIOUS", "asset_type": "FILE", "name": "Executable"},
        files={"file": ("malware.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
        headers=headers,
    )
    assert bad_upload.status_code == 400
    assert "not permitted" in bad_upload.text


# ---------------------------------------------------------------------------
# 5. Multi-Tenant Isolation for Constitution Entities
# ---------------------------------------------------------------------------

def test_cross_tenant_constitution_isolation():
    session_a = _create_org_and_tokens("ADMIN")
    session_b = _create_org_and_tokens("ADMIN")

    headers_a = {"Authorization": f"Bearer {session_a['token']}"}
    headers_b = {"Authorization": f"Bearer {session_b['token']}"}

    # Tenant A creates rule
    rule_a = client.post("/api/v1/constitution/rules", json={
        "rule_code": "A-RULE-01", "category": "TONE_VOICE", "title": "Tenant A Secret Rule", "description": "Secret A",
    }, headers=headers_a).json()

    # Tenant B lists rules: MUST NOT see Tenant A's rule
    rules_b = client.get("/api/v1/constitution/rules", headers=headers_b).json()
    b_codes = [r["rule_code"] for r in rules_b]
    assert "A-RULE-01" not in b_codes

    # Tenant B direct GET rule by ID: MUST RETURN 404
    assert client.get(f"/api/v1/constitution/rules/{rule_a['id']}", headers=headers_b).status_code == 404


# ---------------------------------------------------------------------------
# 6. Constitution Overview Metrics & Demo Seeder
# ---------------------------------------------------------------------------

def test_constitution_overview_and_seed_demo():
    session = _create_org_and_tokens("ADMIN")
    headers = {"Authorization": f"Bearer {session['token']}"}

    # Seed demo data
    seed_res = client.post("/api/v1/constitution/seed-demo", headers=headers)
    assert seed_res.status_code == 200

    # Query overview
    overview_res = client.get("/api/v1/constitution/overview", headers=headers)
    assert overview_res.status_code == 200
    data = overview_res.json()
    assert data["total_rules"] >= 4
    assert data["approved_rules"] >= 4
    assert data["total_facts"] >= 4
    assert data["expired_facts"] >= 1  # FACT-EXPIRED-LEGACY
    assert data["total_terms"] >= 3
    assert data["total_assets"] >= 3

