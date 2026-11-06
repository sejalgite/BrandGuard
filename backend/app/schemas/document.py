"""
app/schemas/document.py
Pydantic schemas for Document and DocumentVersion management and ingestion.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class TextSegmentOut(BaseModel):
    segment_id: str
    page_number: int
    paragraph_index: int
    sentence_index: int
    text: str
    char_start: int
    char_end: int
    heading_context: Optional[str] = None


class StructuredContentOut(BaseModel):
    title: Optional[str] = None
    total_segments: int = 0
    total_paragraphs: int = 0
    total_pages: int = 1
    headings: List[Dict[str, Any]] = []
    paragraphs: List[Dict[str, Any]] = []
    segments: List[TextSegmentOut] = []
    word_count: int = 0
    character_count: int = 0


class DocumentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    document_id: str
    version_number: int
    original_filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    extraction_status: str
    extracted_text: Optional[str] = None
    word_count: int = 0
    character_count: int = 0
    version_status: str
    is_locked: bool
    created_at: datetime
    extraction_metadata: Optional[Dict[str, Any]] = None
    structured_content: Optional[Dict[str, Any]] = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    creator_id: str
    title: str
    content_type: str
    lifecycle_status: str
    created_at: datetime
    updated_at: datetime
    latest_version: Optional[DocumentVersionOut] = None
    versions_count: int = 1


class DocumentUploadResponse(BaseModel):
    document: DocumentOut
    version: DocumentVersionOut
    message: str


class DocumentUpdateTitle(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
