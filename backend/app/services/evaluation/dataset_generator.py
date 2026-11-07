"""
app/services/evaluation/dataset_generator.py
Generates the synthetic ApexCloud Technologies evaluation dataset for Phase 7.
Contains representative marketing content covering all 6 compliance categories,
clean compliant text, ambiguous copy, and expired facts with ground-truth expectations.
"""
import uuid
from datetime import date
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.constitution import (
    BrandConstitution, BrandRule, FactRegistry, TermBank, BrandAsset,
    RuleCategory, EntityStatus
)
from app.models.evaluation import EvaluationDataset, EvaluationTestCase


# Standard Ground Truth Dataset definition
APEXCLOUD_BENCHMARK_CASES: List[Dict[str, Any]] = [
    # -------------------------------------------------------------------------
    # 1. Clean Compliant Content (Should generate ZERO findings)
    # -------------------------------------------------------------------------
    {
        "test_code": "TC-CLEAN-01",
        "title": "Compliant Enterprise Cloud Overview",
        "content_type": "TEXT",
        "input_content": (
            "ApexCloud provides cost-effective enterprise cloud infrastructure designed for high availability. "
            "Our enterprise starter plan starts at $79 per month with verified 99.99% uptime SLA. "
            "Explore enterprise solutions at our documentation portal."
        ),
        "content_metadata": {},
        "expected_findings": [],
        "expected_compliant": True,
        "is_ambiguous": False,
        "target_category": "CLEAN",
    },
    {
        "test_code": "TC-CLEAN-02",
        "title": "Compliant Product Press Release",
        "content_type": "TEXT",
        "input_content": (
            "ApexCloud announces global expansion into European regions with certified data sovereignty. "
            "Organizations benefit from competitive pricing and dedicated 24/7 technical assistance. "
            "For full technical specifications, explore the ApexCloud architecture guide."
        ),
        "content_metadata": {},
        "expected_findings": [],
        "expected_compliant": True,
        "is_ambiguous": False,
        "target_category": "CLEAN",
    },

    # -------------------------------------------------------------------------
    # 2. Terminology Violations
    # -------------------------------------------------------------------------
    {
        "test_code": "TC-TERM-01",
        "title": "Prohibited Brand Name Spacing",
        "content_type": "TEXT",
        "input_content": "Deploy your next application on Apex Cloud with automated multi-zone replication.",
        "content_metadata": {},
        "expected_findings": [
            {
                "category": "TERMINOLOGY",
                "flagged_snippet": "Apex Cloud",
                "cited_code": "TERM-APEXCLOUD",
                "severity": "HIGH",
                "explanation": "Brand name must be written as single word 'ApexCloud', never spaced as 'Apex Cloud'."
            }
        ],
        "expected_compliant": False,
        "is_ambiguous": False,
        "target_category": "TERMINOLOGY",
    },
    {
        "test_code": "TC-TERM-02",
        "title": "Prohibited Legacy Terminology",
        "content_type": "TEXT",
        "input_content": "Manage legacy workloads effortlessly using our CloudDesk portal interface.",
        "content_metadata": {},
        "expected_findings": [
            {
                "category": "TERMINOLOGY",
                "flagged_snippet": "CloudDesk",
                "cited_code": "TERM-LEGACY-01",
                "severity": "MEDIUM",
                "explanation": "Deprecated legacy product term 'CloudDesk' has been rebranded to 'ApexConsole'."
            }
        ],
        "expected_compliant": False,
        "is_ambiguous": False,
        "target_category": "TERMINOLOGY",
    },

    # -------------------------------------------------------------------------
    # 3. Tone & Voice Violations
    # -------------------------------------------------------------------------
    {
        "test_code": "TC-TONE-01",
        "title": "Discounting Language in Executive Copy",
        "content_type": "TEXT",
        "input_content": "Get cheap cloud servers for your startup with minimal financial commitment.",
        "content_metadata": {},
        "expected_findings": [
            {
                "category": "TONE",
                "flagged_snippet": "cheap",
                "cited_code": "RULE-TONE-PREMIUM",
                "severity": "HIGH",
                "explanation": "Prohibited discounting language 'cheap' undermines premium brand voice."
            }
        ],
        "expected_compliant": False,
        "is_ambiguous": False,
        "target_category": "TONE",
    },
    {
        "test_code": "TC-TONE-02",
        "title": "Informal Slang in Product Brief",
        "content_type": "TEXT",
        "input_content": "Our new Kubernetes engine is totally kickass and will blow your developers' minds.",
        "content_metadata": {},
        "expected_findings": [
            {
                "category": "TONE",
                "flagged_snippet": "kickass",
                "cited_code": "RULE-TONE-PROFESSIONAL",
                "severity": "HIGH",
                "explanation": "Colloquial slang violates professional enterprise tone guidelines."
            }
        ],
        "expected_compliant": False,
        "is_ambiguous": False,
        "target_category": "TONE",
    },

    # -------------------------------------------------------------------------
    # 4. Claims & Fact Verification
    # -------------------------------------------------------------------------
    {
        "test_code": "TC-CLAIM-01",
        "title": "Incorrect Pricing Claim",
        "content_type": "TEXT",
        "input_content": "Sign up for ApexCloud enterprise starter tier today for only $49 per month.",
        "content_metadata": {},
        "expected_findings": [
            {
                "category": "CLAIMS",
                "flagged_snippet": "$49",
                "cited_code": "FACT-PRICE-STARTER",
                "severity": "CRITICAL",
                "explanation": "Pricing claim '$49' contradicts official verified registry price of $79/month."
            }
        ],
        "expected_compliant": False,
        "is_ambiguous": False,
        "target_category": "CLAIMS",
    },
    {
        "test_code": "TC-CLAIM-02",
        "title": "Unsupported Security Guarantee Claim",
        "content_type": "TEXT",
        "input_content": "ApexCloud provides 100% guaranteed zero-downtime SLA across all enterprise zones.",
        "content_metadata": {},
        "expected_findings": [
            {
                "category": "CLAIMS",
                "flagged_snippet": "100% guaranteed",
                "cited_code": "RULE-CLAIM-UNSUPPORTED",
                "severity": "HIGH",
                "explanation": "Absolute guarantee claim requires verified technical proof."
            }
        ],
        "expected_compliant": False,
        "is_ambiguous": False,
        "target_category": "CLAIMS",
    },

    # -------------------------------------------------------------------------
    # 5. Messaging Alignment & Competitor Disparagement
    # -------------------------------------------------------------------------
    {
        "test_code": "TC-MSG-01",
        "title": "Direct Competitor Disparagement",
        "content_type": "TEXT",
        "input_content": "Unlike AWS which is broken and failing, ApexCloud is streamlined.",
        "content_metadata": {},
        "expected_findings": [
            {
                "category": "MESSAGING",
                "flagged_snippet": "AWS which is broken",
                "cited_code": "RULE-MSG-NO-DISPARAGE",
                "severity": "CRITICAL",
                "explanation": "Direct negative disparagement of named competitors violates fair messaging guidelines."
            }
        ],
        "expected_compliant": False,
        "is_ambiguous": False,
        "target_category": "MESSAGING",
    },

    # -------------------------------------------------------------------------
    # 6. Visual & Color Consistency
    # -------------------------------------------------------------------------
    {
        "test_code": "TC-VISUAL-01",
        "title": "Unapproved Brand Color Hex in Marketing Asset",
        "content_type": "TEXT",
        "input_content": "ApexCloud brand banners with background accent #FF00FF and neon text elements.",
        "content_metadata": {
            "detected_colors": ["#FF00FF", "#00FF00"]
        },
        "expected_findings": [
            {
                "category": "VISUAL",
                "flagged_snippet": "#FF00FF",
                "cited_code": "RULE-VISUAL-PALETTE",
                "severity": "MEDIUM",
                "explanation": "Hex code #FF00FF is outside the approved ApexCloud brand palette."
            }
        ],
        "expected_compliant": False,
        "is_ambiguous": False,
        "target_category": "VISUAL",
    },

    # -------------------------------------------------------------------------
    # 7. Accessibility Violations
    # -------------------------------------------------------------------------
    {
        "test_code": "TC-A11Y-01",
        "title": "Vague Link Text Without Context",
        "content_type": "TEXT",
        "input_content": "To review our compliance certifications and security posture, click here.",
        "content_metadata": {},
        "expected_findings": [
            {
                "category": "ACCESSIBILITY",
                "flagged_snippet": "click here",
                "cited_code": "WCAG-2.4.4-LINK-PURPOSE",
                "severity": "MEDIUM",
                "explanation": "Vague link anchor 'click here' violates WCAG 2.4.4 Link Purpose in Context."
            }
        ],
        "expected_compliant": False,
        "is_ambiguous": False,
        "target_category": "ACCESSIBILITY",
    },

    # -------------------------------------------------------------------------
    # 8. Ambiguous Copy (Borderline Phrasing Testing Review Gating)
    # -------------------------------------------------------------------------
    {
        "test_code": "TC-AMBIG-01",
        "title": "Contextual Phrasing - Budget-Friendly",
        "content_type": "TEXT",
        "input_content": "ApexCloud offers budget-friendly hosting packages tailored for educational non-profits.",
        "content_metadata": {},
        "expected_findings": [
            {
                "category": "TONE",
                "flagged_snippet": "budget-friendly",
                "cited_code": "RULE-TONE-PREMIUM",
                "severity": "LOW",
                "explanation": "Borderline term 'budget-friendly' may be permissible in non-profit contexts but requires human approval."
            }
        ],
        "expected_compliant": False,
        "is_ambiguous": True,
        "target_category": "TONE",
    },
]


class EvaluationDatasetGenerator:
    """Creates and seeds standardized benchmark datasets for evaluation."""

    @classmethod
    def seed_apexcloud_benchmark(
        cls,
        db: Session,
        organization_id: uuid.UUID
    ) -> EvaluationDataset:
        """
        Seed or retrieve the synthetic ApexCloud Benchmark Dataset,
        ensuring active constitution entities exist for the organization.
        """
        # 1. Ensure Active Constitution exists
        const = db.query(BrandConstitution).filter(
            BrandConstitution.organization_id == organization_id,
            BrandConstitution.is_active == True
        ).first()
        if not const:
            const = BrandConstitution(
                id=str(uuid.uuid4()),
                organization_id=organization_id,
                title="ApexCloud Benchmark Constitution",
                version="2026.1",
                is_active=True
            )
            db.add(const)
            db.flush()

        # Seed TermBank terms
        term_map = {
            "TERM-APEXCLOUD": ("Apex Cloud", "ApexCloud", "Brand name must be single word ApexCloud"),
            "TERM-LEGACY-01": ("CloudDesk", "ApexConsole", "Deprecated legacy term CloudDesk"),
        }
        for code, (prohib, pref, ctx) in term_map.items():
            if not db.query(TermBank).filter(TermBank.organization_id == organization_id, TermBank.term_code == code).first():
                db.add(TermBank(
                    id=str(uuid.uuid4()),
                    organization_id=organization_id,
                    constitution_id=const.id,
                    term_code=code,
                    prohibited_term=prohib,
                    preferred_term=pref,
                    usage_context=ctx,
                    is_case_sensitive=False,
                    status=EntityStatus.ACTIVE
                ))

        # Seed BrandRules
        rule_specs = [
            ("RULE-TONE-PREMIUM", RuleCategory.TONE_VOICE, "Prohibit Discounting Language",
             "Discounting phrases undermine premium enterprise positioning", ["cost-effective"], ["cheap", "budget-friendly"]),
            ("RULE-TONE-PROFESSIONAL", RuleCategory.TONE_VOICE, "Prohibit Slang",
             "Colloquial slang violates professional enterprise tone", ["highly performant"], ["kickass"]),
            ("RULE-CLAIM-UNSUPPORTED", RuleCategory.MESSAGING_PILLAR, "Claim Substantiation & Proof",
             "Governs claim substantiation and prohibits unsupported absolute claims", ["verified SLA"], ["100% guaranteed"]),
            ("RULE-MSG-NO-DISPARAGE", RuleCategory.MESSAGING_PILLAR, "No Competitor Disparagement",
             "Prohibits direct negative disparagement and derogatory claims against named competitors like AWS or Azure", ["leading cloud solution"], []),
            ("WCAG-2.4.4-LINK-PURPOSE", RuleCategory.ACCESSIBILITY, "Descriptive Link Text",
             "WCAG 2.4.4 Link Purpose in Context requires clear destination anchor text", ["Explore documentation"], ["click here"]),
        ]
        for r_code, cat, title, desc, pos, neg in rule_specs:
            if not db.query(BrandRule).filter(BrandRule.organization_id == organization_id, BrandRule.rule_code == r_code).first():
                db.add(BrandRule(
                    id=str(uuid.uuid4()),
                    organization_id=organization_id,
                    constitution_id=const.id,
                    rule_code=r_code,
                    category=cat,
                    title=title,
                    description=desc,
                    examples_positive=pos,
                    examples_negative=neg,
                    status=EntityStatus.ACTIVE
                ))

        # Seed FactRegistry
        if not db.query(FactRegistry).filter(FactRegistry.organization_id == organization_id, FactRegistry.fact_code == "FACT-PRICE-STARTER").first():
            db.add(FactRegistry(
                id=str(uuid.uuid4()),
                organization_id=organization_id,
                constitution_id=const.id,
                fact_code="FACT-PRICE-STARTER",
                claim_type="PRICING",
                statement="ApexCloud Enterprise Starter tier is priced at $79 per seat monthly.",
                numerical_value=79.0,
                unit="$",
                source_reference="2026 Master Pricing Schedule",
                fact_owner="Finance and Commercial Operations",
                expiry_date=date(2028, 12, 31),
                status=EntityStatus.ACTIVE
            ))

        # Seed BrandAsset
        if not db.query(BrandAsset).filter(BrandAsset.organization_id == organization_id, BrandAsset.asset_code == "RULE-VISUAL-PALETTE").first():
            db.add(BrandAsset(
                id=str(uuid.uuid4()),
                organization_id=organization_id,
                constitution_id=const.id,
                asset_code="RULE-VISUAL-PALETTE",
                asset_type="COLOR_PALETTE",
                name="Approved Brand Palette",
                specifications={"approved_hexes": ["#0052cc", "#0033aa", "#002288"]},
                status=EntityStatus.ACTIVE
            ))

        dataset = db.query(EvaluationDataset).filter(
            EvaluationDataset.organization_id == organization_id,
            EvaluationDataset.name == "ApexCloud Gold Benchmark Dataset",
            EvaluationDataset.version == "1.0"
        ).first()

        if not dataset:
            dataset = EvaluationDataset(
                id=uuid.uuid4(),
                organization_id=organization_id,
                name="ApexCloud Gold Benchmark Dataset",
                description="Synthetic evaluation benchmark representing clean content, category violations, and edge-cases.",
                dataset_type="BENCHMARK",
                version="1.0",
                is_active=True
            )
            db.add(dataset)
            db.commit()
            db.refresh(dataset)

        # Seed test cases if not already present
        for case_data in APEXCLOUD_BENCHMARK_CASES:
            existing = db.query(EvaluationTestCase).filter(
                EvaluationTestCase.organization_id == organization_id,
                EvaluationTestCase.dataset_id == dataset.id,
                EvaluationTestCase.test_code == case_data["test_code"]
            ).first()

            if not existing:
                tc = EvaluationTestCase(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    dataset_id=dataset.id,
                    test_code=case_data["test_code"],
                    title=case_data["title"],
                    content_type=case_data["content_type"],
                    input_content=case_data["input_content"],
                    content_metadata=case_data.get("content_metadata", {}),
                    expected_findings=case_data.get("expected_findings", []),
                    expected_compliant=case_data.get("expected_compliant", False),
                    is_ambiguous=case_data.get("is_ambiguous", False),
                    target_category=case_data.get("target_category")
                )
                db.add(tc)
            else:
                existing.input_content = case_data["input_content"]
                existing.content_metadata = case_data.get("content_metadata", {})
                existing.expected_findings = case_data.get("expected_findings", [])
                existing.expected_compliant = case_data.get("expected_compliant", False)
                existing.is_ambiguous = case_data.get("is_ambiguous", False)
                existing.target_category = case_data.get("target_category")

        db.commit()
        db.refresh(dataset)
        return dataset
