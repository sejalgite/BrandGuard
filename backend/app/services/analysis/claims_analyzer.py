"""
app/services/analysis/claims_analyzer.py
Fact Registry and Claims Analysis Engine.
Detects outdated prices, expired facts, contradictory numerical specifications,
and unsupported performance claims requiring human verification.

Fact status handling:
  - ACTIVE, non-expired facts: used as approved ground truth for price/value comparison.
  - ACTIVE, expired facts:     price comparison raises NEEDS_REVIEW (cannot verify current value).
  - DRAFT / REJECTED facts:    completely ignored — never used as evidence or reference.
  - Expired fact statement cited in content: flagged as NEEDS_REVIEW (no suggested correction).

Confidence values:
  - Price contradiction (active fact): 0.950 — exact numeric comparison against registered fact
  - Price with expired fact reference:  0.850 — comparison possible but fact no longer current
  - Expired fact statement match:       0.900 — keyword-density match against expired statement
  - Unsupported absolute/superlative:   0.850 — pattern match; no active fact supports claim
"""
import re
import logging
from datetime import date
from typing import List, Dict, Any, Optional

from app.models.finding import (
    DetectionCategory, SeverityLevel, FindingStatus, FindingSource, EvidenceEntityType
)
from app.models.constitution import FactRegistry, BrandRule, EntityStatus, RuleCategory

logger = logging.getLogger(__name__)


class ClaimsAnalyzer:
    """Analyzer for verified facts, pricing accuracy, expiry dates, and claim validity."""

    @classmethod
    def analyze(
        cls,
        segments: List[Dict[str, Any]],
        raw_text: str,
        facts: List[FactRegistry],
        rules: List[BrandRule]
    ) -> List[Dict[str, Any]]:
        """
        Compare text against Fact Registry.

        Only ACTIVE facts are used as approved ground truth.
        DRAFT and REJECTED facts are silently ignored.
        Expired ACTIVE facts trigger NEEDS_REVIEW (not OPEN) with no suggested correction.
        """
        findings = []
        today = date.today()

        if not segments:
            return findings

        # Partition facts by usability:
        #   usable_active   — ACTIVE and not expired  → ground truth
        #   usable_expired  — ACTIVE but past expiry_date → flag use as NEEDS_REVIEW
        #   ignored         — DRAFT / REJECTED → never referenced
        usable_active = [
            f for f in facts
            if f.status == EntityStatus.ACTIVE and f.expiry_date >= today
        ]
        usable_expired = [
            f for f in facts
            if f.status == EntityStatus.ACTIVE and f.expiry_date < today
        ]
        # DRAFT / REJECTED facts are excluded entirely — no reference, no finding

        # 1. Detect Pricing and Numerical Contradictions against ACTIVE facts
        # Confidence: 0.950 — exact numeric comparison against registered fact.
        price_pattern = re.compile(
            r'(\$|USD\s*|EUR\s*|GBP\s*)(\d+(?:\.\d{2})?)'
            r'|\b(\d+(?:\.\d{2})?)\s*(USD|EUR|GBP|dollars)\b',
            re.IGNORECASE
        )

        pricing_active = [
            f for f in usable_active
            if (
                f.numerical_value is not None and (
                    "price" in f.claim_type.lower()
                    or "pricing" in f.claim_type.lower()
                    or f.unit in ["$", "USD", "EUR", "GBP", "USD/month"]
                    or "$" in f.statement
                )
            )
        ]
        pricing_expired = [
            f for f in usable_expired
            if (
                f.numerical_value is not None and (
                    "price" in f.claim_type.lower()
                    or "pricing" in f.claim_type.lower()
                    or f.unit in ["$", "USD", "EUR", "GBP", "USD/month"]
                    or "$" in f.statement
                )
            )
        ]

        # Compare stated prices against ACTIVE non-expired pricing facts
        for p_fact in pricing_active:
            approved_price = float(p_fact.numerical_value)
            for seg in segments:
                text = seg.get("text", "")
                if not text:
                    continue
                for match in price_pattern.finditer(text):
                    full_match = match.group(0)
                    amount_str = match.group(2) or match.group(3)
                    if not amount_str:
                        continue
                    try:
                        stated_price = float(amount_str)
                    except ValueError:
                        continue

                    if stated_price != approved_price:
                        base_offset = seg.get("char_start", 0)
                        start = base_offset + match.start()
                        end = base_offset + match.end()

                        unit_prefix = "$" if p_fact.unit in ["$", "USD", None] else f"{p_fact.unit} "
                        suggested = f"{unit_prefix}{approved_price:g}"

                        findings.append({
                            "category": DetectionCategory.CLAIMS,
                            "severity": SeverityLevel.CRITICAL,
                            "confidence": 0.950,
                            "flagged_snippet": full_match,
                            "char_offset_start": max(0, start),
                            "char_offset_end": max(0, end),
                            "explanation": (
                                f"Outdated or incorrect price '{full_match}'. "
                                f"Approved brand fact [{p_fact.fact_code}] specifies the approved value "
                                f"of {suggested} (Source: {p_fact.source_reference})."
                            ),
                            "evidence_type": EvidenceEntityType.FACT,
                            "fact_id": p_fact.id,
                            "rule_id": None,
                            "term_id": None,
                            "asset_id": None,
                            "cited_code": p_fact.fact_code,
                            "source": FindingSource.DETERMINISTIC_ENGINE,
                            "status": FindingStatus.OPEN,
                            "segment_id": seg.get("segment_id"),
                            "suggested_correction": suggested,
                        })

        # Compare stated prices against ACTIVE but expired pricing facts
        # Cannot recommend a replacement — flag as NEEDS_REVIEW only.
        # Confidence: 0.850 — comparison possible but fact no longer certified current.
        for p_fact in pricing_expired:
            approved_price = float(p_fact.numerical_value)
            for seg in segments:
                text = seg.get("text", "")
                if not text:
                    continue
                for match in price_pattern.finditer(text):
                    full_match = match.group(0)
                    amount_str = match.group(2) or match.group(3)
                    if not amount_str:
                        continue
                    try:
                        stated_price = float(amount_str)
                    except ValueError:
                        continue

                    if stated_price != approved_price:
                        base_offset = seg.get("char_start", 0)
                        start = base_offset + match.start()
                        end = base_offset + match.end()

                        findings.append({
                            "category": DetectionCategory.CLAIMS,
                            "severity": SeverityLevel.HIGH,
                            "confidence": 0.850,
                            "flagged_snippet": full_match,
                            "char_offset_start": max(0, start),
                            "char_offset_end": max(0, end),
                            "explanation": (
                                f"Claimed price '{full_match}' cannot be verified: "
                                f"Reference fact [{p_fact.fact_code}] expired on "
                                f"{p_fact.expiry_date.isoformat()}. "
                                f"Current pricing must be re-certified before publication."
                            ),
                            "evidence_type": EvidenceEntityType.FACT,
                            "fact_id": p_fact.id,
                            "rule_id": None,
                            "term_id": None,
                            "asset_id": None,
                            "cited_code": p_fact.fact_code,
                            "source": FindingSource.DETERMINISTIC_ENGINE,
                            "status": FindingStatus.NEEDS_REVIEW,
                            "segment_id": seg.get("segment_id"),
                            "suggested_correction": None,  # Never invent correction for expired facts
                        })

        # 2. Check Content that Explicitly Cites an Expired Fact's Statement
        # Uses keyword-density matching for the expired fact's statement text.
        # Confidence: 0.900 — keyword-density match against expired statement.
        for fact in usable_expired:
            stmt_keywords = [w.lower() for w in fact.statement.split() if len(w) > 4]
            if len(stmt_keywords) < 2:
                continue

            for seg in segments:
                text_lower = seg.get("text", "").lower()
                matched_kw = [kw for kw in stmt_keywords if kw in text_lower]
                if len(matched_kw) >= min(4, len(stmt_keywords)):
                    snippet = seg.get("text", "")[:120]
                    base_offset = seg.get("char_start", 0)
                    findings.append({
                        "category": DetectionCategory.CLAIMS,
                        "severity": SeverityLevel.HIGH,
                        "confidence": 0.900,
                        "flagged_snippet": snippet,
                        "char_offset_start": max(0, base_offset),
                        "char_offset_end": max(0, base_offset + len(snippet)),
                        "explanation": (
                            f"Content references brand fact [{fact.fact_code}] which expired on "
                            f"{fact.expiry_date.isoformat()}. Expired facts cannot be cited in active marketing."
                        ),
                        "evidence_type": EvidenceEntityType.FACT,
                        "fact_id": fact.id,
                        "rule_id": None,
                        "term_id": None,
                        "asset_id": None,
                        "cited_code": fact.fact_code,
                        "source": FindingSource.DETERMINISTIC_ENGINE,
                        "status": FindingStatus.NEEDS_REVIEW,
                        "segment_id": seg.get("segment_id"),
                        "suggested_correction": None,  # Never invent correction for expired facts
                    })
                    break  # Report once per expired fact

        # 3. Check for Unsupported Absolute / Superlative Claims
        # Only activated when an active brand rule governs claim substantiation.
        # Confidence: 0.850 — pattern match; no active fact supports the claim.
        # Design note: Neutral competitor mentions are NOT flagged here (no competitor check).
        claim_rules = [
            r for r in rules
            if r.status == EntityStatus.ACTIVE
            and (
                "claim" in r.rule_code.lower()
                or "claim" in r.title.lower()
                or "substantiation" in r.description.lower()
                or "unsupported" in r.description.lower()
            )
        ]

        unsupported_patterns = [
            (
                re.compile(
                    r'\b(100%\s+guaranteed|100%\s+secure|zero\s+risk|infinitely\s+scalable)\b',
                    re.IGNORECASE
                ),
                "Absolute guarantee requires verified technical proof."
            ),
            (
                re.compile(
                    r'\b(#1|number\s+one|best\s+in\s+the\s+world|industry-leading)\b',
                    re.IGNORECASE
                ),
                "Superlative market claim requires third-party benchmark or citation."
            ),
            (
                re.compile(r'\b(\d+x\s+faster|\d+%\s+cheaper)\b', re.IGNORECASE),
                "Comparative metric claim requires registered fact verification."
            ),
        ]

        if claim_rules:
            active_rule = claim_rules[0]
            for seg in segments:
                text = seg.get("text", "")
                for pattern, reason in unsupported_patterns:
                    match = pattern.search(text)
                    if match:
                        matched_snippet = match.group(0)
                        # Only flag if no active (non-expired) fact supports the exact claim text
                        is_supported = any(
                            matched_snippet.lower() in f.statement.lower()
                            for f in usable_active
                        )
                        if not is_supported:
                            base_offset = seg.get("char_start", 0)
                            start = base_offset + match.start()
                            end = base_offset + match.end()

                            findings.append({
                                "category": DetectionCategory.CLAIMS,
                                "severity": SeverityLevel.HIGH,
                                "confidence": 0.850,
                                "flagged_snippet": matched_snippet,
                                "char_offset_start": max(0, start),
                                "char_offset_end": max(0, end),
                                "explanation": (
                                    f"Unsupported claim '{matched_snippet}': {reason} "
                                    f"Governed by rule [{active_rule.rule_code}]: '{active_rule.title}'. "
                                    f"No active registered fact validates this claim."
                                ),
                                "evidence_type": EvidenceEntityType.RULE,
                                "rule_id": active_rule.id,
                                "fact_id": None,
                                "term_id": None,
                                "asset_id": None,
                                "cited_code": active_rule.rule_code,
                                "source": FindingSource.DETERMINISTIC_ENGINE,
                                "status": FindingStatus.NEEDS_REVIEW,
                                "segment_id": seg.get("segment_id"),
                                "suggested_correction": None,  # Never invent a correction for unsupported claims
                            })

        return findings
