"""
app/api/v1/documents.py
Content Ingestion, File Upload, Extraction, and Document Management API.
Enforces strict multi-tenant isolation, safe local file storage, and RBAC permissions.
"""
import os
import re
import uuid
import logging
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.models.document import Document, DocumentVersion, DocumentLifecycleStatus, VersionWorkflowStatus
from app.schemas.document import (
    DocumentOut, DocumentVersionOut, DocumentUploadResponse, DocumentUpdateTitle
)
from app.auth.dependencies import get_current_active_user
from app.auth.rbac import require_permission, PERM_UPLOAD_DOCS, PERM_READ_OWN_DOCS
from app.audit.audit_logger import log_action
from app.services.extractor import ContentExtractor, validate_file

logger = logging.getLogger(__name__)

router = APIRouter()

STORAGE_BASE_DIR = os.path.abspath(settings.STORAGE_PATH)


def _safe_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and shell injection."""
    basename = os.path.basename(filename)
    clean = re.sub(r'[^a-zA-Z0-9_.-]', '_', basename)
    return clean[:120] if clean else "document.bin"


def _get_document_or_404(document_id: str, current_user: User, db: Session) -> Document:
    """Tenant-isolated retrieval of Document."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    doc = (
        db.query(Document)
        .filter(
            Document.id == doc_uuid,
            Document.organization_id == current_user.organization_id
        )
        .first()
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return doc


def _get_version_or_404(
    document: Document,
    version_id: str,
    current_user: User,
    db: Session
) -> DocumentVersion:
    """Tenant-isolated retrieval of DocumentVersion."""
    try:
        v_uuid = uuid.UUID(version_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

    version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.id == v_uuid,
            DocumentVersion.document_id == document.id,
            DocumentVersion.organization_id == current_user.organization_id
        )
        .first()
    )
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found.")
    return version


def _format_version_out(v: DocumentVersion) -> DocumentVersionOut:
    return DocumentVersionOut(
        id=str(v.id),
        organization_id=str(v.organization_id),
        document_id=str(v.document_id),
        version_number=v.version_number,
        original_filename=v.original_filename,
        file_size_bytes=v.file_size_bytes,
        mime_type=v.mime_type,
        extraction_status=v.extraction_status,
        extracted_text=v.extracted_text,
        word_count=v.word_count,
        character_count=v.character_count,
        version_status=v.version_status.value if hasattr(v.version_status, "value") else str(v.version_status),
        is_locked=v.is_locked,
        created_at=v.created_at,
        extraction_metadata=v.extraction_metadata,
        structured_content=v.structured_content,
    )


def _format_document_out(doc: Document, latest_version: Optional[DocumentVersion], count: int) -> DocumentOut:
    return DocumentOut(
        id=str(doc.id),
        organization_id=str(doc.organization_id),
        creator_id=str(doc.creator_id),
        title=doc.title,
        content_type=doc.content_type,
        lifecycle_status=doc.lifecycle_status.value if hasattr(doc.lifecycle_status, "value") else str(doc.lifecycle_status),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        latest_version=_format_version_out(latest_version) if latest_version else None,
        versions_count=count,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(PERM_UPLOAD_DOCS))]
)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Upload a document, validate format & magic bytes, extract content, and store metadata.
    """
    raw_bytes = await file.read()
    filename = file.filename or "upload.txt"

    # Validation
    try:
        ext, canonical_mime = validate_file(filename, raw_bytes, file.content_type)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()

    # Determine document content type enum string
    ext_upper = ext.upper()
    if ext_upper in {"PNG", "JPG", "JPEG"}:
        content_type_str = "IMAGE"
    elif ext_upper in {"DOCX"}:
        content_type_str = "DOCX"
    elif ext_upper in {"PDF"}:
        content_type_str = "PDF"
    else:
        content_type_str = "TEXT"

    # Content extraction
    extraction = ContentExtractor.extract(raw_bytes, filename, canonical_mime)

    # Derive document title
    doc_title = title.strip() if (title and title.strip()) else None
    if not doc_title:
        inferred = extraction.structured_content.get("title")
        doc_title = inferred if inferred else os.path.splitext(filename)[0]
    doc_title = doc_title[:255]

    # Save file safely to disk
    org_folder = os.path.join(STORAGE_BASE_DIR, str(current_user.organization_id))
    os.makedirs(org_folder, exist_ok=True)
    safe_name = f"{version_id}_{_safe_filename(filename)}"
    stored_path = os.path.join(org_folder, safe_name)
    with open(stored_path, "wb") as f:
        f.write(raw_bytes)

    # Database records
    new_doc = Document(
        id=doc_id,
        organization_id=current_user.organization_id,
        creator_id=current_user.id,
        title=doc_title,
        content_type=content_type_str,
        lifecycle_status=DocumentLifecycleStatus.IN_PROGRESS
    )
    db.add(new_doc)
    db.flush()

    new_version = DocumentVersion(
        id=version_id,
        organization_id=current_user.organization_id,
        document_id=doc_id,
        version_number=1,
        raw_content=extraction.extracted_text if len(extraction.extracted_text) < 100000 else extraction.extracted_text[:100000],
        file_path=stored_path,
        extracted_text=extraction.extracted_text,
        original_filename=filename,
        file_size_bytes=len(raw_bytes),
        mime_type=canonical_mime,
        extraction_status=extraction.status,
        extraction_metadata=extraction.metadata,
        structured_content=extraction.structured_content,
        word_count=extraction.word_count,
        character_count=extraction.character_count,
        version_status=VersionWorkflowStatus.DRAFT,
        is_locked=False
    )
    db.add(new_version)

    # Audit log
    log_action(
        db=db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="DOCUMENT_UPLOADED",
        target_entity="documents",
        target_id=new_doc.id,
        details={
            "filename": filename,
            "version_number": 1,
            "file_size": len(raw_bytes),
            "extraction_status": extraction.status,
            "word_count": extraction.word_count
        }
    )
    db.commit()
    db.refresh(new_doc)
    db.refresh(new_version)

    msg = f"Document '{doc_title}' uploaded successfully. Extraction status: {extraction.status}."
    return DocumentUploadResponse(
        document=_format_document_out(new_doc, new_version, 1),
        version=_format_version_out(new_version),
        message=msg
    )


@router.post(
    "/{document_id}/versions",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(PERM_UPLOAD_DOCS))]
)
async def upload_new_version(
    document_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Upload a new version to an existing document."""
    doc = _get_document_or_404(document_id, current_user, db)

    raw_bytes = await file.read()
    filename = file.filename or "version_upload.bin"

    try:
        ext, canonical_mime = validate_file(filename, raw_bytes, file.content_type)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    # Determine next version number
    highest_ver = (
        db.query(func.max(DocumentVersion.version_number))
        .filter(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.organization_id == current_user.organization_id
        )
        .scalar()
    ) or 0
    next_ver = highest_ver + 1
    version_id = uuid.uuid4()

    # Extraction
    extraction = ContentExtractor.extract(raw_bytes, filename, canonical_mime)

    # Save file
    org_folder = os.path.join(STORAGE_BASE_DIR, str(current_user.organization_id))
    os.makedirs(org_folder, exist_ok=True)
    safe_name = f"{version_id}_v{next_ver}_{_safe_filename(filename)}"
    stored_path = os.path.join(org_folder, safe_name)
    with open(stored_path, "wb") as f:
        f.write(raw_bytes)

    new_version = DocumentVersion(
        id=version_id,
        organization_id=current_user.organization_id,
        document_id=doc.id,
        version_number=next_ver,
        raw_content=extraction.extracted_text if len(extraction.extracted_text) < 100000 else extraction.extracted_text[:100000],
        file_path=stored_path,
        extracted_text=extraction.extracted_text,
        original_filename=filename,
        file_size_bytes=len(raw_bytes),
        mime_type=canonical_mime,
        extraction_status=extraction.status,
        extraction_metadata=extraction.metadata,
        structured_content=extraction.structured_content,
        word_count=extraction.word_count,
        character_count=extraction.character_count,
        version_status=VersionWorkflowStatus.DRAFT,
        is_locked=False
    )
    db.add(new_version)
    doc.updated_at = datetime.now(timezone.utc)

    log_action(
        db=db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="DOCUMENT_VERSION_UPLOADED",
        target_entity="document_versions",
        target_id=new_version.id,
        details={
            "document_id": str(doc.id),
            "version_number": next_ver,
            "filename": filename,
            "extraction_status": extraction.status
        }
    )
    db.commit()
    db.refresh(new_version)
    db.refresh(doc)

    total_count = (
        db.query(func.count(DocumentVersion.id))
        .filter(DocumentVersion.document_id == doc.id)
        .scalar()
    ) or next_ver

    return DocumentUploadResponse(
        document=_format_document_out(doc, new_version, total_count),
        version=_format_version_out(new_version),
        message=f"Version {next_ver} uploaded. Extraction status: {extraction.status}."
    )


@router.get("", response_model=List[DocumentOut])
def list_documents(
    content_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List documents belonging to the user's organization."""
    query = db.query(Document).filter(Document.organization_id == current_user.organization_id)

    if content_type and content_type.upper() != "ALL":
        query = query.filter(Document.content_type == content_type.upper())

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(Document.title.ilike(term))

    docs = query.order_by(desc(Document.created_at)).offset(offset).limit(limit).all()

    result = []
    for doc in docs:
        latest = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.organization_id == current_user.organization_id
            )
            .order_by(desc(DocumentVersion.version_number))
            .first()
        )
        count = (
            db.query(func.count(DocumentVersion.id))
            .filter(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.organization_id == current_user.organization_id
            )
            .scalar()
        ) or 1
        result.append(_format_document_out(doc, latest, count))
    return result


@router.get("/{document_id}", response_model=DocumentOut)
def get_document_details(
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get document details with its latest version."""
    doc = _get_document_or_404(document_id, current_user, db)
    latest = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.organization_id == current_user.organization_id
        )
        .order_by(desc(DocumentVersion.version_number))
        .first()
    )
    count = (
        db.query(func.count(DocumentVersion.id))
        .filter(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.organization_id == current_user.organization_id
        )
        .scalar()
    ) or 1
    return _format_document_out(doc, latest, count)


@router.get("/{document_id}/versions", response_model=List[DocumentVersionOut])
def list_document_versions(
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all versions for a document."""
    doc = _get_document_or_404(document_id, current_user, db)
    versions = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.organization_id == current_user.organization_id
        )
        .order_by(desc(DocumentVersion.version_number))
        .all()
    )
    return [_format_version_out(v) for v in versions]


@router.get("/{document_id}/versions/{version_id}", response_model=DocumentVersionOut)
def get_version_details(
    document_id: str,
    version_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get details, extracted text, and structured segments of a specific version."""
    doc = _get_document_or_404(document_id, current_user, db)
    version = _get_version_or_404(doc, version_id, current_user, db)
    return _format_version_out(version)


@router.get("/{document_id}/versions/{version_id}/download")
def download_original_file(
    document_id: str,
    version_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Download the authorized original uploaded file.
    Validates tenant isolation and prevents path traversal.
    """
    doc = _get_document_or_404(document_id, current_user, db)
    version = _get_version_or_404(doc, version_id, current_user, db)

    if not version.file_path or not os.path.exists(version.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored file not found on disk."
        )

    # Security check: ensure path is strictly inside tenant's storage folder
    expected_org_dir = os.path.abspath(os.path.join(STORAGE_BASE_DIR, str(current_user.organization_id)))
    actual_file_dir = os.path.abspath(os.path.dirname(version.file_path))
    if not actual_file_dir.startswith(expected_org_dir):
        logger.error("Path traversal detected: %s vs %s", actual_file_dir, expected_org_dir)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    download_name = version.original_filename or f"document_{doc.id}_v{version.version_number}"
    return FileResponse(
        path=version.file_path,
        media_type=version.mime_type or "application/octet-stream",
        filename=download_name
    )


@router.post(
    "/{document_id}/versions/{version_id}/retry",
    response_model=DocumentVersionOut,
    dependencies=[Depends(require_permission(PERM_UPLOAD_DOCS))]
)
def retry_extraction(
    document_id: str,
    version_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retry extraction on an existing document version."""
    doc = _get_document_or_404(document_id, current_user, db)
    version = _get_version_or_404(doc, version_id, current_user, db)

    if not version.file_path or not os.path.exists(version.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file not found.")

    with open(version.file_path, "rb") as f:
        raw_bytes = f.read()

    extraction = ContentExtractor.extract(raw_bytes, version.original_filename or "document.bin", version.mime_type)

    version.extracted_text = extraction.extracted_text
    version.raw_content = extraction.extracted_text[:100000] if extraction.extracted_text else ""
    version.extraction_status = extraction.status
    version.extraction_metadata = extraction.metadata
    version.structured_content = extraction.structured_content
    version.word_count = extraction.word_count
    version.character_count = extraction.character_count

    log_action(
        db=db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="DOCUMENT_EXTRACTION_RETRIED",
        target_entity="document_versions",
        target_id=version.id,
        details={
            "document_id": str(doc.id),
            "version_number": version.version_number,
            "status": extraction.status
        }
    )
    db.commit()
    db.refresh(version)

    return _format_version_out(version)


@router.patch("/{document_id}/title", response_model=DocumentOut)
def update_document_title(
    document_id: str,
    payload: DocumentUpdateTitle,
    current_user: User = Depends(require_permission(PERM_UPLOAD_DOCS)),
    db: Session = Depends(get_db)
):
    """Update a document's title."""
    doc = _get_document_or_404(document_id, current_user, db)
    doc.title = payload.title.strip()
    doc.updated_at = datetime.now(timezone.utc)

    log_action(
        db=db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="DOCUMENT_TITLE_UPDATED",
        target_entity="documents",
        target_id=doc.id,
        details={"title": doc.title}
    )
    db.commit()
    db.refresh(doc)

    latest = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == doc.id)
        .order_by(desc(DocumentVersion.version_number))
        .first()
    )
    count = db.query(func.count(DocumentVersion.id)).filter(DocumentVersion.document_id == doc.id).scalar() or 1
    return _format_document_out(doc, latest, count)


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    document_id: str,
    current_user: User = Depends(require_permission(PERM_UPLOAD_DOCS)),
    db: Session = Depends(get_db)
):
    """Delete a document and its stored files."""
    doc = _get_document_or_404(document_id, current_user, db)

    # Clean up files on disk
    versions = db.query(DocumentVersion).filter(DocumentVersion.document_id == doc.id).all()
    for v in versions:
        if v.file_path and os.path.exists(v.file_path):
            try:
                os.remove(v.file_path)
            except OSError as err:
                logger.warning("Could not delete file %s: %s", v.file_path, err)

    doc_title = doc.title
    log_action(
        db=db,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action="DOCUMENT_DELETED",
        target_entity="documents",
        target_id=doc.id,
        details={"title": doc_title}
    )
    db.delete(doc)
    db.commit()

    return {"message": f"Document '{doc_title}' deleted successfully."}
