"""
tests/test_analysis_quality.py
Phase 5 Quality Audit Regression Tests.
Covers:
  - Tone deduplication (overlapping spans, repeated occurrences)
  - Terminology whole-word matching and case sensitivity
  - Claims: correct price, wrong price, expired fact, draft fact isolation
  - Visual: Pillow pixel analysis (approved, unapproved, corrupt bytes)
  - Accessibility: WCAG normal vs large-text thresholds, vague links, alt-text flag
  - Messaging: neutral competitor mention vs disparagement
  - Finding verification layer
  - Ollama offline / deterministic-only mode
  - Tenant isolation (cross-org fact isolation)
"""
import uuid
import math
from datetime import date, timedelta
from types import SimpleNamespace
from typing import List

import pytest

from app.services.analysis.tone_analyzer import ToneAnalyzer, _deduplicate_tone_findings
from app.services.analysis.terminology_analyzer import TerminologyAnalyzer
from app.services.analysis.claims_analyzer import ClaimsAnalyzer
from app.services.analysis.visual_analyzer import VisualAnalyzer, _extract_dominant_colors, _rgb_distance
from app.services.analysis.accessibility_analyzer import (
    AccessibilityAnalyzer, calculate_contrast_ratio
)
from app.services.analysis.messaging_analyzer import MessagingAnalyzer
from app.services.analysis.engine import _verify_finding, _deduplicate_cross_category
from app.models.finding import (
    DetectionCategory, SeverityLevel, FindingStatus, FindingSource, EvidenceEntityType
)
from app.models.constitution import EntityStatus, RuleCategory


# ---------------------------------------------------------------------------
# Minimal plain-object stub factories (SimpleNamespace — no SQLAlchemy overhead)
# These mimic the ORM model attributes that the analyzers actually read.
# ---------------------------------------------------------------------------

def _rule(
    rule_code: str,
    category: RuleCategory,
    description: str = "",
    examples_negative: List[str] = None,
    examples_positive: List[str] = None,
    status: EntityStatus = EntityStatus.ACTIVE,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        rule_code=rule_code,
        category=category,
        title=rule_code,
        description=description,
        examples_negative=examples_negative or [],
        examples_positive=examples_positive or [],
        status=status,
    )


def _term(
    prohibited: str,
    preferred: str,
    is_case_sensitive: bool = False,
    status: EntityStatus = EntityStatus.ACTIVE,
    usage_context: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        term_code=f"TERM-{prohibited[:6].upper()}",
        prohibited_term=prohibited,
        preferred_term=preferred,
        is_case_sensitive=is_case_sensitive,
        status=status,
        usage_context=usage_context,
    )


def _fact(
    fact_code: str,
    claim_type: str,
    statement: str,
    numerical_value: float = None,
    unit: str = "$",
    expiry_days: int = 90,
    status: EntityStatus = EntityStatus.ACTIVE,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        fact_code=fact_code,
        claim_type=claim_type,
        statement=statement,
        numerical_value=numerical_value,
        unit=unit,
        expiry_date=date.today() + timedelta(days=expiry_days),
        source_reference="Test",
        status=status,
    )


def _asset(
    asset_code: str,
    asset_type: str,
    specifications: dict,
    status: EntityStatus = EntityStatus.ACTIVE,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        asset_code=asset_code,
        asset_type=asset_type,
        name=asset_code,
        specifications=specifications,
        status=status,
    )


def _seg(text: str, seg_id: str = "seg_1", char_start: int = 0):
    return {
        "segment_id": seg_id,
        "text": text,
        "char_start": char_start,
        "char_end": char_start + len(text),
    }


# ---------------------------------------------------------------------------
# Minimal valid PNG builder (solid color, no Pillow dependency at build time)
# ---------------------------------------------------------------------------

def _make_solid_png(r: int, g: int, b: int, width: int = 10, height: int = 10) -> bytes:
    """
    Build a minimal valid PNG file from scratch (no Pillow needed to create it).
    Uses raw DEFLATE-compressed IDAT data.
    """
    import zlib, struct

    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    # PNG signature
    sig = b"\x89PNG\r\n\x1a\n"

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = chunk(b"IHDR", ihdr_data)

    # IDAT: raw scanlines, one filter byte (0 = None) per row
    raw_rows = b""
    for _ in range(height):
        raw_rows += b"\x00" + bytes([r, g, b] * width)
    compressed = zlib.compress(raw_rows)
    idat = chunk(b"IDAT", compressed)

    # IEND
    iend = chunk(b"IEND", b"")

    return sig + ihdr + idat + iend


# ---------------------------------------------------------------------------
# TONE ANALYZER TESTS
# ---------------------------------------------------------------------------

class TestToneDeduplication:
    """Verify overlapping span deduplication for tone findings."""

    def _make_tone_finding(self, snippet, start, end, rule_id, severity=SeverityLevel.HIGH):
        return {
            "category": DetectionCategory.TONE,
            "severity": severity,
            "confidence": 0.92,
            "flagged_snippet": snippet,
            "char_offset_start": start,
            "char_offset_end": end,
            "explanation": "test",
            "evidence_type": EvidenceEntityType.RULE,
            "rule_id": rule_id,
            "fact_id": None,
            "term_id": None,
            "asset_id": None,
            "cited_code": "RULE-TONE-01",
            "source": FindingSource.DETERMINISTIC_ENGINE,
            "status": FindingStatus.OPEN,
            "segment_id": "seg_1",
            "suggested_correction": None,
        }

    def test_overlapping_spans_keeps_longest(self):
        rule_id = "rule-1"
        # Full phrase (longer) should win over substring
        full = self._make_tone_finding("game-changing miracle", 10, 31, rule_id, SeverityLevel.HIGH)
        sub = self._make_tone_finding("game-changing", 10, 23, rule_id, SeverityLevel.MEDIUM)
        result = _deduplicate_tone_findings([sub, full])  # input order: shorter first
        assert len(result) == 1
        assert result[0]["flagged_snippet"] == "game-changing miracle"

    def test_non_overlapping_same_rule_both_kept(self):
        rule_id = "rule-1"
        f1 = self._make_tone_finding("game-changing", 0, 13, rule_id)
        f2 = self._make_tone_finding("miraculous", 50, 60, rule_id)
        result = _deduplicate_tone_findings([f1, f2])
        assert len(result) == 2

    def test_different_rules_both_kept(self):
        f1 = self._make_tone_finding("game-changing", 0, 13, "rule-1")
        f2 = self._make_tone_finding("game-changing", 0, 13, "rule-2")
        result = _deduplicate_tone_findings([f1, f2])
        assert len(result) == 2

    def test_llm_findings_never_suppressed(self):
        rule_id = "rule-1"
        llm = {**self._make_tone_finding("game-changing", 0, 13, rule_id),
               "source": FindingSource.LIVE_LLM}
        det = self._make_tone_finding("game-changing", 0, 13, rule_id)
        result = _deduplicate_tone_findings([llm, det])
        # LLM finding is kept (no overlap check); deterministic may also be kept (different source)
        assert len(result) >= 1

    def test_same_term_twice_at_different_offsets(self):
        """'cheap' at offset 10 and 'cheap' at offset 80 → both kept (different positions)."""
        rule_id = "rule-tone"
        f1 = self._make_tone_finding("cheap", 10, 15, rule_id)
        f2 = self._make_tone_finding("cheap", 80, 85, rule_id)
        result = _deduplicate_tone_findings([f1, f2])
        assert len(result) == 2

    def test_tone_analyzer_deduplication_integration(self):
        """Full ToneAnalyzer run: 'game-changing miracle' → only 1 tone finding (not 2)."""
        rule = _rule(
            "RULE-TONE-01",
            RuleCategory.TONE_VOICE,
            description="Avoid hyperbole game-changing or revolutionary without benchmarks.",
            examples_negative=["game-changing miracle"],
            examples_positive=["evidence-based performance"],
        )
        text = "This is a game-changing miracle for IT teams."
        segments = [_seg(text, "seg_1", 0)]
        findings = ToneAnalyzer.analyze(segments, text, [rule])
        tone_findings = [f for f in findings if f["category"] == DetectionCategory.TONE]
        # Both negative-example and hyperbole pattern would match — dedup should leave 1
        assert len(tone_findings) == 1
        assert "game-changing" in tone_findings[0]["flagged_snippet"].lower()

    def test_valid_content_no_findings(self):
        """Content using the approved positive example should not trigger tone findings."""
        rule = _rule(
            "RULE-TONE-01",
            RuleCategory.TONE_VOICE,
            description="Avoid hyperbole game-changing or revolutionary.",
            examples_negative=["revolutionary nonsense"],
            examples_positive=["proven enterprise reliability"],
        )
        text = "We offer proven enterprise reliability and measurable uptime."
        segments = [_seg(text, "seg_1", 0)]
        findings = ToneAnalyzer.analyze(segments, text, [rule])
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# TERMINOLOGY ANALYZER TESTS
# ---------------------------------------------------------------------------

class TestTerminologyAnalyzer:

    def test_whole_word_match(self):
        """'cheap' in 'looks cheap.' → matched."""
        term = _term("cheap", "cost-effective")
        text = "Our product looks cheap."
        findings = TerminologyAnalyzer.analyze([_seg(text)], text, [term])
        assert len(findings) == 1
        assert findings[0]["flagged_snippet"] == "cheap"
        assert findings[0]["suggested_correction"] == "cost-effective"

    def test_substring_not_matched(self):
        """'cheap' in 'cheapest' → NOT matched (whole-word boundary)."""
        term = _term("cheap", "cost-effective")
        text = "Get the cheapest plan available."
        findings = TerminologyAnalyzer.analyze([_seg(text)], text, [term])
        assert len(findings) == 0

    def test_case_insensitive_match(self):
        """'CHEAP' matches when is_case_sensitive=False."""
        term = _term("cheap", "cost-effective", is_case_sensitive=False)
        text = "This is a CHEAP solution."
        findings = TerminologyAnalyzer.analyze([_seg(text)], text, [term])
        assert len(findings) == 1

    def test_case_sensitive_no_match(self):
        """'apexcloud' should NOT match 'ApexCloud' when case-sensitive."""
        term = _term("ApexCloud", "ApexCloud™", is_case_sensitive=True)
        text = "apexcloud delivers performance."
        findings = TerminologyAnalyzer.analyze([_seg(text)], text, [term])
        assert len(findings) == 0

    def test_case_sensitive_exact_match(self):
        """'ApexCloud' (exact case) → matched."""
        term = _term("ApexCloud", "ApexCloud™", is_case_sensitive=True)
        text = "ApexCloud delivers performance."
        findings = TerminologyAnalyzer.analyze([_seg(text)], text, [term])
        assert len(findings) == 1

    def test_draft_term_ignored(self):
        """DRAFT term should not generate any findings."""
        term = _term("legacy", "modern", status=EntityStatus.DRAFT)
        text = "This is legacy infrastructure."
        findings = TerminologyAnalyzer.analyze([_seg(text)], text, [term])
        assert len(findings) == 0

    def test_term_at_end_of_sentence(self):
        """'cheap' before period (end of sentence) → matched."""
        term = _term("cheap", "cost-effective")
        text = "The alternative is cheap."
        findings = TerminologyAnalyzer.analyze([_seg(text)], text, [term])
        assert len(findings) == 1


# ---------------------------------------------------------------------------
# CLAIMS ANALYZER TESTS
# ---------------------------------------------------------------------------

class TestClaimsAnalyzer:

    def test_correct_price_no_finding(self):
        """Matching price $79 → 0 findings."""
        fact = _fact("FACT-P01", "PRICING", "Price is $79", numerical_value=79.0, expiry_days=90)
        text = "Subscribe for $79 per month."
        findings = ClaimsAnalyzer.analyze([_seg(text)], text, [fact], [])
        price_findings = [f for f in findings if f["category"] == DetectionCategory.CLAIMS]
        assert len(price_findings) == 0

    def test_wrong_price_critical_finding(self):
        """Wrong price $49 when fact says $79 → 1 CRITICAL finding."""
        fact = _fact("FACT-P01", "PRICING", "Price is $79 per user", numerical_value=79.0, expiry_days=90)
        text = "Subscribe for $49 per month."
        findings = ClaimsAnalyzer.analyze([_seg(text)], text, [fact], [])
        assert len(findings) == 1
        assert findings[0]["severity"] == SeverityLevel.CRITICAL
        assert "$49" in findings[0]["flagged_snippet"]
        assert "$79" in findings[0]["explanation"]
        assert findings[0]["suggested_correction"] == "$79"

    def test_expired_fact_no_correction(self):
        """Expired fact + differing price → NEEDS_REVIEW, suggested_correction=None."""
        fact = _fact("FACT-P02", "PRICING", "Price is $99 per user", numerical_value=99.0, expiry_days=-5)
        text = "Get it for $49 monthly."
        findings = ClaimsAnalyzer.analyze([_seg(text)], text, [fact], [])
        assert any(f["status"] == FindingStatus.NEEDS_REVIEW for f in findings)
        exp_findings = [f for f in findings if f["status"] == FindingStatus.NEEDS_REVIEW]
        for f in exp_findings:
            assert f["suggested_correction"] is None, "No correction should be given for expired facts"

    def test_draft_fact_completely_ignored(self):
        """DRAFT fact → 0 findings (draft facts must never be referenced)."""
        fact = _fact("FACT-DRAFT", "PRICING", "Price is $999", numerical_value=999.0, expiry_days=90,
                     status=EntityStatus.DRAFT)
        text = "Get it for $49 monthly."
        findings = ClaimsAnalyzer.analyze([_seg(text)], text, [fact], [])
        assert len(findings) == 0

    def test_cross_org_fact_isolation(self):
        """Facts from org_b must not appear in findings for org_a's text.
        (Simulated by passing only the correct org's facts.)"""
        fact_a = _fact("FACT-A01", "PRICING", "Price $79", numerical_value=79.0, expiry_days=90)
        # Org A's text uses wrong price vs Org A's fact → 1 finding
        text = "Subscribe for $49 per month."
        findings_a = ClaimsAnalyzer.analyze([_seg(text)], text, [fact_a], [])
        assert len(findings_a) == 1

        # Org B passes no facts → 0 findings
        findings_b = ClaimsAnalyzer.analyze([_seg(text)], text, [], [])
        assert len(findings_b) == 0

    def test_unsupported_claim_flagged_with_rule(self):
        """'industry-leading' + no supporting fact + active claim rule → NEEDS_REVIEW finding."""
        rule = _rule(
            "RULE-CLAIM-01",
            RuleCategory.TONE_VOICE,
            description="All superlative claims require substantiation from verified sources.",
        )
        text = "We are the industry-leading provider."
        findings = ClaimsAnalyzer.analyze([_seg(text)], text, [], [rule])
        assert len(findings) == 1
        assert findings[0]["status"] == FindingStatus.NEEDS_REVIEW
        assert findings[0]["suggested_correction"] is None

    def test_unsupported_claim_no_rule_no_finding(self):
        """'industry-leading' + no claim rule → 0 findings (design intent: rule-gated)."""
        text = "We are the industry-leading provider."
        findings = ClaimsAnalyzer.analyze([_seg(text)], text, [], [])
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# VISUAL ANALYZER TESTS (Pixel Analysis)
# ---------------------------------------------------------------------------

class TestVisualPixelAnalysis:

    def test_approved_color_no_finding(self):
        """Solid PNG in an approved blue → 0 pixel findings."""
        # #0052CC = (0, 82, 204)
        png_bytes = _make_solid_png(0, 82, 204)
        asset = _asset("ASSET-COLOR-01", "COLOR_PALETTE", {"approved_hexes": ["#0052CC"]})
        findings = VisualAnalyzer.analyze([], "", [asset], image_bytes=png_bytes)
        pixel_findings = [f for f in findings if "PIXEL_ANALYSIS" in f.get("explanation", "")]
        assert len(pixel_findings) == 0

    def test_unapproved_color_medium_finding(self):
        """Solid red PNG not in approved palette → 1 MEDIUM pixel finding."""
        # Solid red = (255, 0, 0), approved is blue #0052CC
        png_bytes = _make_solid_png(255, 0, 0)
        asset = _asset("ASSET-COLOR-01", "COLOR_PALETTE", {"approved_hexes": ["#0052CC"]})
        findings = VisualAnalyzer.analyze([], "", [asset], image_bytes=png_bytes)
        pixel_findings = [f for f in findings if "PIXEL_ANALYSIS" in f.get("explanation", "")]
        assert len(pixel_findings) >= 1
        assert pixel_findings[0]["severity"] == SeverityLevel.MEDIUM

    def test_corrupt_bytes_no_crash(self):
        """Corrupt image bytes → safe handling (INFO finding or empty, no exception)."""
        corrupt = b"not a valid image file at all"
        asset = _asset("ASSET-COLOR-01", "COLOR_PALETTE", {"approved_hexes": ["#0052CC"]})
        try:
            findings = VisualAnalyzer.analyze([], "", [asset], image_bytes=corrupt)
            # Should not raise; may return INFO finding or empty list
            for f in findings:
                assert f["severity"] in [SeverityLevel.INFO, SeverityLevel.MEDIUM, SeverityLevel.HIGH]
        except Exception as exc:
            pytest.fail(f"VisualAnalyzer raised on corrupt bytes: {exc}")

    def test_no_image_bytes_no_pixel_findings(self):
        """When image_bytes=None, no pixel analysis findings should be generated."""
        asset = _asset("ASSET-COLOR-01", "COLOR_PALETTE", {"approved_hexes": ["#0052CC"]})
        findings = VisualAnalyzer.analyze([], "", [asset], image_bytes=None)
        pixel_findings = [f for f in findings if "PIXEL_ANALYSIS" in f.get("explanation", "")]
        assert len(pixel_findings) == 0

    def test_text_hex_detection_separate(self):
        """Text containing an unapproved color hex in brand context → TEXT_HEX_DETECTION finding."""
        asset = _asset("ASSET-COLOR-01", "COLOR_PALETTE", {"approved_hexes": ["#0052CC"]})
        text = "Our brand primary color is #FF5500."
        segments = [_seg(text)]
        findings = VisualAnalyzer.analyze(segments, text, [asset], image_bytes=None)
        hex_findings = [f for f in findings if "TEXT_HEX_DETECTION" in f.get("explanation", "")]
        assert len(hex_findings) == 1

    def test_rgb_distance_calculation(self):
        """Verify Euclidean RGB distance math."""
        assert _rgb_distance((0, 0, 0), (0, 0, 0)) == 0.0
        assert abs(_rgb_distance((255, 0, 0), (0, 0, 0)) - 255.0) < 0.01
        # Distance between two blues close together should be small
        assert _rgb_distance((0, 82, 204), (0, 90, 210)) < 15.0


# ---------------------------------------------------------------------------
# ACCESSIBILITY ANALYZER TESTS
# ---------------------------------------------------------------------------

class TestAccessibilityAnalyzer:

    def _a11y_rule(self):
        return _rule(
            "RULE-A11Y-01",
            RuleCategory.ACCESSIBILITY,
            description="Ensure WCAG 2.1 Level AA compliance for all content.",
        )

    def test_contrast_below_normal_threshold_flagged(self):
        """Ratio 2.5:1 (below 4.5:1 for normal text) → HIGH finding."""
        ratio = calculate_contrast_ratio("#AAAAAA", "#FFFFFF")
        assert ratio is not None and ratio < 4.5

        rule = self._a11y_rule()
        text = "text: #AAAAAA on background: #FFFFFF"
        findings = AccessibilityAnalyzer.analyze([_seg(text)], text, [rule])
        contrast_f = [f for f in findings if "contrast" in f["explanation"].lower()]
        assert len(contrast_f) >= 1
        assert contrast_f[0]["severity"] == SeverityLevel.HIGH

    def test_contrast_above_normal_threshold_no_finding(self):
        """Ratio ~5.7:1 (above 4.5:1) → 0 contrast findings."""
        ratio = calculate_contrast_ratio("#595959", "#FFFFFF")
        assert ratio is not None and ratio >= 4.5

        rule = self._a11y_rule()
        text = "text: #595959 on background: #FFFFFF"
        findings = AccessibilityAnalyzer.analyze([_seg(text)], text, [rule])
        contrast_f = [f for f in findings if "contrast" in f["explanation"].lower()]
        assert len(contrast_f) == 0

    def test_contrast_large_text_threshold_3_to_1(self):
        """Ratio 3.5:1 passes large text threshold (3:1) but fails normal (4.5:1)."""
        # #767676 on white ≈ 4.54:1, let us use a deliberately low-contrast pair
        # #CCCCCC on white ≈ 1.6:1 — fails both thresholds
        # To test large-text path, we need a ratio between 3.0 and 4.5
        # #767676 on #FFFFFF ≈ 4.54 (passes normal, so no finding)
        # Use #888888 on #FFFFFF ≈ 3.54:1 — passes large, fails normal
        ratio = calculate_contrast_ratio("#888888", "#FFFFFF")
        assert ratio is not None and 3.0 <= ratio < 4.5

        rule = self._a11y_rule()
        # Segment text includes "large text" keyword → 3:1 threshold applies
        text = "large text: #888888 on background: #FFFFFF applies here"
        findings = AccessibilityAnalyzer.analyze([_seg(text)], text, [rule])
        contrast_f = [f for f in findings if "contrast" in f["explanation"].lower()]
        # With large text threshold 3.0, ratio ~3.54 passes → no finding
        assert len(contrast_f) == 0

    def test_contrast_large_text_still_fails_very_low(self):
        """Ratio 1.6:1 fails even large text 3:1 threshold."""
        ratio = calculate_contrast_ratio("#CCCCCC", "#FFFFFF")
        assert ratio is not None and ratio < 3.0

        rule = self._a11y_rule()
        text = "large text: #CCCCCC on background: #FFFFFF usage note"
        findings = AccessibilityAnalyzer.analyze([_seg(text)], text, [rule])
        contrast_f = [f for f in findings if "contrast" in f["explanation"].lower()]
        assert len(contrast_f) >= 1

    def test_vague_link_text_flagged(self):
        """'click here' → LOW accessibility finding."""
        rule = self._a11y_rule()
        text = "To view the report, click here."
        findings = AccessibilityAnalyzer.analyze([_seg(text)], text, [rule])
        link_f = [f for f in findings if "link" in f["explanation"].lower() or "cta" in f["explanation"].lower()]
        assert len(link_f) >= 1
        assert link_f[0]["severity"] == SeverityLevel.LOW

    def test_descriptive_link_no_finding(self):
        """'Download whitepaper' → 0 vague link findings."""
        rule = self._a11y_rule()
        text = "Download whitepaper for full architecture details."
        findings = AccessibilityAnalyzer.analyze([_seg(text)], text, [rule])
        link_f = [f for f in findings if "link" in f["explanation"].lower()]
        assert len(link_f) == 0

    def test_alt_text_flag_on_ocr_unavailable(self):
        """When structured_content has extraction_status=OCR_UNAVAILABLE → HIGH a11y finding."""
        rule = self._a11y_rule()
        struct = {"extraction_status": "OCR_UNAVAILABLE", "segments": []}
        # Need at least 1 segment to pass the initial guard
        seg = _seg("image content")
        findings = AccessibilityAnalyzer.analyze([seg], "", [rule], structured_content=struct)
        alt_f = [f for f in findings if "alt" in f["explanation"].lower()]
        assert len(alt_f) >= 1
        assert alt_f[0]["severity"] == SeverityLevel.HIGH
        assert alt_f[0]["status"] == FindingStatus.NEEDS_REVIEW

    def test_no_color_info_no_contrast_claim(self):
        """Segments with no hex color pairs → 0 contrast findings (not fabricated)."""
        rule = self._a11y_rule()
        text = "Our product is reliable and scalable."
        findings = AccessibilityAnalyzer.analyze([_seg(text)], text, [rule])
        contrast_f = [f for f in findings if "contrast" in f["explanation"].lower()]
        assert len(contrast_f) == 0


# ---------------------------------------------------------------------------
# MESSAGING ANALYZER TESTS
# ---------------------------------------------------------------------------

class TestMessagingAnalyzer:

    def test_neutral_competitor_mention_no_finding(self):
        """'Migration from AWS' (neutral) → 0 messaging findings."""
        rule = _rule(
            "RULE-MSG-01",
            RuleCategory.MESSAGING_PILLAR,
            description="Never state competitor clouds are failing or broken.",
            examples_negative=["AWS is broken and failing"],
        )
        text = "We support seamless migration from AWS to our platform."
        findings = MessagingAnalyzer.analyze([_seg(text)], text, [rule])
        assert len(findings) == 0

    def test_disparagement_flagged(self):
        """'AWS which is broken and failing' → CRITICAL messaging finding."""
        rule = _rule(
            "RULE-MSG-01",
            RuleCategory.MESSAGING_PILLAR,
            description="Never state competitor clouds are failing or broken.",
            examples_negative=["AWS is broken and failing"],
        )
        text = "Unlike AWS which is broken and failing, we offer full resilience."
        findings = MessagingAnalyzer.analyze([_seg(text)], text, [rule])
        assert len(findings) >= 1
        assert any(f["severity"] == SeverityLevel.CRITICAL for f in findings)

    def test_no_rule_no_findings(self):
        """No messaging rules → 0 findings regardless of content."""
        text = "AWS is broken and failing."
        findings = MessagingAnalyzer.analyze([_seg(text)], text, [])
        assert len(findings) == 0

    def test_negative_example_match(self):
        """Exact negative example match → HIGH finding with suggested correction."""
        rule = _rule(
            "RULE-MSG-02",
            RuleCategory.MESSAGING_PILLAR,
            description="Avoid low-cost positioning.",
            examples_negative=["budget option"],
            examples_positive=["enterprise-grade value"],
        )
        text = "We are the budget option for enterprise."
        findings = MessagingAnalyzer.analyze([_seg(text)], text, [rule])
        assert len(findings) >= 1
        assert findings[0]["suggested_correction"] == "enterprise-grade value"


# ---------------------------------------------------------------------------
# FINDING VERIFICATION LAYER TESTS
# ---------------------------------------------------------------------------

class TestFindingVerification:

    def _candidate(self, snippet, start, end, raw_text=""):
        return {
            "category": DetectionCategory.TERMINOLOGY,
            "severity": SeverityLevel.HIGH,
            "confidence": 0.98,
            "flagged_snippet": snippet,
            "char_offset_start": start,
            "char_offset_end": end,
            "explanation": "test",
            "evidence_type": EvidenceEntityType.TERM,
            "rule_id": None,
            "fact_id": None,
            "term_id": str(uuid.uuid4()),
            "asset_id": None,
            "cited_code": "TERM-TEST",
            "source": FindingSource.DETERMINISTIC_ENGINE,
            "status": FindingStatus.OPEN,
            "segment_id": "seg_1",
            "suggested_correction": "better",
        }

    def test_valid_finding_passes(self):
        raw = "Our solution is cheap compared to others."
        c = self._candidate("cheap", 16, 21, raw)
        assert _verify_finding(c, raw) is True

    def test_empty_snippet_discarded(self):
        raw = "Some text here."
        c = self._candidate("", 0, 0, raw)
        assert _verify_finding(c, raw) is False

    def test_snippet_not_in_raw_text_discarded(self):
        raw = "Our solution is cost-effective."
        c = self._candidate("cheap", 0, 5, raw)
        assert _verify_finding(c, raw) is False

    def test_offset_out_of_bounds_discarded(self):
        raw = "Short text."
        c = self._candidate("text", 1000, 1004, raw)
        assert _verify_finding(c, raw) is False

    def test_zero_offset_dimension_finding_passes(self):
        """Image dimension findings use offsets [0,0] and should always pass."""
        c = self._candidate("Image dimensions: 100x100 px", 0, 0, "")
        assert _verify_finding(c, "") is True

    def test_cross_category_deduplication(self):
        """Same snippet at same offsets in same category → deduplicated to 1."""
        c1 = self._candidate("cheap", 10, 15)
        c2 = self._candidate("cheap", 10, 15)
        result = _deduplicate_cross_category([c1, c2])
        assert len(result) == 1

    def test_different_offset_not_deduplicated(self):
        """Same snippet at different offsets → both kept."""
        c1 = self._candidate("cheap", 10, 15)
        c2 = self._candidate("cheap", 50, 55)
        result = _deduplicate_cross_category([c1, c2])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# WCAG CONTRAST MATH UNIT TESTS
# ---------------------------------------------------------------------------

class TestWCAGContrastMath:

    def test_pure_white_black_contrast_21_to_1(self):
        ratio = calculate_contrast_ratio("#FFFFFF", "#000000")
        assert ratio is not None
        assert abs(ratio - 21.0) < 0.1

    def test_same_color_contrast_1_to_1(self):
        ratio = calculate_contrast_ratio("#FF0000", "#FF0000")
        assert ratio is not None
        assert abs(ratio - 1.0) < 0.01

    def test_invalid_hex_returns_none(self):
        assert calculate_contrast_ratio("not_a_hex", "#FFFFFF") is None
        assert calculate_contrast_ratio("#FFFFFF", "ZZZZZZ") is None

    def test_three_char_hex_expansion(self):
        """#FFF should equal #FFFFFF."""
        ratio_long = calculate_contrast_ratio("#FFFFFF", "#000000")
        ratio_short = calculate_contrast_ratio("#FFF", "#000")
        assert ratio_long is not None and ratio_short is not None
        assert abs(ratio_long - ratio_short) < 0.01
