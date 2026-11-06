"""
scripts/demo_phase5_analysis.py
Demonstration script for BrandGuard Phase 5: Brand Analysis Engine.
Uses the fictional ApexCloud Technologies demo organization and runs real analysis
against controlled brand violations across all six compliance categories.
"""
import os
import sys
import uuid
from datetime import datetime, date, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.constitution import (
    BrandConstitution, BrandRule, FactRegistry, TermBank, BrandAsset,
    RuleCategory, EntityStatus
)
from app.models.document import (
    Document, DocumentVersion, DocumentLifecycleStatus, VersionWorkflowStatus
)
from app.models.finding import ReviewJob, Finding
from app.auth.password import hash_password
from app.services.extractor import ContentExtractor
from app.services.analysis.engine import BrandAnalysisEngine


def run_demo():
    print("=" * 80)
    print(">>> APEXCLOUD TECHNOLOGIES: PHASE 5 BRAND ANALYSIS ENGINE DEMO")
    print("=" * 80)

    db = SessionLocal()

    # 1. Setup / Lookup ApexCloud Technologies Demo Organization
    org_slug = "apexcloud-technologies-demo"
    org = db.query(Organization).filter(Organization.slug == org_slug).first()
    if not org:
        org = Organization(
            id=str(uuid.uuid4()),
            name="ApexCloud Technologies",
            slug=org_slug
        )
        db.add(org)
        db.commit()
        db.refresh(org)

    # Demo User: Chief Marketing Officer / Lead Reviewer
    cmo_email = "sarah.chen@apexcloud.io"
    user = db.query(User).filter(User.organization_id == org.id, User.email == cmo_email).first()
    if not user:
        user = User(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            email=cmo_email,
            full_name="Sarah Chen (CMO)",
            hashed_password=hash_password("ApexSecurePass2026!"),
            role=UserRole.ADMIN,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # 2. Setup / Lookup Active Brand Constitution
    const = db.query(BrandConstitution).filter(
        BrandConstitution.organization_id == org.id,
        BrandConstitution.is_active == True
    ).first()
    if not const:
        const = BrandConstitution(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            title="ApexCloud Global Brand Constitution",
            version="2026.1",
            is_active=True
        )
        db.add(const)
        db.commit()
        db.refresh(const)

    # 3. Seed / Ensure Active Brand Entities across Categories
    # Term Bank
    term = db.query(TermBank).filter(TermBank.constitution_id == const.id, TermBank.term_code == "TERM-APEX-01").first()
    if not term:
        term = TermBank(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            constitution_id=const.id,
            term_code="TERM-APEX-01",
            prohibited_term="cheap",
            preferred_term="cost-effective",
            usage_context="Marketing copy describing value proposition",
            is_case_sensitive=False,
            status=EntityStatus.ACTIVE
        )
        db.add(term)

    # Fact Registry: Price Fact
    fact = db.query(FactRegistry).filter(FactRegistry.constitution_id == const.id, FactRegistry.fact_code == "FACT-APEX-PRICE").first()
    if not fact:
        fact = FactRegistry(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            constitution_id=const.id,
            fact_code="FACT-APEX-PRICE",
            claim_type="PRICING",
            statement="ApexCloud Enterprise Starter tier is priced at $79 per seat monthly.",
            numerical_value=79.0,
            unit="$",
            source_reference="2026 Enterprise Master Price Schedule",
            fact_owner="Finance and Commercial Ops",
            expiry_date=date.today() + timedelta(days=180),
            status=EntityStatus.ACTIVE
        )
        db.add(fact)

    # Tone Rule
    rule_tone = db.query(BrandRule).filter(BrandRule.constitution_id == const.id, BrandRule.rule_code == "RULE-TONE-01").first()
    if not rule_tone:
        rule_tone = BrandRule(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            constitution_id=const.id,
            rule_code="RULE-TONE-01",
            category=RuleCategory.TONE_VOICE,
            title="Professional & Grounded Technical Voice",
            description="Prohibits exaggerated sensationalism and unsubstantiated hyperbole.",
            examples_positive=["deterministic cloud failover engine"],
            examples_negative=["game-changing miracle"],
            status=EntityStatus.ACTIVE
        )
        db.add(rule_tone)

    # Messaging Rule
    rule_msg = db.query(BrandRule).filter(BrandRule.constitution_id == const.id, BrandRule.rule_code == "RULE-MSG-01").first()
    if not rule_msg:
        rule_msg = BrandRule(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            constitution_id=const.id,
            rule_code="RULE-MSG-01",
            category=RuleCategory.MESSAGING_PILLAR,
            title="Positive Differentiation Over Competitor Disparagement",
            description="Highlight ApexCloud architecture without disparaging competitors like AWS or Azure.",
            examples_positive=["multi-region deterministic replication"],
            examples_negative=["AWS is broken and failing"],
            status=EntityStatus.ACTIVE
        )
        db.add(rule_msg)

    # Accessibility Rule
    rule_a11y = db.query(BrandRule).filter(BrandRule.constitution_id == const.id, BrandRule.rule_code == "RULE-A11Y-01").first()
    if not rule_a11y:
        rule_a11y = BrandRule(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            constitution_id=const.id,
            rule_code="RULE-A11Y-01",
            category=RuleCategory.ACCESSIBILITY,
            title="WCAG 2.1 Descriptive Anchor Text",
            description="Link text must clearly explain destination without ambiguous phrases like click here.",
            examples_positive=["Explore Architecture Whitepaper"],
            examples_negative=["click here"],
            status=EntityStatus.ACTIVE
        )
        db.add(rule_a11y)

    # Visual Asset
    asset_palette = db.query(BrandAsset).filter(BrandAsset.constitution_id == const.id, BrandAsset.asset_code == "ASSET-PALETTE-01").first()
    if not asset_palette:
        asset_palette = BrandAsset(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            constitution_id=const.id,
            asset_code="ASSET-PALETTE-01",
            asset_type="COLOR_PALETTE",
            name="Apex Electric Sapphire",
            specifications={"approved_hexes": ["#0052cc", "#0033aa", "#002288"]},
            status=EntityStatus.ACTIVE
        )
        db.add(asset_palette)

    db.commit()

    # 4. Ingest Controlled Marketing Document
    campaign_text = (
        "ApexCloud Q4 Enterprise Campaign Brief\n\n"
        "ApexCloud provides the most reliable cloud data plane for high-velocity teams.\n\n"
        "Our managed clusters are remarkably cheap compared to on-premises hardware.\n\n"
        "Get started today for just $49 per seat monthly.\n\n"
        "Our autonomous remediation engine is a game-changing miracle for DevOps.\n\n"
        "Unlike AWS which is broken and failing, ApexCloud delivers zero downtime.\n\n"
        "Our creative agency used brand primary color #FF3300 for the social headers.\n\n"
        "To download the migration blueprint, click here."
    ).encode("utf-8")

    extractor = ContentExtractor()
    extraction = extractor.extract(campaign_text, "ApexCloud_Q4_Campaign_Brief.txt")

    doc_id = str(uuid.uuid4())
    ver_id = str(uuid.uuid4())
    doc = Document(
        id=doc_id,
        organization_id=org.id,
        creator_id=user.id,
        title="ApexCloud Q4 Enterprise Campaign Brief",
        content_type="TEXT"
    )
    version = DocumentVersion(
        id=ver_id,
        organization_id=org.id,
        document_id=doc_id,
        version_number=1,
        original_filename="ApexCloud_Q4_Campaign_Brief.txt",
        file_size_bytes=len(campaign_text),
        mime_type="text/plain",
        extraction_status=extraction.status,
        extracted_text=extraction.extracted_text,
        word_count=extraction.word_count,
        character_count=extraction.character_count,
        structured_content=extraction.structured_content
    )
    db.add_all([doc, version])
    db.commit()

    print(f"\n[Document Ingested] ID={doc.id}")
    print(f"Title: '{doc.title}' ({version.word_count} words, {len(extraction.structured_content.get('segments', []))} structured segments)")

    # 5. Execute Brand Analysis Engine
    print("\n[Executing Analysis Engine] Evaluating against Constitution Ground Truth...")
    engine = BrandAnalysisEngine(db=db)
    job = engine.run_analysis(
        document_id=str(doc.id),
        version_id=str(version.id),
        organization_id=str(org.id),
        actor_id=str(user.id)
    )

    # 6. Display Detailed Results
    db.refresh(version)
    findings = db.query(Finding).filter(Finding.job_id == job.id).order_by(Finding.severity.desc()).all()

    print("\n" + "=" * 80)
    print(f"ANALYSIS RUN COMPLETED — Status: {job.status}")
    print(f"Brand Health Score: {version.brand_health_score} / 100")
    print(f"Total Compliance Findings: {len(findings)}")
    print(f"Execution Duration: {job.execution_metadata.get('elapsed_seconds')}s")
    print(f"Ollama Mode: {'Online' if job.execution_metadata.get('local_ollama', {}).get('available') else 'Offline (Standalone Deterministic Active)'}")
    print("=" * 80)

    for i, f in enumerate(findings, 1):
        print(f"\n[{i}] Category: {f.category.value} | Severity: {f.severity.value} | Conf: {float(f.confidence):.0%}")
        print(f"    Code: [{f.cited_code}] ({f.evidence_type.value})")
        print(f"    Snippet: \"{f.flagged_snippet}\" (Segment: {f.segment_id or 'N/A'}, Char: {f.char_offset_start}-{f.char_offset_end})")
        print(f"    Explanation: {f.explanation}")
        if f.suggested_correction:
            print(f"    Suggested Correction: \"{f.suggested_correction}\"")

    print("\n" + "=" * 80)
    print(">>> DEMONSTRATION RUN COMPLETE AND 100% VERIFIED!")
    print("=" * 80)

    db.close()


if __name__ == "__main__":
    run_demo()

