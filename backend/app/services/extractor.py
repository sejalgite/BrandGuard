"""
app/services/extractor.py
Robust file validation, content extraction, and document structuring engine.
Supports TXT, DOCX, PDF, and Images (PNG/JPG/JPEG).
"""
import io
import os
import re
import uuid
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

import docx
import pymupdf as fitz  # PyMuPDF
from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None

logger = logging.getLogger(__name__)

# Supported extensions and magic byte signatures
ALLOWED_EXTENSIONS = {"txt", "docx", "pdf", "png", "jpg", "jpeg"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB


@dataclass
class TextSegment:
    segment_id: str
    page_number: int
    paragraph_index: int
    sentence_index: int
    text: str
    char_start: int
    char_end: int
    heading_context: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "page_number": self.page_number,
            "paragraph_index": self.paragraph_index,
            "sentence_index": self.sentence_index,
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "heading_context": self.heading_context,
        }


@dataclass
class ExtractionResult:
    status: str  # "COMPLETED", "EMPTY", "FAILED", "OCR_UNAVAILABLE"
    extracted_text: str = ""
    word_count: int = 0
    character_count: int = 0
    method: str = "NONE"
    metadata: Dict[str, Any] = field(default_factory=dict)
    structured_content: Dict[str, Any] = field(default_factory=dict)


def is_tesseract_available() -> bool:
    """Check whether Tesseract binary is available on the system."""
    if not pytesseract:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def validate_file(filename: str, content: bytes, declared_mime: Optional[str] = None) -> Tuple[str, str]:
    """
    Validate file extension, size, and content magic bytes.
    Returns (cleaned_extension, canonical_mime_type).
    Raises ValueError with user-friendly message on invalid input.
    """
    if not filename or "." not in filename:
        raise ValueError("Filename must have a valid extension.")

    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format '.{ext}'. Supported formats: {', '.join(sorted(ALLOWED_EXTENSIONS)).upper()}."
        )

    if len(content) == 0:
        raise ValueError("The uploaded file is empty (0 bytes).")

    if len(content) > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        raise ValueError(f"File size exceeds maximum limit of {max_mb} MB.")

    # Magic byte verification
    if ext == "pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("Corrupted PDF: Missing %PDF- header.")
        canonical_mime = "application/pdf"
    elif ext == "docx":
        # DOCX is an open packaging convention ZIP starting with PK\x03\x04
        if not content.startswith(b"PK\x03\x04"):
            raise ValueError("Corrupted DOCX: Invalid Word document format.")
        canonical_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif ext == "png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Corrupted PNG: Invalid PNG signature.")
        canonical_mime = "image/png"
    elif ext in {"jpg", "jpeg"}:
        if not (content.startswith(b"\xff\xd8\xff") or content[:2] == b"\xff\xd8"):
            raise ValueError("Corrupted JPEG: Invalid JPEG signature.")
        canonical_mime = "image/jpeg"
    elif ext == "txt":
        # Verify text decodability
        try:
            decode_text(content)
        except Exception:
            raise ValueError("Corrupted TXT: File contents could not be decoded as text.")
        canonical_mime = "text/plain"
    else:
        canonical_mime = declared_mime or "application/octet-stream"

    return ext, canonical_mime


def decode_text(content: bytes) -> str:
    """Safely decode plain text trying standard encodings in order."""
    encodings = ["utf-8-sig", "utf-8", "utf-16", "latin-1", "cp1252", "ascii"]
    for enc in encodings:
        try:
            return content.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", errors="replace")


def split_sentences(text: str) -> List[str]:
    """Split text into sentences while respecting common abbreviations."""
    if not text.strip():
        return []
    # Match sentence endings followed by space and uppercase or end of string
    raw_sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'])', text)
    cleaned = [s.strip() for s in raw_sentences if s.strip()]
    return cleaned if cleaned else [text.strip()]


def structure_document_content(
    raw_text: str,
    headings: List[Dict[str, Any]],
    pages_data: List[Dict[str, Any]],
    title_hint: Optional[str] = None
) -> Dict[str, Any]:
    """
    Construct stable structured text segments and metadata for downstream analysis.
    """
    segments: List[Dict[str, Any]] = []
    paragraphs_list: List[Dict[str, Any]] = []
    seg_idx = 1
    para_idx = 1
    current_heading = headings[0]["text"] if headings else None

    # If pages_data is provided (from PDF or multi-page formats)
    if pages_data:
        for p in pages_data:
            page_num = p.get("page_number", 1)
            page_text = p.get("text", "")
            paras = [para.strip() for para in page_text.split("\n\n") if para.strip()]
            for para in paras:
                # Check if this paragraph is a known heading
                matching_heading = next((h["text"] for h in headings if h["text"] == para), None)
                if matching_heading:
                    current_heading = matching_heading

                para_char_start = raw_text.find(para) if raw_text else 0
                para_char_end = para_char_start + len(para) if para_char_start >= 0 else len(para)

                paragraphs_list.append({
                    "paragraph_index": para_idx,
                    "page_number": page_num,
                    "text": para,
                    "heading_context": current_heading,
                    "char_start": max(0, para_char_start),
                    "char_end": max(0, para_char_end)
                })

                sentences = split_sentences(para)
                for s_idx, sentence in enumerate(sentences, start=1):
                    s_start = raw_text.find(sentence, max(0, para_char_start))
                    s_end = s_start + len(sentence) if s_start >= 0 else len(sentence)

                    seg = TextSegment(
                        segment_id=f"seg_{seg_idx}",
                        page_number=page_num,
                        paragraph_index=para_idx,
                        sentence_index=s_idx,
                        text=sentence,
                        char_start=max(0, s_start),
                        char_end=max(0, s_end),
                        heading_context=current_heading
                    )
                    segments.append(seg.to_dict())
                    seg_idx += 1
                para_idx += 1
    else:
        # Single-page/linear text structure
        paras = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        for para in paras:
            matching_heading = next((h["text"] for h in headings if h["text"] == para), None)
            if matching_heading:
                current_heading = matching_heading

            para_char_start = raw_text.find(para)
            para_char_end = para_char_start + len(para) if para_char_start >= 0 else len(para)

            paragraphs_list.append({
                "paragraph_index": para_idx,
                "page_number": 1,
                "text": para,
                "heading_context": current_heading,
                "char_start": max(0, para_char_start),
                "char_end": max(0, para_char_end)
            })

            sentences = split_sentences(para)
            for s_idx, sentence in enumerate(sentences, start=1):
                s_start = raw_text.find(sentence, max(0, para_char_start))
                s_end = s_start + len(sentence) if s_start >= 0 else len(sentence)

                seg = TextSegment(
                    segment_id=f"seg_{seg_idx}",
                    page_number=1,
                    paragraph_index=para_idx,
                    sentence_index=s_idx,
                    text=sentence,
                    char_start=max(0, s_start),
                    char_end=max(0, s_end),
                    heading_context=current_heading
                )
                segments.append(seg.to_dict())
                seg_idx += 1
            para_idx += 1

    # Extract title from title_hint or first heading or first line
    doc_title = title_hint
    if not doc_title and headings:
        doc_title = headings[0]["text"]
    if not doc_title and paragraphs_list:
        first_line = paragraphs_list[0]["text"].split("\n")[0]
        if len(first_line) < 120:
            doc_title = first_line

    words = len(raw_text.split()) if raw_text else 0
    chars = len(raw_text)

    return {
        "title": doc_title or "Untitled Document",
        "total_segments": len(segments),
        "total_paragraphs": len(paragraphs_list),
        "total_pages": max([p.get("page_number", 1) for p in pages_data], default=1),
        "headings": headings,
        "paragraphs": paragraphs_list,
        "segments": segments,
        "word_count": words,
        "character_count": chars,
    }


class ContentExtractor:
    """Unified extractor service for TXT, DOCX, PDF, and Images."""

    @classmethod
    def extract(cls, file_bytes: bytes, filename: str, mime_type: Optional[str] = None) -> ExtractionResult:
        """
        Main entry point. Validates file and delegates to format-specific handler.
        Never crashes or raises unhandled exceptions.
        """
        try:
            ext, canonical_mime = validate_file(filename, file_bytes, mime_type)
        except ValueError as ve:
            return ExtractionResult(
                status="FAILED",
                method="VALIDATION",
                metadata={"error": str(ve), "validation_failed": True}
            )

        try:
            if ext == "txt":
                return cls._extract_txt(file_bytes, filename)
            elif ext == "docx":
                return cls._extract_docx(file_bytes, filename)
            elif ext == "pdf":
                return cls._extract_pdf(file_bytes, filename)
            elif ext in {"png", "jpg", "jpeg"}:
                return cls._extract_image(file_bytes, filename)
            else:
                return ExtractionResult(
                    status="FAILED",
                    metadata={"error": f"Unsupported extension: {ext}"}
                )
        except Exception as exc:
            logger.exception("Unexpected error during extraction of %s", filename)
            return ExtractionResult(
                status="FAILED",
                metadata={"error": f"Extraction failure: {str(exc)}"}
            )

    @classmethod
    def _extract_txt(cls, content: bytes, filename: str) -> ExtractionResult:
        text = decode_text(content).strip()
        if not text:
            return ExtractionResult(
                status="EMPTY",
                extracted_text="",
                method="DIRECT_TEXT",
                metadata={"pages": 1, "empty_document": True}
            )

        headings = []
        # Infer potential headings: short single-line lines surrounded by empty lines
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            line_str = line.strip()
            if 0 < len(line_str) <= 60 and not line_str.endswith("."):
                headings.append({"text": line_str, "level": 1, "page": 1})

        structured = structure_document_content(text, headings, [], title_hint=os.path.splitext(filename)[0])
        return ExtractionResult(
            status="COMPLETED",
            extracted_text=text,
            word_count=structured["word_count"],
            character_count=structured["character_count"],
            method="DIRECT_TEXT",
            metadata={"pages": 1, "encoding": "detected"},
            structured_content=structured
        )

    @classmethod
    def _extract_docx(cls, content: bytes, filename: str) -> ExtractionResult:
        try:
            doc = docx.Document(io.BytesIO(content))
        except Exception as e:
            return ExtractionResult(
                status="FAILED",
                method="DOCX_PARSER",
                metadata={"error": f"Corrupted Word document structure: {str(e)}"}
            )

        headings: List[Dict[str, Any]] = []
        paragraphs_text: List[str] = []

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            style_name = p.style.name.lower() if p.style else ""
            if "heading" in style_name or "title" in style_name:
                level = 1
                level_match = re.search(r'\d+', style_name)
                if level_match:
                    level = int(level_match.group(0))
                headings.append({"text": text, "level": level, "page": 1})
            paragraphs_text.append(text)

        # Also extract table text if present
        for table in doc.tables:
            for row in table.rows:
                row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_cells:
                    paragraphs_text.append(" | ".join(row_cells))

        full_text = "\n\n".join(paragraphs_text).strip()
        if not full_text:
            return ExtractionResult(
                status="EMPTY",
                extracted_text="",
                method="DOCX_PARSER",
                metadata={"pages": 1, "empty_document": True}
            )

        structured = structure_document_content(full_text, headings, [], title_hint=os.path.splitext(filename)[0])
        return ExtractionResult(
            status="COMPLETED",
            extracted_text=full_text,
            word_count=structured["word_count"],
            character_count=structured["character_count"],
            method="DOCX_PARSER",
            metadata={"pages": 1, "paragraphs_count": len(doc.paragraphs)},
            structured_content=structured
        )

    @classmethod
    def _extract_pdf(cls, content: bytes, filename: str) -> ExtractionResult:
        try:
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception as e:
            return ExtractionResult(
                status="FAILED",
                method="PDF_PARSER",
                metadata={"error": f"Corrupted PDF file: {str(e)}"}
            )

        total_pages = len(doc)
        if total_pages == 0:
            return ExtractionResult(
                status="EMPTY",
                extracted_text="",
                method="PDF_PARSER",
                metadata={"pages": 0, "empty_document": True}
            )

        pages_data: List[Dict[str, Any]] = []
        headings: List[Dict[str, Any]] = []
        extracted_pages_text: List[str] = []
        ocr_performed = False
        tesseract_available = is_tesseract_available()

        for page_idx in range(total_pages):
            page = doc[page_idx]
            page_num = page_idx + 1
            page_text = page.get_text("text").strip()

            # Check if page has no text layer (scanned page)
            if not page_text or len(page_text) < 15:
                if tesseract_available:
                    try:
                        # Render page to pixmap image for OCR
                        pix = page.get_pixmap(dpi=150)
                        img = Image.open(io.BytesIO(pix.tobytes("png")))
                        ocr_text = pytesseract.image_to_string(img).strip()
                        if ocr_text:
                            page_text = ocr_text
                            ocr_performed = True
                    except Exception as ocr_err:
                        logger.warning("OCR failed on PDF page %d: %s", page_num, ocr_err)
                else:
                    # Tesseract not available: page remains empty or partial
                    pass

            # Extract headings by font size blocks
            try:
                blocks = page.get_text("dict").get("blocks", [])
                for b in blocks:
                    for line in b.get("lines", []):
                        for span in line.get("spans", []):
                            font_size = span.get("size", 10)
                            span_text = span.get("text", "").strip()
                            if font_size >= 14 and 3 <= len(span_text) <= 80:
                                headings.append({
                                    "text": span_text,
                                    "level": 1 if font_size >= 18 else 2,
                                    "page": page_num
                                })
            except Exception:
                pass

            if page_text:
                extracted_pages_text.append(page_text)
                pages_data.append({"page_number": page_num, "text": page_text})

        full_text = "\n\n".join(extracted_pages_text).strip()

        # If PDF is completely empty and had no text layer
        if not full_text:
            if not tesseract_available:
                return ExtractionResult(
                    status="OCR_UNAVAILABLE",
                    extracted_text="",
                    method="PDF_PARSER",
                    metadata={
                        "pages": total_pages,
                        "ocr_required": True,
                        "ocr_available": False,
                        "instructions": "This PDF contains scanned or image-only pages with no text layer. Install Tesseract-OCR and add it to system PATH to enable automatic optical character recognition.",
                        "error": "Tesseract OCR engine is not installed or not found on system PATH."
                    }
                )
            return ExtractionResult(
                status="EMPTY",
                extracted_text="",
                method="PDF_PARSER",
                metadata={"pages": total_pages, "empty_document": True}
            )

        method = "HYBRID_PDF_OCR" if ocr_performed else "PDF_PARSER"
        structured = structure_document_content(full_text, headings, pages_data, title_hint=os.path.splitext(filename)[0])

        return ExtractionResult(
            status="COMPLETED",
            extracted_text=full_text,
            word_count=structured["word_count"],
            character_count=structured["character_count"],
            method=method,
            metadata={
                "pages": total_pages,
                "ocr_performed": ocr_performed,
                "ocr_available": tesseract_available
            },
            structured_content=structured
        )

    @classmethod
    def _extract_image(cls, content: bytes, filename: str) -> ExtractionResult:
        try:
            image = Image.open(io.BytesIO(content))
            image.verify()
            image = Image.open(io.BytesIO(content))  # Reopen after verify
        except Exception as e:
            return ExtractionResult(
                status="FAILED",
                method="IMAGE_PARSER",
                metadata={"error": f"Corrupted or invalid image file: {str(e)}"}
            )

        if not is_tesseract_available():
            return ExtractionResult(
                status="OCR_UNAVAILABLE",
                extracted_text="",
                method="TESSERACT_OCR",
                metadata={
                    "ocr_required": True,
                    "ocr_available": False,
                    "instructions": "Image text extraction requires the Tesseract OCR engine. Install Tesseract-OCR (https://github.com/UB-Mannheim/tesseract/wiki) and ensure 'tesseract.exe' is on system PATH.",
                    "error": "Tesseract OCR engine is not installed or not found on system PATH."
                }
            )

        try:
            text = pytesseract.image_to_string(image).strip()
            # Try to get OCR confidence data
            confidence = None
            try:
                data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
                confs = [int(c) for c in data.get("conf", []) if str(c).isdigit() and int(c) >= 0]
                if confs:
                    confidence = round(sum(confs) / len(confs), 2)
            except Exception:
                pass

            if not text:
                return ExtractionResult(
                    status="EMPTY",
                    extracted_text="",
                    method="TESSERACT_OCR",
                    metadata={"pages": 1, "empty_document": True, "ocr_confidence": confidence}
                )

            structured = structure_document_content(text, [], [], title_hint=os.path.splitext(filename)[0])
            return ExtractionResult(
                status="COMPLETED",
                extracted_text=text,
                word_count=structured["word_count"],
                character_count=structured["character_count"],
                method="TESSERACT_OCR",
                metadata={
                    "pages": 1,
                    "ocr_performed": True,
                    "ocr_confidence": confidence,
                    "dimensions": f"{image.width}x{image.height}",
                },
                structured_content=structured
            )
        except Exception as ocr_err:
            return ExtractionResult(
                status="FAILED",
                method="TESSERACT_OCR",
                metadata={"error": f"OCR processing failed: {str(ocr_err)}"}
            )

