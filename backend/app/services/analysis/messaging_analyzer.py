"""
app/services/analysis/messaging_analyzer.py
Messaging Alignment and Brand Pillar Analysis Engine.
Checks content alignment against approved positioning statements, audience targeting,
and competitor comparison guidelines.

Design note — competitor mention policy:
  Neutral mentions of competitors (e.g. "AWS", "Azure") are NOT flagged.
  Only combinations of a competitor name AND an explicitly negative descriptor
  (e.g. "inferior", "broken", "failing") trigger a finding, AND only when an
  active messaging rule with a "competitor" / "comparison" governing context exists.
  This prevents false positives on legitimate technical comparisons.

Confidence values:
  - Negative example match:    0.940 — exact string match from approved rule
  - Competitor disparagement:  0.910 — regex pattern: competitor name + derogatory adjective
  - LLM contextual:            0.800 — LLM judgment (Ollama), lower certainty
"""
import re
import logging
from typing import List, Dict, Any, Optional

from app.models.finding import (
    DetectionCategory, SeverityLevel, FindingStatus, FindingSource, EvidenceEntityType
)
from app.models.constitution import BrandRule, EntityStatus, RuleCategory
from app.services.analysis.ollama_client import LocalOllamaClient

logger = logging.getLogger(__name__)


class MessagingAnalyzer:
    """Analyzer for messaging pillar alignment, positioning fidelity, and competitor claims."""

    @classmethod
    def analyze(
        cls,
        segments: List[Dict[str, Any]],
        raw_text: str,
        rules: List[BrandRule],
        ollama_client: Optional[LocalOllamaClient] = None
    ) -> List[Dict[str, Any]]:
        findings = []

        # Filter strictly for ACTIVE messaging rules
        messaging_rules = [
            r for r in rules
            if r.status == EntityStatus.ACTIVE and r.category == RuleCategory.MESSAGING_PILLAR
        ]
        if not messaging_rules or not segments:
            return findings

        for rule in messaging_rules:
            # 1. Negative Examples in Messaging Rules
            # Confidence: 0.940 — exact string match from approved rule (high certainty).
            if rule.examples_negative:
                for neg_ex in rule.examples_negative:
                    neg_clean = neg_ex.strip()
                    if not neg_clean or len(neg_clean) < 3:
                        continue

                    pattern = re.compile(r'\b' + re.escape(neg_clean) + r'\b', re.IGNORECASE)
                    for seg in segments:
                        text = seg.get("text", "")
                        match = pattern.search(text)
                        if match:
                            snippet = match.group(0)
                            base_offset = seg.get("char_start", 0)
                            start = base_offset + match.start()
                            end = base_offset + match.end()

                            suggested = rule.examples_positive[0] if rule.examples_positive else None

                            findings.append({
                                "category": DetectionCategory.MESSAGING,
                                "severity": SeverityLevel.HIGH,
                                "confidence": 0.940,
                                "flagged_snippet": snippet,
                                "char_offset_start": max(0, start),
                                "char_offset_end": max(0, end),
                                "explanation": (
                                    f"Messaging misalignment: '{snippet}' contradicts approved messaging pillar "
                                    f"[{rule.rule_code}]: '{rule.title}'. {rule.description}"
                                ),
                                "evidence_type": EvidenceEntityType.RULE,
                                "rule_id": rule.id,
                                "fact_id": None,
                                "term_id": None,
                                "asset_id": None,
                                "cited_code": rule.rule_code,
                                "source": FindingSource.DETERMINISTIC_ENGINE,
                                "status": FindingStatus.OPEN,
                                "segment_id": seg.get("segment_id"),
                                "suggested_correction": suggested,
                            })

            # 2. Competitor Disparagement Detection
            # Only triggered when this rule's description contains "competitor" or "comparison".
            # This check detects competitor name + derogatory adjective within the same sentence.
            # Confidence: 0.910 — regex pattern: named competitor + explicit negative descriptor.
            #
            # Design note: We require BOTH a competitor name AND a derogatory adjective to be
            # present in the same match span. This ensures neutral competitor mentions
            # (e.g. "migration from AWS", "compatible with Azure") are NOT flagged.
            desc_lower = rule.description.lower()
            if "competitor" in desc_lower or "comparison" in desc_lower:
                comp_pat = re.compile(
                    r'\b(AWS|Amazon Web Services|Azure|Microsoft Azure|Google Cloud|GCP)\b'
                    r'.*?\b(inferior|worse|failing|broken|legacy|obsolete)\b',
                    re.IGNORECASE
                )
                for seg in segments:
                    text = seg.get("text", "")
                    match = comp_pat.search(text)
                    if match:
                        snippet = match.group(0)
                        base_offset = seg.get("char_start", 0)
                        start = base_offset + match.start()
                        end = base_offset + match.end()

                        findings.append({
                            "category": DetectionCategory.MESSAGING,
                            "severity": SeverityLevel.CRITICAL,
                            "confidence": 0.910,
                            "flagged_snippet": snippet,
                            "char_offset_start": max(0, start),
                            "char_offset_end": max(0, end),
                            "explanation": (
                                f"Direct disparagement of competitor in '{snippet}'. "
                                f"Approved rule [{rule.rule_code}] prohibits derogatory competitor "
                                f"claims without verified legal approval."
                            ),
                            "evidence_type": EvidenceEntityType.RULE,
                            "rule_id": rule.id,
                            "fact_id": None,
                            "term_id": None,
                            "asset_id": None,
                            "cited_code": rule.rule_code,
                            "source": FindingSource.DETERMINISTIC_ENGINE,
                            "status": FindingStatus.OPEN,
                            "segment_id": seg.get("segment_id"),
                            "suggested_correction": (
                                "Focus on internal product capabilities rather than named "
                                "competitor disparagement"
                            ),
                        })

            # 3. Contextual LLM Evaluation (if Ollama available)
            # Confidence: 0.800 — LLM judgment (Ollama), lower certainty.
            if ollama_client:
                health = ollama_client.check_health()
                if health.get("available") and health.get("model_ready"):
                    for seg in segments[:3]:
                        text = seg.get("text", "")
                        prompt = (
                            f"Messaging Rule: {rule.title}\nDescription: {rule.description}\n"
                            f"Content: \"{text}\"\n"
                            f"Does this content violate the messaging rule? Reply YES or NO with brief reason."
                        )
                        resp = ollama_client.generate_completion(prompt)
                        if resp and resp.upper().startswith("YES"):
                            reason = resp[3:].strip(": ").strip()
                            base_offset = seg.get("char_start", 0)
                            findings.append({
                                "category": DetectionCategory.MESSAGING,
                                "severity": SeverityLevel.MEDIUM,
                                "confidence": 0.800,
                                "flagged_snippet": text[:100],
                                "char_offset_start": max(0, base_offset),
                                "char_offset_end": max(0, base_offset + min(100, len(text))),
                                "explanation": (
                                    f"Contextual messaging discrepancy with [{rule.rule_code}]: {reason}"
                                ),
                                "evidence_type": EvidenceEntityType.RULE,
                                "rule_id": rule.id,
                                "fact_id": None,
                                "term_id": None,
                                "asset_id": None,
                                "cited_code": rule.rule_code,
                                "source": FindingSource.LIVE_LLM,
                                "status": FindingStatus.OPEN,
                                "segment_id": seg.get("segment_id"),
                                "suggested_correction": None,
                            })

        return findings
