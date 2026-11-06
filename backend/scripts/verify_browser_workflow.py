"""
scripts/verify_browser_workflow.py
Simulates the exact end-to-end browser user workflow:
Login -> Document Upload -> Extraction Preview -> Version 2 Upload -> Download Both Versions -> Audit Log Verification
"""
import os
import sys
import uuid
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.audit import AuditLog
from app.auth.password import hash_password

client = TestClient(app)

def run_browser_workflow():
    print("=" * 80)
    print(">>> COMPLETE LIVE BROWSER WORKFLOW SIMULATION")
    print("=" * 80)

    db = SessionLocal()

    # Step 1: Ensure user and organization exist for login
    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name="Apex Global Corp", slug=f"apex-{org_id[:8]}")
    db.add(org)

    user_id = str(uuid.uuid4())
    user_email = f"lead_creator_{user_id[:6]}@apexcorp.com"
    plain_password = "ApexSecurePassword2026!"
    user = User(
        id=user_id,
        organization_id=org_id,
        email=user_email,
        full_name="Alex Mercer",
        hashed_password=hash_password(plain_password),
        role=UserRole.CONTENT_CREATOR,
        is_active=True
    )
    db.add(user)
    db.commit()

    # 1. Login via /api/v1/auth/login
    print("\n[Step 1] Logging in via POST /api/v1/auth/login...")
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": plain_password, "organization_slug": org.slug}
    )
    print(f"Login Status: {login_res.status_code}")
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token_data = login_res.json()
    access_token = token_data.get("access_token")
    assert access_token, "No access token in response"
    auth_headers = {"Authorization": f"Bearer {access_token}"}
    print("Authenticated successfully. Bearer token acquired.")

    # 2. Document Upload via POST /api/v1/documents/upload
    print("\n[Step 2] Uploading Document via POST /api/v1/documents/upload...")
    v1_text = (
        "ApexCloud Brand Architecture v1\n\n"
        "ApexCloud provides deterministic enterprise cloud orchestration.\n"
        "Our mission is absolute operational reliability and transparency.\n\n"
        "Key Differentiators:\n"
        "1. Active-Active Multicloud Failover\n"
        "2. Deterministic State Verification\n"
        "3. Zero Overhead Telemetry\n"
    ).encode("utf-8")

    upload_res = client.post(
        "/api/v1/documents/upload",
        headers=auth_headers,
        files={"file": ("ApexCloud_Architecture.txt", v1_text, "text/plain")},
        data={"title": "ApexCloud Core Architecture"}
    )
    print(f"Upload Status: {upload_res.status_code}")
    assert upload_res.status_code in [200, 201], f"Upload failed: {upload_res.text}"
    upload_payload = upload_res.json()
    doc = upload_payload["document"]
    v1 = upload_payload["version"]
    doc_id = doc["id"]
    v1_id = v1["id"]
    print(f"Document Created: ID={doc_id}, Title='{doc['title']}', ContentType={doc['content_type']}")
    print(f"Version 1 Created: ID={v1_id}, Status={v1['extraction_status']}, Words={v1['word_count']}")

    # 3. Document Details & Extraction Preview via GET /api/v1/documents/{doc_id}
    print(f"\n[Step 3] Fetching Document Details & Extraction Preview via GET /api/v1/documents/{doc_id}...")
    details_res = client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    print(f"Details Status: {details_res.status_code}")
    assert details_res.status_code == 200, f"Details failed: {details_res.text}"
    doc_details = details_res.json()
    latest_ver = doc_details["latest_version"]
    print(f"Document Title: {doc_details['title']}")
    print(f"Extracted Words: {latest_ver['word_count']}, Chars: {latest_ver['character_count']}")
    print(f"Extracted Text Preview: {latest_ver['extracted_text'][:80]}...")
    structured_content = latest_ver.get("structured_content", {})
    segments = structured_content.get("segments", [])
    print(f"Structured Segments Count: {len(segments)}")
    for i, seg in enumerate(segments[:3], 1):
        print(f"  Segment {i}: [P{seg['paragraph_index']}:S{seg['sentence_index']}] '{seg['text']}'")
    assert len(segments) >= 3, "Expected at least 3 structured segments"

    # 4. Version 2 Upload via POST /api/v1/documents/{doc_id}/versions
    print(f"\n[Step 4] Uploading Version 2 via POST /api/v1/documents/{doc_id}/versions...")
    v2_text = (
        "ApexCloud Brand Architecture v2 (Updated Q4)\n\n"
        "ApexCloud provides deterministic enterprise cloud orchestration at hyper-scale.\n"
        "Our updated architecture expands coverage across hybrid multi-region data planes.\n\n"
        "Key Differentiators (v2):\n"
        "1. Active-Active Multicloud Failover with <1s recovery\n"
        "2. Deterministic State Verification via cryptographic ledgers\n"
        "3. Real-Time Telemetry and Autonomous Remediation\n"
    ).encode("utf-8")

    v2_upload_res = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers=auth_headers,
        files={"file": ("ApexCloud_Architecture_v2.txt", v2_text, "text/plain")}
    )
    print(f"V2 Upload Status: {v2_upload_res.status_code}")
    assert v2_upload_res.status_code in [200, 201], f"V2 upload failed: {v2_upload_res.text}"
    v2_payload = v2_upload_res.json()
    v2 = v2_payload["version"]
    v2_id = v2["id"]
    print(f"Version 2 Created: ID={v2_id}, VersionNumber={v2['version_number']}, Status={v2['extraction_status']}")
    assert v2["version_number"] == 2

    # 5. Version History Inspection via GET /api/v1/documents/{doc_id}/versions
    print(f"\n[Step 5] Inspecting Version History via GET /api/v1/documents/{doc_id}/versions...")
    versions_res = client.get(f"/api/v1/documents/{doc_id}/versions", headers=auth_headers)
    assert versions_res.status_code == 200
    versions_list = versions_res.json()
    print(f"Total Versions in History: {len(versions_list)}")
    for ver in versions_list:
        print(f"  v{ver['version_number']}: ID={ver['id']}, Filename={ver['original_filename']}, Status={ver['extraction_status']}, Words={ver['word_count']}")
    assert len(versions_list) == 2

    # 6. File Downloads for both versions via GET /api/v1/documents/{doc_id}/versions/{v_id}/download
    print(f"\n[Step 6] Downloading Version 1 & Version 2 files...")
    dl_v1 = client.get(f"/api/v1/documents/{doc_id}/versions/{v1_id}/download", headers=auth_headers)
    assert dl_v1.status_code == 200
    assert dl_v1.content == v1_text
    print(f"Downloaded v1 successfully: {len(dl_v1.content)} bytes (MD5/SHA matches original)")

    dl_v2 = client.get(f"/api/v1/documents/{doc_id}/versions/{v2_id}/download", headers=auth_headers)
    assert dl_v2.status_code == 200
    assert dl_v2.content == v2_text
    print(f"Downloaded v2 successfully: {len(dl_v2.content)} bytes (MD5/SHA matches original)")

    # 7. Audit Log Trail Verification
    print("\n[Step 7] Verifying Audit Logs for this workflow...")
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.organization_id == org_id)
        .order_by(AuditLog.timestamp.asc())
        .all()
    )
    print(f"Audit Log Events Recorded ({len(logs)}):")
    for log_item in logs:
        print(f"  [{log_item.action}] Actor={log_item.actor_id} Target={log_item.target_entity}:{log_item.target_id}")

    actions = [l.action for l in logs]
    assert "DOCUMENT_UPLOADED" in actions
    assert "DOCUMENT_VERSION_UPLOADED" in actions
    print("Audit Trail Verified: DOCUMENT_UPLOADED and DOCUMENT_VERSION_UPLOADED recorded.")

    db.close()
    print("\n" + "=" * 80)
    print(">>> COMPLETE LIVE BROWSER WORKFLOW VERIFIED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    run_browser_workflow()
