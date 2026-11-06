"""
app/services/evaluation/guideline_intelligence.py
Guideline Clarity & Intelligence Engine (Phase 7).
Analyzes human review decisions, dispute/dismissal ratios, and rule text ambiguity.
Distinguishes between genuine violations, ambiguous guidelines, reviewer preferences,
and legitimate exceptions.
CRITICAL: Recommendations require human approval before mutating the Brand Constitution.
"""
import uuid
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models.constitution import BrandRule, BrandConstitution, EntityStatus, RuleCategory
from app.models.finding import Finding, FindingStatus
from app.models.review import FindingDecision, FindingDecisionType, Review, ReviewHistory


# Vague/subjective terms that indicate ambiguous guidelines when used without concrete thresholds
AMBIGUOUS_KEYWORDS = [
    "reasonable", "appropriate", "good", "bad", "suitable", "natural",
    "acceptable", "proper", "moderate", "fairly", "somewhat", "high quality",
    "professional looking", "standard", "normal", "best effort"
]


class GuidelineIntelligenceEngine:
    """
    Analyzes historical review data and constitution rules to generate actionable
    intelligence for brand managers.
    """

    @classmethod
    def analyze_rule_performance(
        cls,
        db: Session,
        organization_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        """
        Compute decision statistics for each active brand rule based on actual Phase 6 reviews.
        """
        rules = db.query(BrandRule).filter(
            BrandRule.organization_id == organization_id,
            BrandRule.status == EntityStatus.ACTIVE
        ).all()

        rule_stats = []

        for r in rules:
            # Query all decisions associated with findings citing this rule
            decisions = db.query(FindingDecision).join(
                Finding, FindingDecision.finding_id == Finding.id
            ).filter(
                Finding.organization_id == organization_id,
                Finding.rule_id == r.id
            ).all()

            total_decisions = len(decisions)
            accepted = sum(1 for d in decisions if d.decision == FindingDecisionType.ACCEPTED)
            dismissed = sum(1 for d in decisions if d.decision == FindingDecisionType.DISMISSED)
            disputed = sum(1 for d in decisions if d.decision == FindingDecisionType.DISPUTED)
            resolved = sum(1 for d in decisions if d.decision == FindingDecisionType.RESOLVED)

            # Dispute and Dismissal rates
            dispute_rate = round(disputed / total_decisions, 4) if total_decisions > 0 else 0.0
            dismissal_rate = round(dismissed / total_decisions, 4) if total_decisions > 0 else 0.0

            # Text ambiguity analysis
            ambiguity_score, detected_vague_terms = cls._calculate_ambiguity_score(
                r.title, r.description, dispute_rate, dismissal_rate
            )

            rule_stats.append({
                "rule_id": str(r.id),
                "rule_code": r.rule_code,
                "title": r.title,
                "category": r.category.value if hasattr(r.category, "value") else str(r.category),
                "total_decisions": total_decisions,
                "accepted_count": accepted,
                "dismissed_count": dismissed,
                "disputed_count": disputed,
                "resolved_count": resolved,
                "dispute_rate": dispute_rate,
                "dismissal_rate": dismissal_rate,
                "ambiguity_score": ambiguity_score,
                "detected_vague_terms": detected_vague_terms,
                "needs_review": (dispute_rate > 0.25 or dismissal_rate > 0.35 or ambiguity_score > 0.6)
            })

        # Sort by highest ambiguity/dispute first
        rule_stats.sort(key=lambda x: (x["disputed_count"], x["ambiguity_score"]), reverse=True)
        return rule_stats

    @classmethod
    def detect_conflicting_rules(
        cls,
        db: Session,
        organization_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        """
        Detect contradictory guidelines within active rules.
        """
        rules = db.query(BrandRule).filter(
            BrandRule.organization_id == organization_id,
            BrandRule.status == EntityStatus.ACTIVE
        ).all()

        conflicts = []

        # Group rules by category
        by_cat: Dict[str, List[BrandRule]] = {}
        for r in rules:
            cat_val = r.category.value if hasattr(r.category, "value") else str(r.category)
            by_cat.setdefault(cat_val, []).append(r)

        # Cross-examine within category
        for cat, cat_rules in by_cat.items():
            for i in range(len(cat_rules)):
                for j in range(i + 1, len(cat_rules)):
                    r1 = cat_rules[i]
                    r2 = cat_rules[j]

                    conflict_reason = cls._check_pair_conflict(r1, r2)
                    if conflict_reason:
                        conflicts.append({
                            "rule_code_1": r1.rule_code,
                            "rule_title_1": r1.title,
                            "rule_code_2": r2.rule_code,
                            "rule_title_2": r2.title,
                            "category": cat,
                            "conflict_reason": conflict_reason,
                            "recommended_action": "Harmonize terminology and tone requirements in Constitution."
                        })

        return conflicts

    @classmethod
    def generate_clarity_recommendations(
        cls,
        db: Session,
        organization_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        """
        Produce categorized, actionable intelligence recommendations.
        Requires human authorization before Constitution mutation.
        """
        rule_stats = cls.analyze_rule_performance(db, organization_id)
        conflicts = cls.detect_conflicting_rules(db, organization_id)

        recommendations = []

        # 1. Ambiguous Guidelines Recommendations
        for stat in rule_stats:
            if stat["ambiguity_score"] > 0.5:
                vague_str = ", ".join([f"'{t}'" for t in stat["detected_vague_terms"]])
                recommendations.append({
                    "id": str(uuid.uuid4()),
                    "recommendation_type": "AMBIGUOUS_GUIDELINE",
                    "target_rule_code": stat["rule_code"],
                    "target_rule_title": stat["title"],
                    "severity": "MEDIUM",
                    "issue_summary": f"Subjective terms ({vague_str}) lead to reviewer ambiguity (Ambiguity Score: {stat['ambiguity_score']}).",
                    "action_suggested": "Add measurable thresholds, concrete examples, or explicit exclusion criteria.",
                    "requires_human_approval": True,
                    "applied": False
                })

        # 2. Frequently Dismissed Detections (False Positive Signals)
        for stat in rule_stats:
            if stat["total_decisions"] >= 2 and stat["dismissal_rate"] > 0.4:
                recommendations.append({
                    "id": str(uuid.uuid4()),
                    "recommendation_type": "FREQUENT_DISMISSAL",
                    "target_rule_code": stat["rule_code"],
                    "target_rule_title": stat["title"],
                    "severity": "HIGH",
                    "issue_summary": f"Reviewers dismiss detections under this rule {stat['dismissal_rate']*100:.0f}% of the time.",
                    "action_suggested": "Refine rule trigger regex or narrow applicability to avoid false-positive alert fatigue.",
                    "requires_human_approval": True,
                    "applied": False
                })

        # 3. Frequently Disputed Findings
        for stat in rule_stats:
            if stat["disputed_count"] > 0:
                recommendations.append({
                    "id": str(uuid.uuid4()),
                    "recommendation_type": "FREQUENT_DISPUTE",
                    "target_rule_code": stat["rule_code"],
                    "target_rule_title": stat["title"],
                    "severity": "HIGH",
                    "issue_summary": f"Content creators repeatedly dispute findings citing [{stat['rule_code']}].",
                    "action_suggested": "Hold brand alignment review between marketing creators and brand leads to clarify intent.",
                    "requires_human_approval": True,
                    "applied": False
                })

        # 4. Conflicting Rules
        for c in conflicts:
            recommendations.append({
                "id": str(uuid.uuid4()),
                "recommendation_type": "RULE_CONFLICT",
                "target_rule_code": f"{c['rule_code_1']} vs {c['rule_code_2']}",
                "target_rule_title": f"{c['rule_title_1']} vs {c['rule_title_2']}",
                "severity": "CRITICAL",
                "issue_summary": c["conflict_reason"],
                "action_suggested": c["recommended_action"],
                "requires_human_approval": True,
                "applied": False
            })

        return recommendations

    # --- Private Helpers ---

    @classmethod
    def _calculate_ambiguity_score(
        cls,
        title: str,
        description: str,
        dispute_rate: float,
        dismissal_rate: float
    ) -> Tuple[float, List[str]]:
        """
        Heuristic ambiguity score combining textual vagueness and review friction.
        """
        combined = f"{title} {description}".lower()
        found_terms = [t for t in AMBIGUOUS_KEYWORDS if re.search(r'\b' + re.escape(t) + r'\b', combined)]

        # Base text score: 0.2 per vague term, max 0.6
        text_score = min(0.6, len(found_terms) * 0.2)

        # Review friction bonus: up to 0.4
        friction_score = (dispute_rate * 0.25) + (dismissal_rate * 0.15)

        total_score = round(min(1.0, text_score + friction_score), 2)
        return total_score, found_terms

    @classmethod
    def _check_pair_conflict(cls, r1: BrandRule, r2: BrandRule) -> Optional[str]:
        """Check if two rules in the same category have opposing directions."""
        t1 = f"{r1.title} {r1.description}".lower()
        t2 = f"{r2.title} {r2.description}".lower()

        # Formal vs Casual conflict
        if ("formal" in t1 and "casual" in t2) or ("casual" in t1 and "formal" in t2):
            return "Contradictory tone direction: One rule specifies formal tone while another allows or recommends casual phrasing."

        # Technical vs Simplified conflict
        if ("deep technical" in t1 and "plain language" in t2) or ("plain language" in t1 and "deep technical" in t2):
            return "Conflicting technical specificity: One rule mandates simplified plain language while another mandates deep technical terminology."

        return None
