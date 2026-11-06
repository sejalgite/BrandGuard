"""
app/services/analysis/terminology_analyzer.py
Deterministic Term Bank matching engine.
Detects prohibited terms, incorrect naming, and suggests preferred alternatives.
"""
import re
import logging
from typing import List, Dict, Any, Optional

from app.models.finding import (
    DetectionCategory, SeverityLevel, FindingStatus, FindingSource, EvidenceEntityType
)
from app.models.constitution import TermBank, EntityStatus

logger = logging.getLogger(__name__)


class TerminologyAnalyzer:
    """Deterministic analyzer for brand terminology and prohibited vocabulary."""

    @classmethod
    def analyze(
        cls,
        segments: List[Dict[str, Any]],
        raw_text: str,
        terms: List[TermBank]
    ) -> List[Dict[str, Any]]:
        """
        Scan text segments against active approved Term Bank entries.
        Only active approved terms are evaluated.
        """
        findings = []

        # Filter strictly for ACTIVE approved terms
        active_terms = [t for t in terms if t.status == EntityStatus.ACTIVE]
        if not active_terms or not segments:
            return findings

        for term in active_terms:
            prohibited = term.prohibited_term.strip()
            if not prohibited:
                continue

            flags = 0 if term.is_case_sensitive else re.IGNORECASE
            pattern_str = r'\b' + re.escape(prohibited) + r'\b'

            try:
                pattern = re.compile(pattern_str, flags)
            except re.error as e:
                logger.warning("Invalid regex for term %s: %s", term.term_code, e)
                continue

            # Check each structured segment to maintain exact segment ID traceability
            for seg in segments:
                text = seg.get("text", "")
                if not text:
                    continue

                for match in pattern.finditer(text):
                    matched_snippet = match.group(0)
                    seg_start = match.start()
                    seg_end = match.end()

                    # Calculate global document character offset
                    base_offset = seg.get("char_start", 0)
                    global_start = base_offset + seg_start
                    global_end = base_offset + seg_end

                    # Ensure character bounds align with raw_text if present
                    if raw_text and global_start < len(raw_text):
                        actual_snippet = raw_text[global_start:global_end]
                        if actual_snippet.lower() == matched_snippet.lower():
                            matched_snippet = actual_snippet

                    explanation = (
                        f"Found prohibited term '{matched_snippet}'. "
                        f"Brand guidelines require using the approved term '{term.preferred_term}' instead."
                    )
                    if term.usage_context:
                        explanation += f" Context: {term.usage_context}."

                    findings.append({
                        "category": DetectionCategory.TERMINOLOGY,
                        "severity": SeverityLevel.HIGH,
                        "confidence": 0.980,
                        "flagged_snippet": matched_snippet,
                        "char_offset_start": max(0, global_start),
                        "char_offset_end": max(0, global_end),
                        "explanation": explanation,
                        "evidence_type": EvidenceEntityType.TERM,
                        "term_id": term.id,
                        "rule_id": None,
                        "fact_id": None,
                        "asset_id": None,
                        "cited_code": term.term_code,
                        "source": FindingSource.DETERMINISTIC_ENGINE,
                        "status": FindingStatus.OPEN,
                        "segment_id": seg.get("segment_id"),
                        "suggested_correction": term.preferred_term,
                    })

        return findings

