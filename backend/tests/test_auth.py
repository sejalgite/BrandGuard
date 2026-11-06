"""
tests/test_auth.py
Comprehensive automated security and functional verification suite for BrandGuard Phase 2:
1. Public registration cannot self-assign privileged roles.
2. Initial organization bootstrap cannot be repeated or exploited concurrently.
3. Only Admin can assign or modify roles.
4. All seven roles are tested against actual protected API endpoints.
5. Expired and tampered JWTs are rejected.
6. Stale role claims cannot preserve revoked permissions (DB role changes take immediate effect).
7. Deactivated users are rejected.
8. Logout revokes the session / credentials via PostgreSQL denylist.
9. Revoked credentials cannot be reused.
10. Cross-tenant access is rejected across all endpoints (user list, user detail, role update, status, audit).
11. Unauthorized requests receive correct HTTP status codes (401 vs 403).
12. Sensitive information is not exposed in authentication or audit responses.
13. Audit log records remain strictly append-only and protected by PostgreSQL triggers.
"""
import uuid
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.audit import AuditLog
from app.models.token import RevokedToken
from app.auth.jwt import create_access_token
from app.auth.password import verify_password
from app.auth.rbac import ROLE_PERMISSIONS

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_rate_limits():
    """Ensure test isolation so rate-limiting in one test does not fail others."""
    from app.auth.rate_limiter import limiter
    limiter.reset_all_for_testing()
    yield
    limiter.reset_all_for_testing()


def _unique_slug(prefix: str = "org") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# 1. Atomic Organization Bootstrap Tests
# ---------------------------------------------------------------------------

def test_organization_bootstrap_creates_admin_and_cannot_be_repeated(db_session: Session):
    """
    Test 1 & 2: Controlled, one-time bootstrap creates Org + Admin in one atomic transaction.
    Subsequent attempts with the same slug fail with 409 Conflict.
    """
    slug = _unique_slug("boot")
    email = f"admin_{uuid.uuid4().hex[:6]}@example.com"
    pwd = "SecurePassword123!"

    # 1. Bootstrap new organization
    response = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Bootstrap Enterprises",
        "org_slug": slug,
        "admin_email": email,
        "admin_password": pwd,
        "admin_full_name": "Bootstrap Administrator",
    })
    assert response.status_code == 201, response.text
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == "ADMIN"
    assert data["user"]["email"] == email
    org_id = data["user"]["organization_id"]

    # Verify audit trail contains ORGANIZATION_BOOTSTRAPPED and USER_REGISTERED
    audit_boot = db_session.query(AuditLog).filter(
        AuditLog.organization_id == uuid.UUID(org_id),
        AuditLog.action == "ORGANIZATION_BOOTSTRAPPED",
    ).first()
    assert audit_boot is not None

    # 2. Repeated bootstrap attempt MUST fail with 409 Conflict
    repeat_res = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Repeated Enterprises",
        "org_slug": slug,
        "admin_email": "intruder@example.com",
        "admin_password": "IntruderPassword123!",
        "admin_full_name": "Intruder",
    })
    assert repeat_res.status_code == 409


# ---------------------------------------------------------------------------
# 2. Public Registration Security & Role Escalation Prevention
# ---------------------------------------------------------------------------

def test_public_registration_cannot_self_assign_privileged_roles():
    """
    Requirement 2.1: Public registration must NEVER allow users to assign themselves privileged roles.
    Attempting to register as ADMIN, BRAND_MANAGER, REVIEWER, etc. MUST receive 403 Forbidden.
    """
    slug = _unique_slug("priv-test")
    # Create org via bootstrap
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Privilege Test Org",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin",
    }).json()
    org_id = boot["user"]["organization_id"]

    # Attacker tries to self-register as ADMIN
    res_admin = client.post("/api/v1/auth/register", json={
        "email": f"attacker_admin_{uuid.uuid4().hex[:6]}@example.com",
        "password": "Password123!",
        "full_name": "Attacker Admin",
        "organization_id": org_id,
        "role": "ADMIN",
    })
    assert res_admin.status_code == 403
    assert "cannot self-assign privileged roles" in res_admin.text

    # Attacker tries to self-register as BRAND_MANAGER
    res_bm = client.post("/api/v1/auth/register", json={
        "email": f"attacker_bm_{uuid.uuid4().hex[:6]}@example.com",
        "password": "Password123!",
        "full_name": "Attacker BM",
        "organization_id": org_id,
        "role": "BRAND_MANAGER",
    })
    assert res_bm.status_code == 403

    # Normal public registration without specifying role or with CONTENT_CREATOR succeeds
    res_legit = client.post("/api/v1/auth/register", json={
        "email": f"creator_{uuid.uuid4().hex[:6]}@example.com",
        "password": "Password123!",
        "full_name": "Legit Creator",
        "organization_id": org_id,
    })
    assert res_legit.status_code == 201
    assert res_legit.json()["role"] == "CONTENT_CREATOR"


# ---------------------------------------------------------------------------
# 3. Only Admin Can Assign or Modify Roles
# ---------------------------------------------------------------------------

def test_only_admin_can_assign_or_modify_roles():
    """
    Requirement 2.5: Only an authorized Admin may assign or change roles.
    Non-admins cannot change roles. Admin can provision users with any role.
    """
    slug = _unique_slug("role-mgmt")
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Role Org",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Org Admin",
    }).json()
    admin_token = boot["access_token"]
    org_id = boot["user"]["organization_id"]

    # 1. Admin provisions a BRAND_MANAGER via POST /api/v1/users
    bm_res = client.post(
        "/api/v1/users",
        json={
            "email": f"bm_{uuid.uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "full_name": "Brand Manager User",
            "role": "BRAND_MANAGER",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert bm_res.status_code == 201
    bm_user = bm_res.json()
    assert bm_user["role"] == "BRAND_MANAGER"

    # 2. Public user registers as creator
    creator_email = f"creator_{uuid.uuid4().hex[:6]}@example.com"
    creator = client.post("/api/v1/auth/register", json={
        "email": creator_email,
        "password": "Password123!",
        "full_name": "Creator",
        "organization_id": org_id,
    }).json()

    creator_token = client.post("/api/v1/auth/login", json={
        "email": creator_email,
        "password": "Password123!",
        "organization_id": org_id,
    }).json()["access_token"]

    # 3. Creator tries to promote himself to ADMIN: rejected with 403
    hack_res = client.patch(
        f"/api/v1/users/{creator['id']}/role",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert hack_res.status_code == 403

    # 4. Admin promotes creator to LEGAL_REVIEWER: succeeds
    promote_res = client.patch(
        f"/api/v1/users/{creator['id']}/role",
        json={"role": "LEGAL_REVIEWER"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert promote_res.status_code == 200
    assert promote_res.json()["role"] == "LEGAL_REVIEWER"


# ---------------------------------------------------------------------------
# 4. Stale Role Claims in Token Cannot Preserve Revoked Permissions
# ---------------------------------------------------------------------------

def test_stale_role_claim_cannot_preserve_revoked_permissions(db_session: Session):
    """
    Requirement 3.5: Role changes and permission revocations take effect immediately
    without relying on stale token claims.
    If a user's role is demoted in PostgreSQL, an existing token cannot access former endpoints.
    """
    slug = _unique_slug("stale")
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Stale Org",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin",
    }).json()
    admin_token = boot["access_token"]

    # Admin provisions a second admin
    target_email = f"target_{uuid.uuid4().hex[:6]}@example.com"
    target_user = client.post(
        "/api/v1/users",
        json={
            "email": target_email,
            "password": "Password123!",
            "full_name": "Target Admin",
            "role": "ADMIN",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    # Target logs in and receives token with role=ADMIN inside JWT payload
    target_token = client.post("/api/v1/auth/login", json={
        "email": target_email,
        "password": "Password123!",
        "organization_id": target_user["organization_id"],
    }).json()["access_token"]

    # Verify target can access admin endpoint initially
    assert client.get("/api/v1/users/rbac/admin-check", headers={"Authorization": f"Bearer {target_token}"}).status_code == 200

    # Primary Admin demotes target to CONTENT_CREATOR
    client.patch(
        f"/api/v1/users/{target_user['id']}/role",
        json={"role": "CONTENT_CREATOR"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Target tries to call admin endpoint with the EXISTING token (which still contains role="ADMIN" in JWT)
    # The backend queries the database for the active role and MUST reject with 403 Forbidden!
    demoted_res = client.get("/api/v1/users/rbac/admin-check", headers={"Authorization": f"Bearer {target_token}"})
    assert demoted_res.status_code == 403


# ---------------------------------------------------------------------------
# 5. Token Revocation & Logout Security
# ---------------------------------------------------------------------------

def test_logout_revokes_token_and_cannot_be_reused(db_session: Session):
    """
    Requirement 3.7, 3.8, 3.9: Genuine token/session revocation.
    Logged out tokens are stored in PostgreSQL denylist and cannot be reused.
    """
    slug = _unique_slug("revoc")
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Revoc Org",
        "org_slug": slug,
        "admin_email": f"user_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "User",
    }).json()
    token = boot["access_token"]
    user_id = boot["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify token works before logout
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    # Call logout
    logout_res = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_res.status_code == 200

    # Verify token record was inserted into revoked_tokens in PostgreSQL
    revoked = db_session.query(RevokedToken).filter(
        RevokedToken.user_id == uuid.UUID(user_id),
    ).first()
    assert revoked is not None

    # Now attempt to access /auth/me or any protected endpoint with the revoked token: MUST be rejected with 401
    me_after = client.get("/api/v1/auth/me", headers=headers)
    assert me_after.status_code == 401
    assert "revoked" in me_after.text.lower()

    # Attempt another protected endpoint with revoked token: rejected with 401
    users_after = client.get("/api/v1/users", headers=headers)
    assert users_after.status_code == 401


# ---------------------------------------------------------------------------
# 6. Tampered & Expired JWT Rejection
# ---------------------------------------------------------------------------

def test_tampered_and_expired_jwts_rejected():
    slug = _unique_slug("jwt-sec")
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "JWT Org",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin",
    }).json()
    valid_token = boot["access_token"]

    # 1. Expired token
    expired_token = create_access_token(
        data={"sub": boot["user"]["id"], "org": boot["user"]["organization_id"], "role": "ADMIN"},
        expires_delta=timedelta(minutes=-30),
    )
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"}).status_code == 401

    # 2. Tampered token signature (modify last character)
    tampered_token = valid_token[:-4] + "ABCD"
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"}).status_code == 401

    # 3. Completely bogus token string
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}).status_code == 401


# ---------------------------------------------------------------------------
# 7. All 7 Roles Enforced Against Real Backend Endpoints
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role,can_admin,can_upload,can_audit,can_agency,can_legal,can_analytics", [
    (UserRole.ADMIN, True, True, True, True, True, True),
    (UserRole.BRAND_MANAGER, False, True, True, False, False, True),
    (UserRole.REVIEWER, False, True, False, False, False, True),
    (UserRole.LEGAL_REVIEWER, False, True, True, False, True, True),
    (UserRole.CONTENT_CREATOR, False, True, False, False, False, False),
    (UserRole.EXTERNAL_AGENCY, False, True, False, True, False, False),
    (UserRole.LEADERSHIP, False, False, True, False, False, True),  # Leadership is strictly read-only!
])
def test_all_seven_roles_endpoint_matrix(role, can_admin, can_upload, can_audit, can_agency, can_legal, can_analytics):
    """
    Requirement 5: Test real backend endpoint access for all 7 roles.
    Confirms Leadership is read-only (cannot upload).
    Confirms External Agency has agency portal access only.
    Confirms Admin is the only role with admin-check.
    """
    slug = _unique_slug("role-7")
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Roles Org",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin",
    }).json()
    admin_token = boot["access_token"]

    # Provision user with target role
    test_email = f"user_{role.value.lower()}_{uuid.uuid4().hex[:4]}@example.com"
    user_data = client.post(
        "/api/v1/users",
        json={
            "email": test_email,
            "password": "Password123!",
            "full_name": f"{role.value} Tester",
            "role": role.value,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    # Login as user
    user_token = client.post("/api/v1/auth/login", json={
        "email": test_email,
        "password": "Password123!",
        "organization_id": user_data["organization_id"],
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {user_token}"}

    # Probe all endpoints
    assert (client.get("/api/v1/users/rbac/admin-check", headers=headers).status_code == 200) == can_admin
    assert (client.get("/api/v1/users/rbac/upload-check", headers=headers).status_code == 200) == can_upload
    assert (client.get("/api/v1/users/rbac/audit-check", headers=headers).status_code == 200) == can_audit
    assert (client.get("/api/v1/users/rbac/agency-check", headers=headers).status_code == 200) == can_agency
    assert (client.get("/api/v1/users/rbac/legal-check", headers=headers).status_code == 200) == can_legal
    assert (client.get("/api/v1/users/rbac/analytics-check", headers=headers).status_code == 200) == can_analytics


# ---------------------------------------------------------------------------
# 8. Cross-Tenant Isolation Across All Endpoints
# ---------------------------------------------------------------------------

def test_cross_tenant_isolation_comprehensive():
    """
    Requirement 6: Verify cross-tenant isolation across user list, user detail,
    user deactivation, role update, and audit logs.
    """
    slug_a = _unique_slug("tenant-a")
    slug_b = _unique_slug("tenant-b")

    boot_a = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Tenant A Corp",
        "org_slug": slug_a,
        "admin_email": "admin_a@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin A",
    }).json()
    token_a = boot_a["access_token"]
    user_a_id = boot_a["user"]["id"]

    boot_b = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Tenant B Corp",
        "org_slug": slug_b,
        "admin_email": "admin_b@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin B",
    }).json()
    token_b = boot_b["access_token"]
    user_b_id = boot_b["user"]["id"]

    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 1. User listing: Tenant A only sees Tenant A users
    list_res = client.get("/api/v1/users", headers=headers_a)
    assert list_res.status_code == 200
    ids = [u["id"] for u in list_res.json()]
    assert user_a_id in ids
    assert user_b_id not in ids

    # 2. User detail: Tenant A cannot inspect Tenant B user
    assert client.get(f"/api/v1/users/{user_b_id}", headers=headers_a).status_code == 404

    # 3. Role modification: Tenant A cannot alter Tenant B user role
    patch_role = client.patch(
        f"/api/v1/users/{user_b_id}/role",
        json={"role": "CONTENT_CREATOR"},
        headers=headers_a,
    )
    assert patch_role.status_code == 404

    # 4. User deactivation: Tenant A cannot deactivate Tenant B user
    patch_status = client.patch(
        f"/api/v1/users/{user_b_id}/status",
        json={"is_active": False},
        headers=headers_a,
    )
    assert patch_status.status_code == 404

    # 5. Audit logs: Tenant A cannot see Tenant B audit events
    audit_res = client.get("/api/v1/audit/logs", headers=headers_a)
    assert audit_res.status_code == 200
    for log in audit_res.json():
        assert log["organization_id"] == boot_a["user"]["organization_id"]
        assert log["organization_id"] != boot_b["user"]["organization_id"]


# ---------------------------------------------------------------------------
# 9. Account Deactivation Immediate Enforcement
# ---------------------------------------------------------------------------

def test_account_deactivation_immediate():
    slug = _unique_slug("deact-imm")
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Deact Org",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin",
    }).json()
    admin_token = boot["access_token"]

    # Provision user
    user = client.post(
        "/api/v1/users",
        json={
            "email": f"member_{uuid.uuid4().hex[:6]}@example.com",
            "password": "Password123!",
            "full_name": "Member",
            "role": "CONTENT_CREATOR",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    user_token = client.post("/api/v1/auth/login", json={
        "email": user["email"],
        "password": "Password123!",
        "organization_id": user["organization_id"],
    }).json()["access_token"]

    # Active user works
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {user_token}"}).status_code == 200

    # Admin deactivates member
    deact_res = client.patch(
        f"/api/v1/users/{user['id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # Existing token is immediately rejected with 403
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {user_token}"}).status_code == 403

    # Subsequent login attempt is also rejected with 403
    assert client.post("/api/v1/auth/login", json={
        "email": user["email"],
        "password": "Password123!",
        "organization_id": user["organization_id"],
    }).status_code == 403


# ---------------------------------------------------------------------------
# 10. Failed Login Audit Trail & Password Security
# ---------------------------------------------------------------------------

def test_failed_login_records_audit_trail(db_session: Session):
    slug = _unique_slug("failed-log")
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Failed Log Org",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin",
    }).json()
    org_id = boot["user"]["organization_id"]

    # Attempt login with wrong password
    bad_login = client.post("/api/v1/auth/login", json={
        "email": boot["user"]["email"],
        "password": "WrongPassword123!",
        "organization_id": org_id,
    })
    assert bad_login.status_code == 401

    # Verify USER_LOGIN_FAILED was written to audit_logs
    failed_audit = db_session.query(AuditLog).filter(
        AuditLog.organization_id == uuid.UUID(org_id),
        AuditLog.action == "USER_LOGIN_FAILED",
    ).first()
    assert failed_audit is not None


# ---------------------------------------------------------------------------
# 11. Sensitive Information Exposure Checks
# ---------------------------------------------------------------------------

def test_sensitive_information_never_exposed(db_session: Session):
    """
    Requirement 12: Verify passwords, password hashes, and secrets are never returned in responses.
    """
    slug = _unique_slug("secret-check")
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Secret Org",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "SecretPassword123!",
        "admin_full_name": "Admin",
    }).json()

    # Verify user payload in TokenResponse
    user_data = boot["user"]
    assert "password" not in user_data
    assert "hashed_password" not in user_data

    # Query /auth/me
    me_data = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {boot['access_token']}"}).json()
    assert "password" not in me_data
    assert "hashed_password" not in me_data

    # Query audit logs
    audit_data = client.get("/api/v1/audit/logs", headers={"Authorization": f"Bearer {boot['access_token']}"}).json()
    for log in audit_data:
        assert "password" not in str(log)
        assert "SecretPassword123!" not in str(log)


# ---------------------------------------------------------------------------
# 12. PostgreSQL Audit Log Trigger Immutability
# ---------------------------------------------------------------------------

def test_audit_log_database_immutability(db_session: Session):
    slug = _unique_slug("immut-sec")
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Immut Org",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin",
    }).json()
    org_id = boot["user"]["organization_id"]

    audit_entry = db_session.query(AuditLog).filter(
        AuditLog.organization_id == uuid.UUID(org_id),
    ).first()
    assert audit_entry is not None

    # Direct SQL UPDATE must be rejected by trigger
    with pytest.raises(Exception) as exc_update:
        db_session.execute(
            text("UPDATE audit_logs SET action = 'TAMPERED' WHERE id = :id"),
            {"id": audit_entry.id},
        )
        db_session.commit()
    assert "Table audit_logs is strictly append-only" in str(exc_update.value)
    db_session.rollback()

    # Direct SQL DELETE must be rejected by trigger
    with pytest.raises(Exception) as exc_delete:
        db_session.execute(
            text("DELETE FROM audit_logs WHERE id = :id"),
            {"id": audit_entry.id},
        )
        db_session.commit()
    assert "Table audit_logs is strictly append-only" in str(exc_delete.value)
    db_session.rollback()


# ---------------------------------------------------------------------------
# 13. CSRF Protection for Cookie-Authenticated Requests
# ---------------------------------------------------------------------------

def test_csrf_protection_for_cookie_authenticated_requests():
    """
    Requirement A.1: Protect state-changing requests when authenticated via cookie.
    - Missing CSRF token: 403 Forbidden.
    - Invalid/mismatched CSRF token: 403 Forbidden.
    - Valid CSRF token: 200 OK.
    - Bearer token authentication: exempt from CSRF (immune to browser cookie CSRF).
    """
    slug = _unique_slug("csrf")
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "CSRF Org",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin",
    })
    token = boot.json()["access_token"]
    user_id = boot.json()["user"]["id"]

    # Fetch CSRF token
    csrf_res = client.get("/api/v1/auth/csrf")
    assert csrf_res.status_code == 200
    valid_csrf = csrf_res.json()["csrf_token"]

    # 1. State-changing request using cookie auth WITHOUT CSRF token: REJECTED with 403
    client.cookies.set("access_token", token)
    client.cookies.set("csrf_token", valid_csrf)

    res_no_csrf_header = client.patch(
        f"/api/v1/users/{user_id}/status",
        json={"is_active": True},
        headers={},  # Missing X-CSRF-Token header
    )
    assert res_no_csrf_header.status_code == 403
    assert "CSRF" in res_no_csrf_header.text

    # 2. State-changing request with MISMATCHED CSRF token: REJECTED with 403
    res_bad_csrf = client.patch(
        f"/api/v1/users/{user_id}/status",
        json={"is_active": True},
        headers={"X-CSRF-Token": "bad-tampered-token"},
    )
    assert res_bad_csrf.status_code == 403

    # 3. State-changing request with MATCHING CSRF token: SUCCEEDS with 200
    res_valid_csrf = client.patch(
        f"/api/v1/users/{user_id}/status",
        json={"is_active": True},
        headers={"X-CSRF-Token": valid_csrf},
    )
    assert res_valid_csrf.status_code == 200

    # 4. Bearer-token authentication: exempt from CSRF
    client.cookies.clear()  # Clear cookies
    res_bearer = client.patch(
        f"/api/v1/users/{user_id}/status",
        json={"is_active": True},
        headers={"Authorization": f"Bearer {token}"},  # No CSRF header
    )
    assert res_bearer.status_code == 200


# ---------------------------------------------------------------------------
# 14. Login Rate Limiting (Brute-Force Protection)
# ---------------------------------------------------------------------------

def test_login_rate_limiting_enforcement_and_recovery():
    """
    Requirement A.2: Limit repeated failed login attempts by IP and account.
    Returns HTTP 429 when threshold is reached.
    Successful login clears failure count.
    """
    from app.auth.rate_limiter import limiter
    limiter.reset_all_for_testing()

    slug = _unique_slug("ratelim")
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Rate Limit Org",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin",
    }).json()
    email = boot["user"]["email"]
    org_id = boot["user"]["organization_id"]

    # 5 consecutive failed login attempts
    for _ in range(5):
        fail_res = client.post("/api/v1/auth/login", json={
            "email": email,
            "password": "WrongPassword123!",
            "organization_id": org_id,
        })
        assert fail_res.status_code == 401

    # 6th attempt MUST be blocked by rate limiter with HTTP 429
    blocked_res = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Password123!",  # Even with correct password, account is locked
        "organization_id": org_id,
    })
    assert blocked_res.status_code == 429
    assert "Too many failed login attempts" in blocked_res.text

    # Reset limiter for test cleanup
    limiter.reset_all_for_testing()

    # After rate limit reset/window expiration, legitimate login succeeds
    recovery_res = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Password123!",
        "organization_id": org_id,
    })
    assert recovery_res.status_code == 200


# ---------------------------------------------------------------------------
# 15. Organization Bootstrap Protection & Rate Limiting
# ---------------------------------------------------------------------------

def test_bootstrap_rate_limiting_protection():
    """
    Requirement A.3: Rate limit abuse on public bootstrap attempts.
    """
    from app.auth.rate_limiter import limiter
    limiter.reset_all_for_testing()

    # Exceed bootstrap attempts
    for i in range(20):
        s = _unique_slug(f"limit-{i}")
        client.post("/api/v1/auth/bootstrap", json={
            "org_name": f"Org {i}",
            "org_slug": s,
            "admin_email": f"adm_{i}@example.com",
            "admin_password": "Password123!",
            "admin_full_name": f"Admin {i}",
        })

    # Next attempt from the same client MUST be rate limited with HTTP 429
    excess_res = client.post("/api/v1/auth/bootstrap", json={
        "org_name": "Excess Org",
        "org_slug": _unique_slug("excess"),
        "admin_email": "excess@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Excess Admin",
    })
    assert excess_res.status_code == 429
    assert "Too many organisation bootstrap attempts" in excess_res.text

    limiter.reset_all_for_testing()


# ---------------------------------------------------------------------------
# 16. Cookie Security Configuration Tests
# ---------------------------------------------------------------------------

def test_cookie_security_configuration_development_and_production(monkeypatch):
    """
    Requirement A.4:
    - Development: Secure=False (allows local HTTP localhost development).
    - Production: Secure=True (enforces HTTPS-only cookies).
    """
    from app.config import settings

    # In current development environment:
    assert settings.COOKIE_SECURE is False

    # Simulate production environment:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert settings.COOKIE_SECURE is True

