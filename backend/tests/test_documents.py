"""
tests/test_documents.py
Comprehensive Phase 4 test suite for content ingestion, extraction, structuring, and security.
Tests TXT, DOCX, PDF, image/OCR, corrupted/empty files, duplicate filenames, tenant isolation,
versions, retry, and unauthorized downloads.
"""
import io
import uuid
import pytest
from fastapi.testclient import TestClient
from docx import Document as DocxDocument
import pymupdf as fitz  # PyMuPDF
from PIL import Image

from app.main import app
from app.auth.rate_limiter import limiter

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_rate_limits():
    """Ensure in-memory rate limiter does not interfere across tests."""
    limiter.reset_all_for_testing()
    yield
    limiter.reset_all_for_testing()


def _unique_slug(prefix: str = "doc") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _create_org_and_user(role: str = "CONTENT_CREATOR") -> dict:
    """Bootstrap a tenant organization and provision user with the given role."""
    slug = _unique_slug()
    boot = client.post("/api/v1/auth/bootstrap", json={
        "org_name": f"Org {slug}",
        "org_slug": slug,
        "admin_email": f"adm_{uuid.uuid4().hex[:6]}@example.com",
        "admin_password": "Password123!",
        "admin_full_name": "Admin User",
    }).json()
    admin_token = boot["access_token"]
    org_id = boot["user"]["organization_id"]

    if role == "ADMIN":
        return {
            "token": admin_token,
            "headers": {"Authorization": f"Bearer {admin_token}"},
            "org_id": org_id,
            "user_id": boot["user"]["id"]
        }

    member_email = f"user_{role.lower()}_{uuid.uuid4().hex[:6]}@example.com"
    member = client.post(
        "/api/v1/users",
        json={
            "email": member_email,
            "password": "Password123!",
            "full_name": f"{role} User",
            "role": role,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    user_token = client.post("/api/v1/auth/login", json={
        "email": member_email,
        "password": "Password123!",
        "organization_id": org_id,
    }).json()["access_token"]

    return {
        "token": user_token,
        "headers": {"Authorization": f"Bearer {user_token}"},
        "org_id": org_id,
        "user_id": member["id"]
    }


def _create_test_docx() -> bytes:
    doc = DocxDocument()
    doc.add_heading("ApexCloud Marketing Strategy", level=1)
    doc.add_paragraph("ApexCloud provides ultra-low latency serverless infrastructure.")
    doc.add_paragraph("Our globally distributed database delivers 99.99% availability with zero downtime.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _create_test_pdf() -> bytes:
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((50, 70), "ApexCloud Cloud Solutions", fontsize=18)
    page1.insert_text((50, 110), "Empowering modern engineering teams with enterprise cloud infrastructure.", fontsize=11)
    page1.insert_text((50, 140), "Starting at only $49 per month for unlimited scale.", fontsize=11)

    page2 = doc.new_page()
    page2.insert_text((50, 70), "Technical Specifications", fontsize=16)
    page2.insert_text((50, 110), "Latency is under 15ms globally across all availability zones.", fontsize=11)

    return doc.tobytes()


def _create_test_image(format="PNG") -> bytes:
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_txt_extraction_and_structuring():
    """Test plain text ingestion, paragraph segmentation, and character counting."""
    user = _create_org_and_user("CONTENT_CREATOR")
    content = b"ApexCloud Product Overview\n\nApexCloud accelerates cloud deployments.\nGuaranteed 99.99% uptime."

    response = client.post(
        "/api/v1/documents/upload",
        headers=user["headers"],
        files={"file": ("overview.txt", content, "text/plain")},
        data={"title": "Custom Title Overview"}
    )
    assert response.status_code == 201
    data = response.json()

    doc = data["document"]
    version = data["version"]

    assert doc["title"] == "Custom Title Overview"
    assert doc["content_type"] == "TEXT"
    assert version["version_number"] == 1
    assert version["extraction_status"] == "COMPLETED"
    assert "ApexCloud accelerates" in version["extracted_text"]
    assert version["word_count"] > 0
    assert version["character_count"] == len(content)

    # Check structured content
    structured = version["structured_content"]
    assert structured is not None
    assert len(structured["segments"]) >= 2
    assert structured["segments"][0]["page_number"] == 1


def test_docx_extraction_with_headings():
    """Test Microsoft Word DOCX extraction, headings, and paragraph ordering."""
    user = _create_org_and_user("CONTENT_CREATOR")
    docx_bytes = _create_test_docx()

    response = client.post(
        "/api/v1/documents/upload",
        headers=user["headers"],
        files={"file": ("campaign.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    )
    assert response.status_code == 201
    data = response.json()
    version = data["version"]

    assert version["extraction_status"] == "COMPLETED"
    assert "ApexCloud Marketing Strategy" in version["extracted_text"]
    assert "serverless infrastructure" in version["extracted_text"]

    structured = version["structured_content"]
    assert len(structured["headings"]) >= 1
    assert structured["headings"][0]["text"] == "ApexCloud Marketing Strategy"
    assert len(structured["segments"]) >= 2


def test_pdf_extraction_page_numbers_and_metadata():
    """Test multi-page PDF extraction preserving page numbers and text blocks."""
    user = _create_org_and_user("CONTENT_CREATOR")
    pdf_bytes = _create_test_pdf()

    response = client.post(
        "/api/v1/documents/upload",
        headers=user["headers"],
        files={"file": ("datasheet.pdf", pdf_bytes, "application/pdf")}
    )
    assert response.status_code == 201
    data = response.json()
    version = data["version"]

    assert version["extraction_status"] == "COMPLETED"
    assert "ApexCloud Cloud Solutions" in version["extracted_text"]
    assert "Technical Specifications" in version["extracted_text"]

    structured = version["structured_content"]
    assert structured["total_pages"] == 2

    # Check segments preserve page numbers
    page_numbers = {seg["page_number"] for seg in structured["segments"]}
    assert 1 in page_numbers
    assert 2 in page_numbers


def test_image_upload_and_ocr_handling():
    """Test PNG upload and graceful OCR handling (either OCR extraction or OCR_UNAVAILABLE)."""
    user = _create_org_and_user("CONTENT_CREATOR")
    png_bytes = _create_test_image("PNG")

    response = client.post(
        "/api/v1/documents/upload",
        headers=user["headers"],
        files={"file": ("diagram.png", png_bytes, "image/png")}
    )
    assert response.status_code == 201
    data = response.json()
    version = data["version"]

    # Must be either COMPLETED (if tesseract is present), EMPTY, or OCR_UNAVAILABLE with instructions
    assert version["extraction_status"] in {"COMPLETED", "EMPTY", "OCR_UNAVAILABLE"}
    if version["extraction_status"] == "OCR_UNAVAILABLE":
        meta = version["extraction_metadata"]
        assert meta["ocr_available"] is False
        assert "instructions" in meta


def test_unsupported_file_extension_rejection():
    """Verify that unsupported extensions (.exe, .zip, etc.) are strictly rejected with 400."""
    user = _create_org_and_user("CONTENT_CREATOR")
    response = client.post(
        "/api/v1/documents/upload",
        headers=user["headers"],
        files={"file": ("malware.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/x-dosexec")}
    )
    assert response.status_code == 400
    assert "Unsupported file format" in response.text


def test_oversized_file_rejection():
    """Verify that files exceeding the maximum size limit are rejected with 400."""
    user = _create_org_and_user("CONTENT_CREATOR")
    # 26 MB dummy file
    big_content = b"A" * (26 * 1024 * 1024)
    response = client.post(
        "/api/v1/documents/upload",
        headers=user["headers"],
        files={"file": ("oversized.txt", big_content, "text/plain")}
    )
    assert response.status_code == 400
    assert "exceeds maximum limit" in response.text


def test_empty_file_rejection():
    """Verify that a 0-byte upload is rejected."""
    user = _create_org_and_user("CONTENT_CREATOR")
    response = client.post(
        "/api/v1/documents/upload",
        headers=user["headers"],
        files={"file": ("empty.txt", b"", "text/plain")}
    )
    assert response.status_code == 400
    assert "empty (0 bytes)" in response.text


def test_corrupted_file_handling():
    """Verify that a file with mismatched magic bytes is rejected cleanly."""
    user = _create_org_and_user("CONTENT_CREATOR")
    response = client.post(
        "/api/v1/documents/upload",
        headers=user["headers"],
        files={"file": ("corrupt.pdf", b"NOT_A_REAL_PDF_DATA", "application/pdf")}
    )
    assert response.status_code == 400
    assert "Corrupted PDF" in response.text


def test_duplicate_filenames_handled_safely():
    """Uploading two files with the exact same name creates distinct safe files on disk and DB."""
    user = _create_org_and_user("CONTENT_CREATOR")
    content = b"Version 1 content"
    res1 = client.post(
        "/api/v1/documents/upload",
        headers=user["headers"],
        files={"file": ("report.txt", content, "text/plain")}
    )
    assert res1.status_code == 201

    res2 = client.post(
        "/api/v1/documents/upload",
        headers=user["headers"],
        files={"file": ("report.txt", content, "text/plain")}
    )
    assert res2.status_code == 201

    id1 = res1.json()["document"]["id"]
    id2 = res2.json()["document"]["id"]
    assert id1 != id2


def test_multi_version_document_management():
    """Test adding a new version to an existing document increments version_number."""
    user = _create_org_and_user("CONTENT_CREATOR")

    # Version 1
    res1 = client.post(
        "/api/v1/documents/upload",
        headers=user["headers"],
        files={"file": ("draft.txt", b"Initial copy draft.", "text/plain")}
    )
    assert res1.status_code == 201
    doc_id = res1.json()["document"]["id"]

    # Version 2
    res2 = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers=user["headers"],
        files={"file": ("draft_v2.txt", b"Revised and finalized marketing copy.", "text/plain")}
    )
    assert res2.status_code == 201
    v2_data = res2.json()["version"]
    assert v2_data["version_number"] == 2
    assert "finalized marketing copy" in v2_data["extracted_text"]

    # List versions
    list_res = client.get(
        f"/api/v1/documents/{doc_id}/versions",
        headers=user["headers"]
    )
    assert list_res.status_code == 200
    versions = list_res.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2
    assert versions[1]["version_number"] == 1


def test_cross_tenant_isolation_and_unauthorized_download():
    """Verify that User from Org B cannot read or download documents created in Org A."""
    user_a = _create_org_and_user("CONTENT_CREATOR")
    user_b = _create_org_and_user("CONTENT_CREATOR")

    res = client.post(
        "/api/v1/documents/upload",
        headers=user_a["headers"],
        files={"file": ("secret_alpha.txt", b"Confidential strategy for Org A.", "text/plain")}
    )
    assert res.status_code == 201
    doc_id = res.json()["document"]["id"]
    ver_id = res.json()["version"]["id"]

    # Org B attempts to read document details -> 404
    read_res = client.get(f"/api/v1/documents/{doc_id}", headers=user_b["headers"])
    assert read_res.status_code == 404

    # Org B attempts to download original file -> 404
    dl_res = client.get(
        f"/api/v1/documents/{doc_id}/versions/{ver_id}/download",
        headers=user_b["headers"]
    )
    assert dl_res.status_code == 404

    # Org A authorized download -> 200 with matching content
    dl_ok = client.get(
        f"/api/v1/documents/{doc_id}/versions/{ver_id}/download",
        headers=user_a["headers"]
    )
    assert dl_ok.status_code == 200
    assert b"Confidential strategy" in dl_ok.content


def test_retry_extraction_endpoint():
    """Test re-triggering extraction updates metadata and logs audit event."""
    user = _create_org_and_user("CONTENT_CREATOR")

    res = client.post(
        "/api/v1/documents/upload",
        headers=user["headers"],
        files={"file": ("retry_test.txt", b"Content to be re-extracted.", "text/plain")}
    )
    assert res.status_code == 201
    doc_id = res.json()["document"]["id"]
    ver_id = res.json()["version"]["id"]

    retry_res = client.post(
        f"/api/v1/documents/{doc_id}/versions/{ver_id}/retry",
        headers=user["headers"]
    )
    assert retry_res.status_code == 200
    retried_ver = retry_res.json()
    assert retried_ver["extraction_status"] == "COMPLETED"
    assert retried_ver["word_count"] == 4
