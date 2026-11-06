"""
app/services/analysis/tone_analyzer.py
Tone and Voice Analysis Engine.
Evaluates content against approved brand voice rules, negative examples,
and tone guidelines using deterministic rules and local Ollama when available.

Confidence values:
  - Negative example match: 0.920 — exact string match from approved rule (high certainty)
  - Hyperbole pattern:      0.880 — regex pattern match, not rule-specific text
  - LLM contextual:         0.800 — LLM judgment, lower certainty, not deterministic
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


def _deduplicate_tone_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove overlapping tone findings for the same rule.

    When a full phrase (e.g. "game-changing miracle") and a substring
    ("game-changing") both match for the same rule at overlapping character
    positions, only the longest / most specific finding is kept.

    Algorithm:
      1. Sort candidates by span length descending (longest first).
      2. For each candidate, discard it if its [start, end) range overlaps
         with any already-accepted finding that shares the same rule_id.
    """
    # Separate tone findings from other categories (shouldn't mix, but be safe)
    tone = [f for f in findings if f.get("category") == DetectionCategory.TONE]
    other = [f for f in findings if f.get("category") != DetectionCategory.TONE]

    # Sort by span length descending so longer matches win
    tone.sort(key=lambda f: f.get("char_offset_end", 0) - f.get("char_offset_start", 0), reverse=True)

    accepted: List[Dict[str, Any]] = []

    for candidate in tone:
        c_start = candidate.get("char_offset_start", -1)
        c_end = candidate.get("char_offset_end", -1)
        c_rule = candidate.get("rule_id")
        c_source = candidate.get("source")

        # LLM findings are contextual and have no precise overlap to test
        if c_source == FindingSource.LIVE_LLM:
            accepted.append(candidate)
            continue

        overlaps = False
        for acc in accepted:
            a_start = acc.get("char_offset_start", -1)
            a_end = acc.get("char_offset_end", -1)
            a_rule = acc.get("rule_id")
            a_source = acc.get("source")

            # Only suppress overlap within the same rule and same detection method
            if a_rule != c_rule or a_source == FindingSource.LIVE_LLM:
                continue

            # Check for character-range overlap
            if c_start < a_end and c_end > a_start:
                overlaps = True
                break

        if not overlaps:
            accepted.append(candidate)

    return other + accepted


class ToneAnalyzer:
    """Tone detection engine based on approved Constitution rules."""

    @classmethod
    def analyze(
        cls,
        segments: List[Dict[str, Any]],
        raw_text: str,
        rules: List[BrandRule],
        ollama_client: Optional[LocalOllamaClient] = None
    ) -> List[Dict[str, Any]]:
        findings = []

        # Filter strictly for ACTIVE tone and writing style rules
        tone_rules = [
            r for r in rules
            if r.status == EntityStatus.ACTIVE
            and r.category in [RuleCategory.TONE_VOICE, RuleCategory.WRITING_STYLE]
        ]
        if not tone_rules or not segments:
            return findings

        for rule in tone_rules:
            # 1. Deterministic Negative Example Matching
            # Negative examples in rule configuration are explicit tone violations.
            # Confidence: 0.920 — exact string match from approved rule (high certainty).
            if rule.examples_negative:
                for neg_ex in rule.examples_negative:
                    neg_clean = neg_ex.strip()
                    if not neg_clean or len(neg_clean) < 3:
                        continue

                    pattern = re.compile(r'\b' + re.escape(neg_clean) + r'\b', re.IGNORECASE)
                    for seg in segments:
                        text = seg.get("text", "")
                        for match in pattern.finditer(text):
                            snippet = match.group(0)
                            base_offset = seg.get("char_start", 0)
                            start = base_offset + match.start()
                            end = base_offset + match.end()

                            # Positive example as suggestion if available
                            suggested = rule.examples_positive[0] if rule.examples_positive else None

                            findings.append({
                                "category": DetectionCategory.TONE,
                                "severity": SeverityLevel.HIGH,
                                "confidence": 0.920,
                                "flagged_snippet": snippet,
                                "char_offset_start": max(0, start),
                                "char_offset_end": max(0, end),
                                "explanation": (
                                    f"Tone violation: '{snippet}' directly matches an unapproved negative example "
                                    f"for tone rule [{rule.rule_code}]: '{rule.title}'. {rule.description}"
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

            # 2. Rule-Specific Tone Guardrails (e.g. anti-hyperbole, anti-slang)
            # Confidence: 0.880 — regex pattern match, not rule-specific wording.
            desc_lower = rule.description.lower()
            if "hyperbole" in desc_lower or "exaggerated" in desc_lower or "unsubstantiated" in desc_lower:
                hyperbole_pat = re.compile(
                    r'\b(game-changing|revolutionary|magic|miraculous|infinitely|unbelievable)\b',
                    re.IGNORECASE
                )
                for seg in segments:
                    text = seg.get("text", "")
                    for match in hyperbole_pat.finditer(text):
                        snippet = match.group(0)
                        base_offset = seg.get("char_start", 0)
                        start = base_offset + match.start()
                        end = base_offset + match.end()

                        findings.append({
                            "category": DetectionCategory.TONE,
                            "severity": SeverityLevel.MEDIUM,
                            "confidence": 0.880,
                            "flagged_snippet": snippet,
                            "char_offset_start": max(0, start),
                            "char_offset_end": max(0, end),
                            "explanation": (
                                f"Exaggerated tone detected in '{snippet}'. Approved rule [{rule.rule_code}] "
                                f"requires grounded, objective tone without hyperbolic language."
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
                            "suggested_correction": "grounded, factual phrasing",
                        })

            # 3. Contextual Local LLM Evaluation (if Ollama is active)
            # Confidence: 0.800 — LLM judgment, lower certainty, not deterministic.
            if ollama_client:
                health = ollama_client.check_health()
                if health.get("available") and health.get("model_ready"):
                    for seg in segments[:5]:  # Analyze key early segments contextually
                        text = seg.get("text", "")
                        prompt = (
                            f"Rule: {rule.title}\nDescription: {rule.description}\n"
                            f"Content: \"{text}\"\n"
                            f"Does this content violate the tone rule? Reply YES or NO followed by brief reason."
                        )
                        resp = ollama_client.generate_completion(prompt)
                        if resp and resp.upper().startswith("YES"):
                            reason = resp[3:].strip(": ").strip()
                            base_offset = seg.get("char_start", 0)
                            findings.append({
                                "category": DetectionCategory.TONE,
                                "severity": SeverityLevel.MEDIUM,
                                "confidence": 0.800,
                                "flagged_snippet": text[:100],
                                "char_offset_start": max(0, base_offset),
                                "char_offset_end": max(0, base_offset + min(100, len(text))),
                                "explanation": f"Contextual tone discrepancy with [{rule.rule_code}]: {reason}",
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

        # Deduplicate overlapping span findings within the same rule
        return _deduplicate_tone_findings(findings)
