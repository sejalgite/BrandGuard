"""
app/services/analysis/visual_analyzer.py
Visual Consistency Analysis Engine.
Analyzes visual media, resolution, aspect ratio, and color specifications
against the approved Brand Asset Library.

Confidence values:
  - Dimension check:         0.980 — exact pixel measurement comparison
  - Pixel color analysis:    0.950 — dominant color extraction via sampling (high certainty)
  - Text hex detection:      0.900 — hex code found in brand design context in document text
"""
import io
import re
import math
import logging
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple

from app.models.finding import (
    DetectionCategory, SeverityLevel, FindingStatus, FindingSource, EvidenceEntityType
)
from app.models.constitution import BrandAsset, EntityStatus

logger = logging.getLogger(__name__)

# Approved neutral colors that are always allowed (pure black / pure white)
_ALWAYS_ALLOWED_HEXES = {"#ffffff", "#fff", "#000000", "#000"}

# Color distance tolerance for Euclidean RGB space (0–441 range)
# 60 means approximately ±24% deviation per channel
_COLOR_DISTANCE_TOLERANCE = 60


def _hex_to_rgb(hex_str: str) -> Optional[Tuple[int, int, int]]:
    """Convert 3- or 6-character hex color to (R, G, B) tuple."""
    h = hex_str.lstrip("#").strip()
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    if len(h) != 6:
        return None
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return None


def _rgb_distance(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
    """Euclidean distance in RGB space: sqrt((r1-r2)^2 + (g1-g2)^2 + (b1-b2)^2)."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def _extract_dominant_colors(image_bytes: bytes, top_n: int = 5) -> List[Tuple[int, int, int]]:
    """
    Extract dominant colors from image bytes using pixel frequency sampling.

    Uses Pillow to open the image, convert to RGB, downsample for performance,
    and return the top-N most frequent pixel colors.

    Returns an empty list if the image cannot be opened or is unsupported.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed — pixel analysis unavailable.")
        return []

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        # Downsample to max 200x200 for speed (preserves color distribution)
        img.thumbnail((200, 200))
        try:
            pixels = list(img.get_flattened_data())  # Pillow 14+ API
        except AttributeError:
            pixels = list(img.getdata())  # Pillow < 14 fallback
        # Round each channel to nearest 8 to group near-identical colors
        quantized = [(r & 0xF8, g & 0xF8, b & 0xF8) for r, g, b in pixels]
        counter = Counter(quantized)
        # Return raw (un-rounded) representative from most common bucket
        most_common = [color for color, _ in counter.most_common(top_n)]
        return most_common
    except Exception as exc:
        logger.warning("Image pixel extraction failed: %s", exc)
        return []


def _is_color_approved(
    pixel: Tuple[int, int, int],
    approved_rgbs: List[Tuple[int, int, int]],
    tolerance: float = _COLOR_DISTANCE_TOLERANCE
) -> bool:
    """Return True if pixel is within tolerance of any approved color."""
    return any(_rgb_distance(pixel, approved) <= tolerance for approved in approved_rgbs)


class VisualAnalyzer:
    """Analyzer for visual brand consistency, asset properties, and color palettes."""

    @classmethod
    def analyze(
        cls,
        segments: List[Dict[str, Any]],
        raw_text: str,
        assets: List[BrandAsset],
        extraction_metadata: Optional[Dict[str, Any]] = None,
        image_bytes: Optional[bytes] = None,
    ) -> List[Dict[str, Any]]:
        """
        Analyze visual brand compliance.

        Args:
            segments: Structured text segments from document extraction.
            raw_text: Full extracted text string.
            assets: Active BrandAsset objects from the Constitution.
            extraction_metadata: Extraction metadata dict (may contain image_dimensions).
            image_bytes: Raw bytes of the uploaded image file (for pixel analysis).
                         Only provided when the document version is an image type.
        """
        findings = []

        # Filter strictly for ACTIVE approved assets
        active_assets = [a for a in assets if a.status == EntityStatus.ACTIVE]
        if not active_assets:
            return findings

        metadata = extraction_metadata or {}
        img_dims = metadata.get("image_dimensions")  # [width, height]

        # 1. Dimensional / Resolution Checks against Approved Asset Specs
        # Confidence: 0.980 — exact pixel measurement comparison.
        if img_dims and len(img_dims) == 2:
            w, h = img_dims[0], img_dims[1]
            for asset in active_assets:
                specs = asset.specifications or {}
                min_w = specs.get("min_width")
                min_h = specs.get("min_height")

                if min_w and w < min_w:
                    findings.append({
                        "category": DetectionCategory.VISUAL,
                        "severity": SeverityLevel.HIGH,
                        "confidence": 0.980,
                        "flagged_snippet": f"Image dimensions: {w}x{h} px",
                        "char_offset_start": 0,
                        "char_offset_end": 0,
                        "explanation": (
                            f"Image resolution {w}px width is below approved minimum of {min_w}px "
                            f"specified for asset [{asset.asset_code}]: '{asset.name}'."
                        ),
                        "evidence_type": EvidenceEntityType.ASSET,
                        "asset_id": asset.id,
                        "rule_id": None,
                        "fact_id": None,
                        "term_id": None,
                        "cited_code": asset.asset_code,
                        "source": FindingSource.DETERMINISTIC_ENGINE,
                        "status": FindingStatus.OPEN,
                        "segment_id": None,
                        "suggested_correction": f"Export image at min {min_w}px width",
                    })

                if min_h and h < min_h:
                    findings.append({
                        "category": DetectionCategory.VISUAL,
                        "severity": SeverityLevel.HIGH,
                        "confidence": 0.980,
                        "flagged_snippet": f"Image dimensions: {w}x{h} px",
                        "char_offset_start": 0,
                        "char_offset_end": 0,
                        "explanation": (
                            f"Image resolution {h}px height is below approved minimum of {min_h}px "
                            f"specified for asset [{asset.asset_code}]: '{asset.name}'."
                        ),
                        "evidence_type": EvidenceEntityType.ASSET,
                        "asset_id": asset.id,
                        "rule_id": None,
                        "fact_id": None,
                        "term_id": None,
                        "cited_code": asset.asset_code,
                        "source": FindingSource.DETERMINISTIC_ENGINE,
                        "status": FindingStatus.OPEN,
                        "segment_id": None,
                        "suggested_correction": f"Export image at min {min_h}px height",
                    })

        # Identify color/palette/logo assets that specify an approved color palette
        color_assets = [
            a for a in active_assets
            if a.asset_type.upper() in ["COLOR", "COLOR_PALETTE", "PALETTE", "LOGO"]
        ]

        # 2. Real Pixel Color Analysis (when image bytes are provided)
        # Confidence: 0.950 — dominant color extraction via pixel frequency sampling.
        if image_bytes and color_assets:
            dominant_colors = _extract_dominant_colors(image_bytes)

            if dominant_colors:
                for asset in color_assets:
                    specs = asset.specifications or {}
                    approved_hexes = list(specs.get("approved_hexes") or [])
                    primary_hex = specs.get("hex") or specs.get("primary_hex")
                    if primary_hex:
                        approved_hexes.append(primary_hex)

                    approved_rgbs = [
                        _hex_to_rgb(h) for h in approved_hexes if h
                    ]
                    approved_rgbs = [c for c in approved_rgbs if c is not None]

                    if not approved_rgbs:
                        continue

                    # Flag each dominant color not within tolerance of any approved color
                    for dom_rgb in dominant_colors:
                        # Skip neutral whites/blacks regardless of asset spec
                        if _is_color_approved(dom_rgb, [(255, 255, 255), (0, 0, 0)], tolerance=20):
                            continue
                        if not _is_color_approved(dom_rgb, approved_rgbs):
                            dom_hex = "#{:02X}{:02X}{:02X}".format(*dom_rgb)
                            approved_display = ", ".join(approved_hexes[:5])
                            findings.append({
                                "category": DetectionCategory.VISUAL,
                                "severity": SeverityLevel.MEDIUM,
                                "confidence": 0.950,
                                "flagged_snippet": f"Dominant image color: {dom_hex}",
                                "char_offset_start": 0,
                                "char_offset_end": 0,
                                "explanation": (
                                    f"Dominant color {dom_hex} detected via pixel analysis does not match "
                                    f"approved palette asset [{asset.asset_code}]: '{asset.name}'. "
                                    f"Approved colors: {approved_display}. "
                                    f"Detection method: PIXEL_ANALYSIS."
                                ),
                                "evidence_type": EvidenceEntityType.ASSET,
                                "asset_id": asset.id,
                                "rule_id": None,
                                "fact_id": None,
                                "term_id": None,
                                "cited_code": asset.asset_code,
                                "source": FindingSource.DETERMINISTIC_ENGINE,
                                "status": FindingStatus.OPEN,
                                "segment_id": None,
                                "suggested_correction": approved_hexes[0] if approved_hexes else None,
                            })
            else:
                # Image bytes provided but could not be analyzed — flag as informational
                for asset in color_assets:
                    findings.append({
                        "category": DetectionCategory.VISUAL,
                        "severity": SeverityLevel.INFO,
                        "confidence": 1.0,
                        "flagged_snippet": "Image file (pixel analysis unavailable)",
                        "char_offset_start": 0,
                        "char_offset_end": 0,
                        "explanation": (
                            f"Image pixel color analysis could not be performed (unsupported format or corrupt file). "
                            f"Manual review required against asset [{asset.asset_code}]: '{asset.name}'."
                        ),
                        "evidence_type": EvidenceEntityType.ASSET,
                        "asset_id": asset.id,
                        "rule_id": None,
                        "fact_id": None,
                        "term_id": None,
                        "cited_code": asset.asset_code,
                        "source": FindingSource.DETERMINISTIC_ENGINE,
                        "status": FindingStatus.NEEDS_REVIEW,
                        "segment_id": None,
                        "suggested_correction": None,
                    })
                    break  # One INFO finding is sufficient

        # 3. Text Hex Detection in Design Specification Text
        # Detects hex color codes written explicitly in document text segments
        # (e.g. style guides or design specs mentioning "#FF5500").
        # Confidence: 0.900 — hex code found in brand-context text.
        hex_pattern = re.compile(r'#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})\b')

        for asset in color_assets:
            specs = asset.specifications or {}
            approved_hexes = list(specs.get("approved_hexes") or [])
            primary_hex = specs.get("hex") or specs.get("primary_hex")
            if primary_hex:
                approved_hexes.append(primary_hex)

            approved_set = {h.lower() for h in approved_hexes if h}
            if not approved_set:
                continue

            for seg in segments:
                text = seg.get("text", "")
                for match in hex_pattern.finditer(text):
                    found_hex = match.group(0).lower()
                    # Only flag if segment context suggests brand color discussion
                    context = text.lower()
                    if (
                        "color" in context or "brand" in context
                        or "signature" in context or "primary" in context
                    ) and found_hex not in approved_set:
                        # Skip neutral blacks and whites
                        if found_hex in _ALWAYS_ALLOWED_HEXES:
                            continue
                        base_offset = seg.get("char_start", 0)
                        start = base_offset + match.start()
                        end = base_offset + match.end()

                        suggested = sorted(approved_set)[0] if approved_set else None

                        findings.append({
                            "category": DetectionCategory.VISUAL,
                            "severity": SeverityLevel.MEDIUM,
                            "confidence": 0.900,
                            "flagged_snippet": match.group(0),
                            "char_offset_start": max(0, start),
                            "char_offset_end": max(0, end),
                            "explanation": (
                                f"Unapproved color code '{match.group(0)}' cited in brand design context. "
                                f"Approved palette asset [{asset.asset_code}] specifies: "
                                f"{', '.join(sorted(approved_set))}. "
                                f"Detection method: TEXT_HEX_DETECTION."
                            ),
                            "evidence_type": EvidenceEntityType.ASSET,
                            "asset_id": asset.id,
                            "rule_id": None,
                            "fact_id": None,
                            "term_id": None,
                            "cited_code": asset.asset_code,
                            "source": FindingSource.DETERMINISTIC_ENGINE,
                            "status": FindingStatus.OPEN,
                            "segment_id": seg.get("segment_id"),
                            "suggested_correction": suggested,
                        })

        return findings
