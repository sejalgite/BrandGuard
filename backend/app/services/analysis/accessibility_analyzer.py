"""
app/services/analysis/accessibility_analyzer.py
Deterministic Accessibility Analysis Engine.
Implements WCAG 2.1 contrast calculations, heading structure validation,
image alt-text checks, and link text clarity checks based on approved
Brand Accessibility Rules.

WCAG 2.1 Contrast Thresholds (Level AA):
  - Normal text (<18pt regular / <14pt bold): minimum 4.5:1
  - Large text  (>=18pt regular / >=14pt bold): minimum 3.0:1
  Contrast is computed only when an explicit foreground/background hex pair
  is stated in the document text. No contrast check is claimed when
  color information is unavailable.

Confidence values:
  - Heading hierarchy: 0.950 — structural analysis of extracted headings list
  - Vague link text:   0.910 — regex pattern match on common non-descriptive phrases
  - Color contrast:    0.990 — mathematical WCAG calculation (deterministic)
  - Alt-text missing:  0.950 — image extraction status indicates no text extracted
"""
import re
import logging
from typing import List, Dict, Any, Optional, Tuple

from app.models.finding import (
    DetectionCategory, SeverityLevel, FindingStatus, FindingSource, EvidenceEntityType
)
from app.models.constitution import BrandRule, EntityStatus, RuleCategory

logger = logging.getLogger(__name__)


def parse_hex_color(hex_str: str) -> Optional[Tuple[int, int, int]]:
    """Convert hex string (e.g. #FFFFFF or #FFF) to RGB tuple."""
    hex_clean = hex_str.lstrip("#").strip()
    if len(hex_clean) == 3:
        hex_clean = "".join([c * 2 for c in hex_clean])
    if len(hex_clean) != 6:
        return None
    try:
        r = int(hex_clean[0:2], 16)
        g = int(hex_clean[2:4], 16)
        b = int(hex_clean[4:6], 16)
        return (r, g, b)
    except ValueError:
        return None


def relative_luminance(rgb: Tuple[int, int, int]) -> float:
    """Calculate WCAG 2.1 relative luminance for an sRGB color."""
    linear = []
    for c in rgb:
        srgb = c / 255.0
        if srgb <= 0.04045:
            linear.append(srgb / 12.92)
        else:
            linear.append(((srgb + 0.055) / 1.055) ** 2.4)
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def calculate_contrast_ratio(hex1: str, hex2: str) -> Optional[float]:
    """Calculate WCAG contrast ratio between two hex colors."""
    rgb1 = parse_hex_color(hex1)
    rgb2 = parse_hex_color(hex2)
    if not rgb1 or not rgb2:
        return None

    l1 = relative_luminance(rgb1)
    l2 = relative_luminance(rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


class AccessibilityAnalyzer:
    """Deterministic analyzer for WCAG compliance, heading structure, and content clarity."""

    @classmethod
    def analyze(
        cls,
        segments: List[Dict[str, Any]],
        raw_text: str,
        rules: List[BrandRule],
        structured_content: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        findings = []

        # Filter strictly for ACTIVE accessibility rules
        access_rules = [
            r for r in rules
            if r.status == EntityStatus.ACTIVE and r.category == RuleCategory.ACCESSIBILITY
        ]
        if not access_rules or not segments:
            return findings

        primary_rule = access_rules[0]
        struct = structured_content or {}

        # 1. Heading Hierarchy Structure Validation
        # Confidence: 0.950 — structural analysis of extracted heading list.
        headings = struct.get("headings", [])
        if len(headings) >= 2:
            prev_level = 0
            for h in headings:
                curr_level = h.get("level", 1)
                # Flag when heading level jumps by more than 1 (e.g. H1 -> H3, skipping H2)
                if prev_level > 0 and (curr_level - prev_level) > 1:
                    heading_text = h.get("text", "")
                    char_start = raw_text.find(heading_text) if raw_text else 0
                    char_end = char_start + len(heading_text) if char_start >= 0 else len(heading_text)

                    findings.append({
                        "category": DetectionCategory.ACCESSIBILITY,
                        "severity": SeverityLevel.MEDIUM,
                        "confidence": 0.950,
                        "flagged_snippet": heading_text[:80],
                        "char_offset_start": max(0, char_start),
                        "char_offset_end": max(0, char_end),
                        "explanation": (
                            f"Skipped heading level in document structure: "
                            f"Heading '{heading_text}' is level H{curr_level} "
                            f"immediately following level H{prev_level}. "
                            f"WCAG 2.1 requires consecutive heading hierarchy "
                            f"(H{prev_level} -> H{prev_level + 1}). "
                            f"Governed by rule [{primary_rule.rule_code}]."
                        ),
                        "evidence_type": EvidenceEntityType.RULE,
                        "rule_id": primary_rule.id,
                        "fact_id": None,
                        "term_id": None,
                        "asset_id": None,
                        "cited_code": primary_rule.rule_code,
                        "source": FindingSource.DETERMINISTIC_ENGINE,
                        "status": FindingStatus.OPEN,
                        "segment_id": None,
                        "suggested_correction": f"Adjust heading '{heading_text}' to level H{prev_level + 1}",
                    })
                prev_level = curr_level

        # 2. Vague Link Text Detection (e.g. "click here", "read more")
        # Confidence: 0.910 — regex pattern match on common non-descriptive phrases.
        vague_link_pat = re.compile(
            r'\b(click\s+here|click\s+this\s+link|read\s+more|learn\s+more|more\s+info)\b',
            re.IGNORECASE
        )
        for seg in segments:
            text = seg.get("text", "")
            for match in vague_link_pat.finditer(text):
                snippet = match.group(0)
                base_offset = seg.get("char_start", 0)
                start = base_offset + match.start()
                end = base_offset + match.end()

                findings.append({
                    "category": DetectionCategory.ACCESSIBILITY,
                    "severity": SeverityLevel.LOW,
                    "confidence": 0.910,
                    "flagged_snippet": snippet,
                    "char_offset_start": max(0, start),
                    "char_offset_end": max(0, end),
                    "explanation": (
                        f"Non-descriptive link / CTA text '{snippet}'. "
                        f"WCAG Success Criterion 2.4.4 requires the purpose of each link "
                        f"to be determined from the link text alone. "
                        f"Governed by [{primary_rule.rule_code}]."
                    ),
                    "evidence_type": EvidenceEntityType.RULE,
                    "rule_id": primary_rule.id,
                    "fact_id": None,
                    "term_id": None,
                    "asset_id": None,
                    "cited_code": primary_rule.rule_code,
                    "source": FindingSource.DETERMINISTIC_ENGINE,
                    "status": FindingStatus.OPEN,
                    "segment_id": seg.get("segment_id"),
                    "suggested_correction": f"Replace with descriptive destination text, e.g. '{snippet.title()} for Architecture Specs'",
                })

        # 3. Color Contrast Verification in Explicit Design Specification Text
        # Only triggered when the document text contains an explicit
        # "text: #HEX on background: #HEX" or "foreground: #HEX, background: #HEX" pair.
        # NOTE: Contrast is NOT claimed as verified when color information is absent from text.
        # Confidence: 0.990 — mathematical WCAG calculation (deterministic).
        #
        # WCAG 2.1 Level AA thresholds:
        #   Normal text: 4.5:1
        #   Large text (>=18pt regular / >=14pt bold): 3.0:1
        #   The "large_text" keyword in the segment context triggers the 3:1 threshold.
        contrast_pair_pat = re.compile(
            r'(?:text|foreground|fg|color):\s*(#[A-Fa-f0-9]{3,6}).*?(?:background|bg|on):\s*(#[A-Fa-f0-9]{3,6})',
            re.IGNORECASE
        )
        large_text_pat = re.compile(r'\b(large\s+text|18\s*pt|14\s*pt\s+bold|heading)\b', re.IGNORECASE)

        for seg in segments:
            text = seg.get("text", "")
            for match in contrast_pair_pat.finditer(text):
                fg_hex = match.group(1)
                bg_hex = match.group(2)
                ratio = calculate_contrast_ratio(fg_hex, bg_hex)
                if ratio is None:
                    continue

                # Determine applicable WCAG threshold
                is_large_text = bool(large_text_pat.search(text))
                min_ratio = 3.0 if is_large_text else 4.5
                threshold_label = "large text (3:1)" if is_large_text else "normal text (4.5:1)"

                if ratio < min_ratio:
                    snippet = match.group(0)
                    base_offset = seg.get("char_start", 0)
                    start = base_offset + match.start()
                    end = base_offset + match.end()

                    findings.append({
                        "category": DetectionCategory.ACCESSIBILITY,
                        "severity": SeverityLevel.HIGH,
                        "confidence": 0.990,
                        "flagged_snippet": snippet,
                        "char_offset_start": max(0, start),
                        "char_offset_end": max(0, end),
                        "explanation": (
                            f"Insufficient color contrast: Ratio {ratio:.2f}:1 between "
                            f"{fg_hex} and {bg_hex} fails WCAG 2.1 Level AA minimum "
                            f"required contrast of {min_ratio}:1 for {threshold_label}. "
                            f"Governed by [{primary_rule.rule_code}]."
                        ),
                        "evidence_type": EvidenceEntityType.RULE,
                        "rule_id": primary_rule.id,
                        "fact_id": None,
                        "term_id": None,
                        "asset_id": None,
                        "cited_code": primary_rule.rule_code,
                        "source": FindingSource.DETERMINISTIC_ENGINE,
                        "status": FindingStatus.OPEN,
                        "segment_id": seg.get("segment_id"),
                        "suggested_correction": (
                            f"Increase contrast between {fg_hex} and {bg_hex} "
                            f"to at least {min_ratio}:1"
                        ),
                    })

        # 4. Image Alt-Text Check
        # When the structured content indicates image extraction was not possible
        # (e.g. OCR_UNAVAILABLE or OCR_FAILED), the document is likely a scanned image
        # with no machine-readable text — this is a critical accessibility gap.
        # Confidence: 0.950 — extraction status is a reliable indicator.
        extraction_status = struct.get("extraction_status", "")
        if extraction_status in ("OCR_UNAVAILABLE", "OCR_FAILED", "NO_TEXT_EXTRACTED"):
            findings.append({
                "category": DetectionCategory.ACCESSIBILITY,
                "severity": SeverityLevel.HIGH,
                "confidence": 0.950,
                "flagged_snippet": "Image document — no extractable text",
                "char_offset_start": 0,
                "char_offset_end": 0,
                "explanation": (
                    f"Document appears to be an image with no machine-readable text "
                    f"(extraction status: {extraction_status}). "
                    f"WCAG 1.1.1 requires a text alternative for all non-text content. "
                    f"An accessible alt-text description must be provided manually. "
                    f"Governed by [{primary_rule.rule_code}]."
                ),
                "evidence_type": EvidenceEntityType.RULE,
                "rule_id": primary_rule.id,
                "fact_id": None,
                "term_id": None,
                "asset_id": None,
                "cited_code": primary_rule.rule_code,
                "source": FindingSource.DETERMINISTIC_ENGINE,
                "status": FindingStatus.NEEDS_REVIEW,
                "segment_id": None,
                "suggested_correction": "Add descriptive alt text that conveys the content and function of the image.",
            })

        return findings
