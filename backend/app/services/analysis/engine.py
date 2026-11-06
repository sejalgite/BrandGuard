"""
app/services/analysis/engine.py
Master Brand Analysis Engine.
Orchestrates hybrid deterministic and contextual AI checks across all 6 brand compliance categories.
Enforces multi-tenant isolation, Constitution traceability, and referential integrity.

Analysis completeness:
  - "FULL"                  — Deterministic + LLM contextual (Ollama available and model ready)
  - "DETERMINISTIC_ONLY"    — All 6 deterministic analyzers; Ollama unavailable or model missing

Finding verification:
  Each candidate finding is validated before persistence:
  - flagged_snippet is non-empty and present in raw_text (case-insensitive)
  - char_offset_start and char_offset_end are within document bounds
  - flagged_snippet length is consistent with the stated offset range
  Invalid findings are discarded (counted in execution_metadata["discarded_findings"]).
"""
import io
import os
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.document import Document, DocumentVersion
from app.models.constitution import (
    BrandConstitution, BrandRule, FactRegistry, TermBank, BrandAsset, EntityStatus
)
from app.models.finding import (
    ReviewJob, Finding, SuggestedCorrection, DetectionCategory, SeverityLevel,
    FindingStatus, FindingSource, EvidenceEntityType
)
from app.audit.audit_logger import log_action
from app.services.analysis.ollama_client import LocalOllamaClient
from app.services.analysis.terminology_analyzer import TerminologyAnalyzer
from app.services.analysis.claims_analyzer import ClaimsAnalyzer
from app.services.analysis.tone_analyzer import ToneAnalyzer
from app.services.analysis.messaging_analyzer import MessagingAnalyzer
from app.services.analysis.visual_analyzer import VisualAnalyzer
from app.services.analysis.accessibility_analyzer import AccessibilityAnalyzer

logger = logging.getLogger(__name__)

SEVERITY_DEDUCTIONS = {
    SeverityLevel.CRITICAL: 20.0,
    SeverityLevel.HIGH: 10.0,
    SeverityLevel.MEDIUM: 5.0,
    SeverityLevel.LOW: 2.0,
    SeverityLevel.INFO: 0.5,
}

# MIME types that represent uploaded image files
_IMAGE_MIME_PREFIXES = ("image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/tiff")


def _load_image_bytes(file_path: Optional[str]) -> Optional[bytes]:
    """
    Safely read image bytes from the stored file path.
    Returns None if path is None, missing, or unreadable.
    """
    if not file_path:
        return None
    try:
        with open(file_path, "rb") as f:
            return f.read()
    except (OSError, IOError) as exc:
        logger.warning("Could not read image file %s: %s", file_path, exc)
        return None


def _verify_finding(candidate: Dict[str, Any], raw_text: str) -> bool:
    """
    Validate a candidate finding before persistence.

    Rules:
    1. flagged_snippet must be non-empty.
    2. flagged_snippet must appear in raw_text (case-insensitive) — skipped for image/dimension findings.
    3. char_offset_start and char_offset_end must be within [0, len(raw_text)] if raw_text exists.
    4. The span length must be consistent with flagged_snippet length (±20 chars tolerance for whitespace).

    Returns True if the finding is valid, False if it should be discarded.
    """
    snippet = candidate.get("flagged_snippet", "")
    if not snippet or not snippet.strip():
        logger.debug("Discarding finding: empty flagged_snippet")
        return False

    start = candidate.get("char_offset_start")
    end = candidate.get("char_offset_end")

    # For image/dimension findings (char_offset_start=0, char_offset_end=0), skip text check
    if start == 0 and end == 0:
        return True

    if raw_text:
        # Verify snippet exists in raw_text (case-insensitive)
        if snippet.lower() not in raw_text.lower():
            logger.debug("Discarding finding: snippet '%s' not found in raw_text", snippet[:50])
            return False

        # Verify offset bounds
        text_len = len(raw_text)
        if start is not None and end is not None:
            if start < 0 or end < 0 or start > text_len or end > text_len:
                logger.debug("Discarding finding: offsets [%s, %s] out of bounds (text_len=%s)", start, end, text_len)
                return False

            # Verify consistency between span length and snippet length (±20 tolerance)
            span_len = end - start
            snippet_len = len(snippet)
            if abs(span_len - snippet_len) > 20:
                logger.debug(
                    "Discarding finding: span length %s inconsistent with snippet length %s",
                    span_len, snippet_len
                )
                return False

    return True


def _deduplicate_cross_category(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove cross-category duplicates where the same flagged_snippet at the same offsets
    appears more than once (e.g. duplicate passes over the same segment).
    """
    seen = set()
    unique = []
    for c in candidates:
        key = (
            c.get("flagged_snippet", "").lower().strip(),
            c.get("char_offset_start"),
            c.get("char_offset_end"),
            c.get("category"),
        )
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


class BrandAnalysisEngine:
    """Master orchestrator for multi-category Brand Constitution compliance analysis."""

    def __init__(self, db: Session):
        self.db = db
        self.ollama = LocalOllamaClient()

    def run_analysis(
        self,
        document_id: str,
        version_id: str,
        organization_id: str,
        actor_id: str,
        trigger_type: str = "MANUAL"
    ) -> ReviewJob:
        """
        Execute full compliance analysis on a specific document version.
        Guarantees organization scoping and traceable evidence linking.
        """
        start_time = time.perf_counter()

        # 1. Load Document and Version with Tenant Isolation
        doc = (
            self.db.query(Document)
            .filter(Document.id == document_id, Document.organization_id == organization_id)
            .first()
        )
        if not doc:
            raise ValueError(f"Document {document_id} not found in organization.")

        version = (
            self.db.query(DocumentVersion)
            .filter(
                DocumentVersion.id == version_id,
                DocumentVersion.document_id == doc.id,
                DocumentVersion.organization_id == organization_id
            )
            .first()
        )
        if not version:
            raise ValueError(f"Document version {version_id} not found.")

        # 2. Load Active Brand Constitution
        constitution = (
            self.db.query(BrandConstitution)
            .filter(
                BrandConstitution.organization_id == organization_id,
                BrandConstitution.is_active == True
            )
            .order_by(desc(BrandConstitution.created_at))
            .first()
        )
        if not constitution:
            raise ValueError("No active Brand Constitution configured for this organization.")

        # 3. Create ReviewJob Record
        job = ReviewJob(
            id=uuid.uuid4(),
            organization_id=uuid.UUID(organization_id),
            document_id=doc.id,
            version_id=version.id,
            status="RUNNING",
            trigger_type=trigger_type,
            started_at=datetime.now(timezone.utc),
            categories_analyzed=[],
            execution_metadata={},
            total_findings=0
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        try:
            # 4. Load Active Constitution Entities (Strictly ACTIVE only)
            rules = (
                self.db.query(BrandRule)
                .filter(
                    BrandRule.organization_id == organization_id,
                    BrandRule.constitution_id == constitution.id,
                    BrandRule.status == EntityStatus.ACTIVE
                )
                .all()
            )
            # Facts: load ALL (active, expired, draft) — analyzers handle status filtering internally.
            # Only ACTIVE facts are used as approved ground truth; expired/draft are flagged or ignored.
            facts = (
                self.db.query(FactRegistry)
                .filter(
                    FactRegistry.organization_id == organization_id,
                    FactRegistry.constitution_id == constitution.id,
                )
                .all()
            )
            terms = (
                self.db.query(TermBank)
                .filter(
                    TermBank.organization_id == organization_id,
                    TermBank.constitution_id == constitution.id,
                    TermBank.status == EntityStatus.ACTIVE
                )
                .all()
            )
            assets = (
                self.db.query(BrandAsset)
                .filter(
                    BrandAsset.organization_id == organization_id,
                    BrandAsset.constitution_id == constitution.id,
                    BrandAsset.status == EntityStatus.ACTIVE
                )
                .all()
            )

            # 5. Extract Segments and Content
            raw_text = version.extracted_text or version.raw_content or ""
            structured_content = version.structured_content or {}
            segments = structured_content.get("segments", [])

            # Fallback if segments empty: generate simple paragraph segments
            if not segments and raw_text:
                paras = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
                seg_idx = 1
                curr_offset = 0
                for p_idx, p in enumerate(paras, 1):
                    p_start = raw_text.find(p, curr_offset)
                    p_start = p_start if p_start >= 0 else curr_offset
                    p_end = p_start + len(p)
                    segments.append({
                        "segment_id": f"seg_{seg_idx}",
                        "paragraph_index": p_idx,
                        "sentence_index": 1,
                        "text": p,
                        "char_start": p_start,
                        "char_end": p_end
                    })
                    curr_offset = p_end
                    seg_idx += 1

            # 6. Load image bytes if this version is an image file (for Pillow pixel analysis)
            image_bytes: Optional[bytes] = None
            mime = (version.mime_type or "").lower()
            if any(mime.startswith(prefix) for prefix in _IMAGE_MIME_PREFIXES):
                image_bytes = _load_image_bytes(version.file_path)
                if image_bytes:
                    logger.info("Loaded %d bytes for pixel color analysis", len(image_bytes))

            # 7. Check Ollama availability once (shared across analyzers)
            ollama_health = self.ollama.check_health()
            ollama_available = ollama_health.get("available") and ollama_health.get("model_ready")

            # 8. Execute All 6 Compliance Analyzers
            candidates: List[Dict[str, Any]] = []

            # Category 1: Terminology
            cat_start = time.perf_counter()
            term_findings = TerminologyAnalyzer.analyze(segments, raw_text, terms)
            candidates.extend(term_findings)
            term_duration = time.perf_counter() - cat_start

            # Category 2: Claims & Facts
            cat_start = time.perf_counter()
            claim_findings = ClaimsAnalyzer.analyze(segments, raw_text, facts, rules)
            candidates.extend(claim_findings)
            claim_duration = time.perf_counter() - cat_start

            # Category 3: Tone & Voice
            cat_start = time.perf_counter()
            tone_findings = ToneAnalyzer.analyze(
                segments, raw_text, rules,
                self.ollama if ollama_available else None
            )
            candidates.extend(tone_findings)
            tone_duration = time.perf_counter() - cat_start

            # Category 4: Messaging Alignment
            cat_start = time.perf_counter()
            msg_findings = MessagingAnalyzer.analyze(
                segments, raw_text, rules,
                self.ollama if ollama_available else None
            )
            candidates.extend(msg_findings)
            msg_duration = time.perf_counter() - cat_start

            # Category 5: Visual Consistency (pass image bytes for pixel analysis)
            cat_start = time.perf_counter()
            visual_findings = VisualAnalyzer.analyze(
                segments, raw_text, assets,
                version.extraction_metadata,
                image_bytes=image_bytes
            )
            candidates.extend(visual_findings)
            visual_duration = time.perf_counter() - cat_start

            # Category 6: Accessibility
            cat_start = time.perf_counter()
            access_findings = AccessibilityAnalyzer.analyze(
                segments, raw_text, rules, structured_content
            )
            candidates.extend(access_findings)
            access_duration = time.perf_counter() - cat_start

            # 9. Deduplicate cross-category duplicates
            candidates = _deduplicate_cross_category(candidates)

            # 10. Verify and Persist Valid Findings
            persisted_findings: List[Finding] = []
            discarded_count = 0
            score_deductions = 0.0

            for c in candidates:
                # Validate finding before persistence
                if not _verify_finding(c, raw_text):
                    discarded_count += 1
                    continue

                fid = uuid.uuid4()
                finding = Finding(
                    id=fid,
                    organization_id=uuid.UUID(organization_id),
                    constitution_id=constitution.id,
                    document_id=doc.id,
                    version_id=version.id,
                    job_id=job.id,
                    category=c["category"],
                    severity=c["severity"],
                    confidence=c["confidence"],
                    flagged_snippet=c["flagged_snippet"][:500],
                    char_offset_start=c.get("char_offset_start"),
                    char_offset_end=c.get("char_offset_end"),
                    explanation=c["explanation"],
                    evidence_type=c["evidence_type"],
                    rule_id=c.get("rule_id"),
                    fact_id=c.get("fact_id"),
                    term_id=c.get("term_id"),
                    asset_id=c.get("asset_id"),
                    cited_code=c["cited_code"],
                    source=c.get("source", FindingSource.DETERMINISTIC_ENGINE),
                    status=c.get("status", FindingStatus.OPEN),
                    segment_id=c.get("segment_id"),
                    suggested_correction=c.get("suggested_correction"),
                    verified_by_gate=True  # Passed the verification gate
                )
                self.db.add(finding)
                persisted_findings.append(finding)

                # If suggested correction is present, also add to suggested_corrections table
                if c.get("suggested_correction"):
                    corr = SuggestedCorrection(
                        id=uuid.uuid4(),
                        organization_id=uuid.UUID(organization_id),
                        finding_id=fid,
                        option_label="Approved Standard",
                        suggested_text=c["suggested_correction"],
                        intent_preserved=True,
                        routing_action="APPLY_SUGGESTION"
                    )
                    self.db.add(corr)

                score_deductions += SEVERITY_DEDUCTIONS.get(c["severity"], 2.0)

            # 11. Compute Brand Health Score (0–100)
            health_score = max(0.0, round(100.0 - score_deductions, 2))
            version.brand_health_score = health_score

            total_elapsed = time.perf_counter() - start_time

            # Determine analysis completeness
            if ollama_available:
                analysis_completeness = "FULL"
                llm_status = "AVAILABLE"
            else:
                analysis_completeness = "DETERMINISTIC_ONLY"
                llm_status = "UNAVAILABLE"

            # 12. Update ReviewJob
            job.status = "COMPLETED"
            job.completed_at = datetime.now(timezone.utc)
            job.total_findings = len(persisted_findings)
            job.categories_analyzed = [
                DetectionCategory.TONE.value,
                DetectionCategory.TERMINOLOGY.value,
                DetectionCategory.MESSAGING.value,
                DetectionCategory.VISUAL.value,
                DetectionCategory.ACCESSIBILITY.value,
                DetectionCategory.CLAIMS.value,
            ]
            job.execution_metadata = {
                "elapsed_seconds": round(total_elapsed, 3),
                "brand_health_score": health_score,
                "segments_analyzed": len(segments),
                "words_analyzed": version.word_count,
                "category_durations_ms": {
                    "terminology": round(term_duration * 1000, 1),
                    "claims": round(claim_duration * 1000, 1),
                    "tone": round(tone_duration * 1000, 1),
                    "messaging": round(msg_duration * 1000, 1),
                    "visual": round(visual_duration * 1000, 1),
                    "accessibility": round(access_duration * 1000, 1),
                },
                "local_ollama": ollama_health,
                "contextual_llm_status": llm_status,
                "analysis_completeness": analysis_completeness,
                "constitution_version": constitution.version,
                "constitution_id": str(constitution.id),
                "validated_findings": len(persisted_findings),
                "discarded_findings": discarded_count,
                "image_pixel_analysis": image_bytes is not None,
            }

            # 13. Audit Log
            log_action(
                db=self.db,
                organization_id=uuid.UUID(organization_id),
                actor_id=uuid.UUID(actor_id) if actor_id else None,
                action="ANALYSIS_RUN_COMPLETED",
                target_entity="review_jobs",
                target_id=job.id,
                details={
                    "document_id": str(doc.id),
                    "version_id": str(version.id),
                    "total_findings": len(persisted_findings),
                    "discarded_findings": discarded_count,
                    "brand_health_score": health_score,
                    "analysis_completeness": analysis_completeness,
                    "elapsed_seconds": round(total_elapsed, 3)
                }
            )

            self.db.commit()
            self.db.refresh(job)
            self.db.refresh(version)
            return job

        except Exception as exc:
            self.db.rollback()
            logger.exception("Analysis execution failed on doc %s ver %s", document_id, version_id)
            job.status = "FAILED"
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = str(exc)
            self.db.commit()
            raise
