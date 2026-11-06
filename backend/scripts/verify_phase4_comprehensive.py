"""
scripts/verify_phase4_comprehensive.py
Final Targeted Verification Script for Phase 4 (Content Ingestion & Extraction Engine).
Covers items 1, 2, 3, 4, 5 of the verification checklist against real PostgreSQL database
and live FastAPI router/service logic.
"""
import io
import os
import sys
import shutil
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from PIL import Image, ImageDraw
import docx
import pymupdf as fitz
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db, SessionLocal
from app.services.extractor import ContentExtractor, validate_file, MAX_FILE_SIZE
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.document import Document, DocumentVersion, DocumentLifecycleStatus, VersionWorkflowStatus
from app.auth.password import hash_password
from app.auth.jwt import create_access_token

client = TestClient(app)

SEPARATOR = "=" * 80

def print_section(title: str):
    print(f"\n{SEPARATOR}\n>>> {title}\n{SEPARATOR}")

def get_auth_token(email: str, role: UserRole, org_id: str, user_id: str) -> str:
    token_payload = {
        "sub": user_id,
        "email": email,
        "org": org_id,
        "role": role.value
    }
    return create_access_token(token_payload)

def main():
    print_section("PHASE 4 TARGETED VERIFICATION COMMENCING")
    db = SessionLocal()

    # Bootstrap two distinct test organizations & users for cross-tenant checks
    tenant_a_id = str(uuid.uuid4())
    tenant_b_id = str(uuid.uuid4())

    org_a = Organization(id=tenant_a_id, name=f"Tenant A {tenant_a_id[:8]}", slug=f"tenant-a-{tenant_a_id[:8]}")
    org_b = Organization(id=tenant_b_id, name=f"Tenant B {tenant_b_id[:8]}", slug=f"tenant-b-{tenant_b_id[:8]}")
    db.add_all([org_a, org_b])

    # Users in Org A: Admin, Creator, Leadership (no upload permission)
    admin_a_id = str(uuid.uuid4())
    creator_a_id = str(uuid.uuid4())
    leadership_a_id = str(uuid.uuid4())

    user_admin_a = User(
        id=admin_a_id,
        organization_id=tenant_a_id,
        email=f"admin_{admin_a_id[:6]}@orga.com",
        full_name="Admin Org A",
        hashed_password=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True
    )
    user_creator_a = User(
        id=creator_a_id,
        organization_id=tenant_a_id,
        email=f"creator_{creator_a_id[:6]}@orga.com",
        full_name="Creator Org A",
        hashed_password=hash_password("CreatorPass123!"),
        role=UserRole.CONTENT_CREATOR,
        is_active=True
    )
    user_leadership_a = User(
        id=leadership_a_id,
        organization_id=tenant_a_id,
        email=f"leadership_{leadership_a_id[:6]}@orga.com",
        full_name="Leadership Org A",
        hashed_password=hash_password("LeadershipPass123!"),
        role=UserRole.LEADERSHIP,
        is_active=True
    )

    # User in Org B: Admin
    admin_b_id = str(uuid.uuid4())
    user_admin_b = User(
        id=admin_b_id,
        organization_id=tenant_b_id,
        email=f"admin_{admin_b_id[:6]}@orgb.com",
        full_name="Admin Org B",
        hashed_password=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active=True
    )

    db.add_all([user_admin_a, user_creator_a, user_leadership_a, user_admin_b])
    db.commit()

    token_admin_a = get_auth_token(user_admin_a.email, UserRole.ADMIN, tenant_a_id, admin_a_id)
    token_creator_a = get_auth_token(user_creator_a.email, UserRole.CONTENT_CREATOR, tenant_a_id, creator_a_id)
    token_leadership_a = get_auth_token(user_leadership_a.email, UserRole.LEADERSHIP, tenant_a_id, leadership_a_id)
    token_admin_b = get_auth_token(user_admin_b.email, UserRole.ADMIN, tenant_b_id, admin_b_id)

    headers_admin_a = {"Authorization": f"Bearer {token_admin_a}"}
    headers_creator_a = {"Authorization": f"Bearer {token_creator_a}"}
    headers_leadership_a = {"Authorization": f"Bearer {token_leadership_a}"}
    headers_admin_b = {"Authorization": f"Bearer {token_admin_b}"}

    # =========================================================================
    # ITEM 1: Real Extraction Tests
    # =========================================================================
    print_section("ITEM 1: Real Extraction for TXT, DOCX, Multi-page PDF, PNG, JPG, and Scanned PDF")

    # 1.1 TXT
    txt_content = (
        "ApexCloud Brand Manifesto\n\n"
        "ApexCloud is the definitive cloud operations engine.\n\n"
        "Core Values:\n"
        "1. Resilience\n"
        "2. Velocity\n"
        "3. Precision\n"
    ).encode("utf-8")
    extractor = ContentExtractor()
    res_txt = extractor.extract(txt_content, "Apex_Manifesto.txt")
    print(f"[TXT] Status: {res_txt.status}, Words: {res_txt.word_count}, Chars: {res_txt.character_count}")
    print(f"[TXT] Structured Segments: {len(res_txt.structured_content.get('segments', []))}")
    assert res_txt.status == "COMPLETED", f"TXT failed: {res_txt.metadata}"
    assert res_txt.word_count > 10
    assert len(res_txt.structured_content.get("segments", [])) >= 2

    # 1.2 DOCX containing Headings, Paragraphs, and Tables
    docx_doc = docx.Document()
    docx_doc.add_heading("ApexCloud Architecture Whitepaper", level=0)
    docx_doc.add_heading("1. Infrastructure Governance", level=1)
    docx_doc.add_paragraph("ApexCloud enforces deterministic multi-region replication across tier-1 clouds.")
    docx_doc.add_heading("2. Operational SLAs", level=2)
    docx_doc.add_paragraph("The table below details target uptime metrics.")
    table = docx_doc.add_table(rows=3, cols=3)
    table.cell(0, 0).text = "Tier"
    table.cell(0, 1).text = "Availability"
    table.cell(0, 2).text = "Recovery Point"
    table.cell(1, 0).text = "Enterprise Prime"
    table.cell(1, 1).text = "99.999%"
    table.cell(1, 2).text = "< 5 seconds"
    table.cell(2, 0).text = "Standard Plus"
    table.cell(2, 1).text = "99.95%"
    table.cell(2, 2).text = "< 60 seconds"

    docx_buffer = io.BytesIO()
    docx_doc.save(docx_buffer)
    docx_bytes = docx_buffer.getvalue()

    res_docx = extractor.extract(docx_bytes, "Architecture_Whitepaper.docx")
    print(f"[DOCX] Status: {res_docx.status}, Words: {res_docx.word_count}, Chars: {res_docx.character_count}")
    docx_headings = res_docx.structured_content.get("headings", [])
    docx_segs = res_docx.structured_content.get("segments", [])
    print(f"[DOCX] Headings Captured: {len(docx_headings)}, Total Segments: {len(docx_segs)}")
    assert res_docx.status == "COMPLETED"
    assert len(docx_headings) >= 2, "Failed to capture DOCX headings"
    assert "99.999%" in res_docx.extracted_text, "Table contents missing from extracted DOCX text"

    # 1.3 Multi-page PDF containing Selectable Text
    pdf_doc = fitz.open()
    # Page 1
    page1 = pdf_doc.new_page(width=595, height=842)
    page1.insert_text((50, 72), "ApexCloud Executive Overview - Page 1", fontsize=18)
    page1.insert_text((50, 120), "This is the first page describing our zero-trust security perimeter.", fontsize=12)
    page1.insert_text((50, 160), "Our protocol eliminates lateral movement through granular service identities.", fontsize=12)

    # Page 2
    page2 = pdf_doc.new_page(width=595, height=842)
    page2.insert_text((50, 72), "ApexCloud Operational Benchmarks - Page 2", fontsize=18)
    page2.insert_text((50, 120), "Benchmarked throughput demonstrates 4.8 million transactions per second.", fontsize=12)
    page2.insert_text((50, 160), "Telemetry validates sub-millisecond p99 latency globally.", fontsize=12)

    pdf_bytes = pdf_doc.write()
    res_pdf = extractor.extract(pdf_bytes, "Executive_Overview.pdf")
    print(f"[PDF] Status: {res_pdf.status}, Pages: {res_pdf.metadata.get('pages')}, Words: {res_pdf.word_count}")
    pdf_segs = res_pdf.structured_content.get("segments", [])
    p1_segs = [s for s in pdf_segs if s.get("page_number") == 1]
    p2_segs = [s for s in pdf_segs if s.get("page_number") == 2]
    print(f"[PDF] Page 1 Segments: {len(p1_segs)}, Page 2 Segments: {len(p2_segs)}")
    assert res_pdf.status == "COMPLETED"
    assert res_pdf.metadata.get("pages") == 2
    assert len(p1_segs) >= 1 and len(p2_segs) >= 1
    assert "zero-trust security" in res_pdf.extracted_text
    assert "4.8 million transactions" in res_pdf.extracted_text

    # 1.4 PNG and JPG Images
    img_png = Image.new("RGB", (320, 120), color=(255, 255, 255))
    draw_png = ImageDraw.Draw(img_png)
    draw_png.text((20, 40), "ApexCloud PNG Image Text", fill=(0, 0, 0))
    png_buf = io.BytesIO()
    img_png.save(png_buf, format="PNG")
    png_bytes = png_buf.getvalue()

    img_jpg = Image.new("RGB", (320, 120), color=(240, 240, 240))
    draw_jpg = ImageDraw.Draw(img_jpg)
    draw_jpg.text((20, 40), "ApexCloud JPG Image Text", fill=(0, 0, 0))
    jpg_buf = io.BytesIO()
    img_jpg.save(jpg_buf, format="JPEG")
    jpg_bytes = jpg_buf.getvalue()

    res_png = extractor.extract(png_bytes, "badge.png")
    res_jpg = extractor.extract(jpg_bytes, "badge.jpg")
    print(f"[PNG] Status: {res_png.status}, Metadata: {res_png.metadata}")
    print(f"[JPG] Status: {res_jpg.status}, Metadata: {res_jpg.metadata}")
    assert res_png.status in ["COMPLETED", "OCR_UNAVAILABLE"]
    assert res_jpg.status in ["COMPLETED", "OCR_UNAVAILABLE"]

    # 1.5 Scanned PDF (PDF containing raster image without text layer)
    scanned_pdf = fitz.open()
    scan_page = scanned_pdf.new_page(width=400, height=300)
    scan_page.insert_image(fitz.Rect(50, 50, 350, 250), stream=png_bytes)
    scanned_pdf_bytes = scanned_pdf.write()
    res_scanned = extractor.extract(scanned_pdf_bytes, "scanned_invoice.pdf")
    print(f"[Scanned PDF] Status: {res_scanned.status}, Metadata: {res_scanned.metadata}")
    assert res_scanned.metadata.get("pages") == 1
    assert res_scanned.status in ["COMPLETED", "OCR_UNAVAILABLE"]
    print("Item 1 Real Extraction Tests: ALL PASSED")

    # =========================================================================
    # ITEM 2: OCR Fallback and Retry Extraction
    # =========================================================================
    print_section("ITEM 2: OCR Fallback When Tesseract is Unavailable and Retry Extraction")

    import app.services.extractor as ext_mod
    original_pytesseract = ext_mod.pytesseract

    # Simulate Tesseract missing
    ext_mod.pytesseract = None
    res_ocr_fallback = ext_mod.ContentExtractor.extract(png_bytes, "badge_no_ocr.png")
    print(f"[Fallback OCR] Status: {res_ocr_fallback.status}")
    print(f"[Fallback OCR] Method: {res_ocr_fallback.method}")
    print(f"[Fallback OCR] Instructions: {res_ocr_fallback.metadata.get('instructions')}")
    assert res_ocr_fallback.status == "OCR_UNAVAILABLE"
    assert "Install Tesseract-OCR" in res_ocr_fallback.metadata.get("instructions", "")

    # Restore pytesseract module ref
    ext_mod.pytesseract = original_pytesseract

    # Test Retry Extraction Endpoint via API
    upload_res = client.post(
        "/api/v1/documents/upload",
        headers=headers_admin_a,
        files={"file": ("apex_badge.png", png_bytes, "image/png")},
        data={"title": "Apex Badge Asset"}
    )
    assert upload_res.status_code in [200, 201], upload_res.text
    badge_data = upload_res.json()
    badge_doc_id = badge_data["document"]["id"]
    badge_v1_id = badge_data["version"]["id"]
    print(f"[Retry Test] Created document {badge_doc_id}, initial status: {badge_data['version']['extraction_status']}")

    retry_res = client.post(
        f"/api/v1/documents/{badge_doc_id}/versions/{badge_v1_id}/retry",
        headers=headers_admin_a
    )
    print(f"[Retry Test] Retry response code: {retry_res.status_code}")
    assert retry_res.status_code == 200, retry_res.text
    retry_data = retry_res.json()
    print(f"[Retry Test] Extraction status after retry: {retry_data['extraction_status']}")
    assert retry_data["extraction_status"] in ["COMPLETED", "OCR_UNAVAILABLE", "FAILED"]
    print("Item 2 OCR Fallback and Retry: ALL PASSED")

    # =========================================================================
    # ITEM 3: Document Versioning (v1, modified v2, file preservation)
    # =========================================================================
    print_section("ITEM 3: Document Versioning (Upload v1, Upload Modified v2, File Preservation)")

    v1_bytes = b"# Brand Guidelines v1.0\nOur signature hex is #0052CC. Font is Inter."
    upload_v1_res = client.post(
        "/api/v1/documents/upload",
        headers=headers_creator_a,
        files={"file": ("BrandGuidelines_v1.txt", v1_bytes, "text/plain")},
        data={"title": "ApexCloud Master Brand Guidelines"}
    )
    assert upload_v1_res.status_code in [200, 201], upload_v1_res.text
    v1_upload_data = upload_v1_res.json()
    doc_id = v1_upload_data["document"]["id"]
    v1_id = v1_upload_data["version"]["id"]
    print(f"[Versioning] Document {doc_id} created with Version 1 (ID: {v1_id})")

    # Upload Modified Version 2
    v2_bytes = b"# Brand Guidelines v2.0 (Updated)\nOur signature hex is #0033AA. Secondary font is Roboto Mono."
    upload_v2_res = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers=headers_creator_a,
        files={"file": ("BrandGuidelines_v2.txt", v2_bytes, "text/plain")}
    )
    assert upload_v2_res.status_code in [200, 201], upload_v2_res.text
    v2_ver = upload_v2_res.json()["version"]
    v2_id = v2_ver["id"]
    print(f"[Versioning] Version 2 created (ID: {v2_id}, Version Number: {v2_ver['version_number']})")
    assert v2_ver["version_number"] == 2

    # Query full version list for document
    versions_list_res = client.get(f"/api/v1/documents/{doc_id}/versions", headers=headers_creator_a)
    assert versions_list_res.status_code == 200
    versions_list = versions_list_res.json()
    print(f"[Versioning] Retrieved {len(versions_list)} versions from API")
    assert len(versions_list) == 2
    assert {v["version_number"] for v in versions_list} == {1, 2}

    # Verify both files exist on disk and can be downloaded independently
    v1_dl = client.get(f"/api/v1/documents/{doc_id}/versions/{v1_id}/download", headers=headers_creator_a)
    assert v1_dl.status_code == 200
    assert v1_dl.content == v1_bytes, "Version 1 file content corrupted or overwritten"

    v2_dl = client.get(f"/api/v1/documents/{doc_id}/versions/{v2_id}/download", headers=headers_creator_a)
    assert v2_dl.status_code == 200
    assert v2_dl.content == v2_bytes, "Version 2 file content corrupted"

    print(f"[Versioning] Version 1 download matches: {len(v1_dl.content)} bytes")
    print(f"[Versioning] Version 2 download matches: {len(v2_dl.content)} bytes")
    print("Item 3 Document Versioning: ALL PASSED")

    # =========================================================================
    # ITEM 4: Security Verifications
    # =========================================================================
    print_section("ITEM 4: Security (Cross-Tenant Access/Download, RBAC, Validation & Defense)")

    # 4.1 Cross-Tenant Document Access
    # Tenant B attempts to read Tenant A's document
    cross_read = client.get(f"/api/v1/documents/{doc_id}", headers=headers_admin_b)
    print(f"[Security] Tenant B GET Tenant A doc: status {cross_read.status_code}")
    assert cross_read.status_code == 404, "Cross-tenant document read must return 404"

    # 4.2 Cross-Tenant Download Attempt
    cross_dl = client.get(f"/api/v1/documents/{doc_id}/versions/{v1_id}/download", headers=headers_admin_b)
    print(f"[Security] Tenant B Download Tenant A version: status {cross_dl.status_code}")
    assert cross_dl.status_code == 404, "Cross-tenant version download must return 404"

    # 4.3 Unauthorized Role Attempts
    # Leadership (no PERM_UPLOAD_DOCS) tries to upload a new document
    unauth_upload = client.post(
        "/api/v1/documents/upload",
        headers=headers_leadership_a,
        files={"file": ("hacker.txt", b"hack", "text/plain")},
        data={"title": "Unauthorized Doc"}
    )
    print(f"[Security] Leadership upload attempt: status {unauth_upload.status_code}")
    assert unauth_upload.status_code == 403, "Leadership must be forbidden from uploading (PERM_UPLOAD_DOCS required)"

    # Leadership tries to upload a new version
    unauth_new_ver = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers=headers_leadership_a,
        files={"file": ("hacker_v3.txt", b"hack v3", "text/plain")}
    )
    print(f"[Security] Leadership new version attempt: status {unauth_new_ver.status_code}")
    assert unauth_new_ver.status_code == 403, "Leadership must be forbidden from creating versions"

    # Leadership tries to retry extraction
    unauth_retry = client.post(
        f"/api/v1/documents/{doc_id}/versions/{v1_id}/retry",
        headers=headers_leadership_a
    )
    print(f"[Security] Leadership retry attempt: status {unauth_retry.status_code}")
    assert unauth_retry.status_code == 403, "Leadership must be forbidden from triggering retry"

    # Leadership tries to delete document
    unauth_delete = client.delete(
        f"/api/v1/documents/{doc_id}",
        headers=headers_leadership_a
    )
    print(f"[Security] Leadership delete attempt: status {unauth_delete.status_code}")
    assert unauth_delete.status_code == 403, "Leadership must be forbidden from deleting documents"

    # 4.4 Unauthenticated Attempts
    unauth_req = client.get(f"/api/v1/documents/{doc_id}")
    print(f"[Security] Unauthenticated document access: status {unauth_req.status_code}")
    assert unauth_req.status_code == 401, "Unauthenticated access must return 401"

    # 4.5 Invalid File Signatures (Spoofed file type)
    # File named .pdf but containing arbitrary binary or executable header (e.g. MZ)
    spoofed_bytes = b"MZ\x90\x00\x03\x00\x00\x00FakePEHeaderNotAPDF"
    bad_sig_res = client.post(
        "/api/v1/documents/upload",
        headers=headers_admin_a,
        files={"file": ("malware.pdf", spoofed_bytes, "application/pdf")},
        data={"title": "Spoofed PDF"}
    )
    print(f"[Security] Spoofed PDF upload: status {bad_sig_res.status_code}")
    assert bad_sig_res.status_code == 400, "Invalid file signature must be rejected with 400"

    # 4.6 Oversized Files
    # Test file validation directly for oversized limit
    huge_bytes = b"0" * (MAX_FILE_SIZE + 1024)
    try:
        validate_file("huge.txt", huge_bytes)
        assert False, "Should have raised ValueError for oversized file"
    except ValueError as ve:
        print(f"[Security] Oversized file validation caught correctly: {ve}")
        assert "exceeds maximum limit" in str(ve)

    # 4.7 Path Traversal Filename
    traversal_bytes = b"Safe file content with dangerous filename"
    traversal_res = client.post(
        "/api/v1/documents/upload",
        headers=headers_admin_a,
        files={"file": ("../../../../etc/shadow.txt", traversal_bytes, "text/plain")},
        data={"title": "Traversal Filename Doc"}
    )
    print(f"[Security] Path traversal filename upload: status {traversal_res.status_code}")
    assert traversal_res.status_code in [200, 201]
    traversal_data = traversal_res.json()
    traversal_v_id = traversal_data["version"]["id"]
    traversal_db_ver = db.query(DocumentVersion).filter(DocumentVersion.id == traversal_v_id).first()
    traversal_storage_path = traversal_db_ver.file_path
    print(f"[Security] Sanitized stored path on disk: {traversal_storage_path}")
    assert ".." not in traversal_storage_path
    assert "etc" not in traversal_storage_path
    assert os.path.exists(traversal_storage_path)

    # 4.8 Corrupted Files
    corrupt_pdf_bytes = b"%PDF-1.4\nCorrupted byte stream without xref table or catalog"
    corrupt_res = client.post(
        "/api/v1/documents/upload",
        headers=headers_admin_a,
        files={"file": ("broken.pdf", corrupt_pdf_bytes, "application/pdf")},
        data={"title": "Corrupted PDF"}
    )
    print(f"[Security] Corrupted PDF upload: status {corrupt_res.status_code}")
    assert corrupt_res.status_code in [200, 201]
    corrupt_data = corrupt_res.json()
    print(f"[Security] Corrupted PDF extraction status: {corrupt_data['version']['extraction_status']}")
    assert corrupt_data["version"]["extraction_status"] == "FAILED"
    assert corrupt_data["version"]["extraction_metadata"].get("error") is not None
    print("Item 4 Security Verifications: ALL PASSED")

    # =========================================================================
    # ITEM 5: Document Deletion and File Cleanup Isolation
    # =========================================================================
    print_section("ITEM 5: Deletion Verification (File Removal & Tenant Isolation)")

    # Create a standalone document with 2 versions to delete
    del_v1_bytes = b"File to be deleted - version 1"
    del_v2_bytes = b"File to be deleted - version 2"
    doc_to_delete_res = client.post(
        "/api/v1/documents/upload",
        headers=headers_admin_a,
        files={"file": ("delete_me_v1.txt", del_v1_bytes, "text/plain")},
        data={"title": "Document To Delete"}
    )
    assert doc_to_delete_res.status_code in [200, 201]
    doc_to_delete_id = doc_to_delete_res.json()["document"]["id"]

    add_v2_res = client.post(
        f"/api/v1/documents/{doc_to_delete_id}/versions",
        headers=headers_admin_a,
        files={"file": ("delete_me_v2.txt", del_v2_bytes, "text/plain")}
    )
    assert add_v2_res.status_code in [200, 201]

    # Retrieve physical file paths of both versions from DB
    db_versions = db.query(DocumentVersion).filter(DocumentVersion.document_id == doc_to_delete_id).all()
    paths_to_check = [v.file_path for v in db_versions]
    print(f"[Deletion] Physical paths before deletion: {paths_to_check}")
    for p in paths_to_check:
        assert os.path.exists(p), f"Expected file {p} to exist before deletion"

    # Also check that an unrelated document's physical file exists
    survivor_v1 = db.query(DocumentVersion).filter(DocumentVersion.id == v1_id).first()
    survivor_path = survivor_v1.file_path
    assert os.path.exists(survivor_path)

    # Perform Deletion of doc_to_delete
    del_call_res = client.delete(
        f"/api/v1/documents/{doc_to_delete_id}",
        headers=headers_admin_a
    )
    print(f"[Deletion] DELETE /documents/{doc_to_delete_id} status: {del_call_res.status_code}")
    assert del_call_res.status_code in [200, 204]

    # Verify both deleted files were purged from disk
    for p in paths_to_check:
        assert not os.path.exists(p), f"Expected file {p} to be removed from disk"
    print(f"[Deletion] Confirmed all {len(paths_to_check)} version files removed from disk")

    # Verify survivor document file was NOT touched
    assert os.path.exists(survivor_path), "Survivor document file was erroneously deleted!"
    print(f"[Deletion] Confirmed survivor file untouched: {survivor_path}")

    # Verify document no longer accessible via API
    get_deleted = client.get(f"/api/v1/documents/{doc_to_delete_id}", headers=headers_admin_a)
    assert get_deleted.status_code == 404
    print("Item 5 Deletion Verification: ALL PASSED")

    db.close()
    print_section("ALL 5 VERIFICATION MODULES EXECUTED AND CONFIRMED 100% SUCCESSFUL!")

if __name__ == "__main__":
    main()
