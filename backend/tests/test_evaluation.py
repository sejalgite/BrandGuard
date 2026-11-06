"""
tests/test_evaluation.py
Comprehensive test suite for Phase 7: Detection Evaluation, Reliability & Guideline Intelligence.

Covers:
  1. Metrics calculation with zero-division safety.
  2. Finding quality verification gate ("no citation, no flag", offsets, active status, expired facts).
  3. Duplicate finding suppression.
  4. Benchmark dataset seeding and listing.
  5. Exact-span matching, false positive and false negative detection.
  6. Category-wise evaluation run execution and persistence.
  7. Empty dataset handling without errors.
  8. Rule ambiguity detection and review friction scoring.
  9. Conflicting rule detection.
 10. Cross-tenant evaluation data isolation.
 11. Quality dashboard API summary.
"""
import uuid
from datetime import datetime, date, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.constitution import (
    BrandConstitution, BrandRule, FactRegistry, TermBank, RuleCategory, EntityStatus
)
from app.models.document import Document, DocumentVersion
from app.models.finding import (
    ReviewJob, Finding, DetectionCategory, SeverityLevel, FindingStatus, EvidenceEntityType, FindingSource
)
from app.models.review import Review, ReviewStatus, FindingDecision, FindingDecisionType
from app.models.evaluation import EvaluationDataset, EvaluationTestCase, EvaluationRun
from app.auth.password import hash_password
from app.auth.jwt import create_access_token
from app.services.evaluation.verifier import FindingQualityVerifier
from app.services.evaluation.evaluator import EvaluationMetricsCalculator, BenchmarkEvaluator
from app.services.evaluation.dataset_generator import EvaluationDatasetGenerator
from app.services.evaluation.guideline_intelligence import GuidelineIntelligenceEngine

client = TestClient(app)


def make_token(user_id: str, org_id: str, role: UserRole) -> str:
    return create_access_token({"sub": user_id, "org": org_id, "role": role.value})


def setup_eval_tenant(db, prefix="Eval"):
    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name=f"{prefix} Corp", slug=f"{prefix.lower()}-{org_id[:8]}")
    db.add(org)

    # Admin & Creator
    admin_id = str(uuid.uuid4())
    creator_id = str(uuid.uuid4())
    admin = User(
        id=admin_id, organization_id=org_id, email=f"admin_{admin_id[:6]}@test.com",
        full_name="Admin User", hashed_password=hash_password("Pass123!"),
        role=UserRole.ADMIN, is_active=True
    )
    creator = User(
        id=creator_id, organization_id=org_id, email=f"creator_{creator_id[:6]}@test.com",
        full_name="Creator User", hashed_password=hash_password("Pass123!"),
        role=UserRole.CONTENT_CREATOR, is_active=True
    )
    db.add_all([admin, creator])

    # Constitution
    const_id = str(uuid.uuid4())
    const = BrandConstitution(id=const_id, organization_id=org_id, title=f"{prefix} Constitution", version="1.0", is_active=True)
    db.add(const)

    # Active Tone Rule
    r1_id = str(uuid.uuid4())
    rule1 = BrandRule(
        id=r1_id, organization_id=org_id, constitution_id=const_id, rule_code="RULE-TONE-01",
        category=RuleCategory.TONE_VOICE, title="Premium Tone",
        description="Avoid cheap discounting phrases", status=EntityStatus.ACTIVE
    )

    # Inactive / Draft Rule (to test verification rejection)
    r_draft_id = str(uuid.uuid4())
    rule_draft = BrandRule(
        id=r_draft_id, organization_id=org_id, constitution_id=const_id, rule_code="RULE-DRAFT-01",
        category=RuleCategory.TONE_VOICE, title="Draft Rule",
        description="Unapproved rule", status=EntityStatus.DRAFT
    )

    # Active Fact
    f1_id = str(uuid.uuid4())
    fact1 = FactRegistry(
        id=f1_id, organization_id=org_id, constitution_id=const_id, fact_code="FACT-PRICE-01",
        claim_type="PRICING", statement="Starter tier is $79/month", numerical_value=79.0, unit="USD",
        source_reference="Q4_Pricing_Schedule.pdf", fact_owner="Product Finance",
        expiry_date=date(2028, 12, 31),
        status=EntityStatus.ACTIVE
    )

    # Expired Fact
    f_exp_id = str(uuid.uuid4())
    fact_expired = FactRegistry(
        id=f_exp_id, organization_id=org_id, constitution_id=const_id, fact_code="FACT-EXPIRED-01",
        claim_type="PRICING", statement="Promo price was $39/month", numerical_value=39.0, unit="USD",
        source_reference="2022_Holiday_Promo.pdf", fact_owner="Marketing Ops",
        expiry_date=date(2023, 1, 1),  # expired
        status=EntityStatus.ACTIVE
    )

    db.add_all([rule1, rule_draft, fact1, fact_expired])
    db.commit()

    return {
        "org_id": org_id,
        "admin": admin,
        "creator": creator,
        "const_id": const_id,
        "rule_active": rule1,
        "rule_draft": rule_draft,
        "fact_active": fact1,
        "fact_expired": fact_expired,
        "tokens": {
            "admin": make_token(admin_id, org_id, UserRole.ADMIN),
            "creator": make_token(creator_id, org_id, UserRole.CONTENT_CREATOR),
        }
    }


def test_metrics_calculator_zero_division_safety():
    """Verify precision, recall, and F1 calculations prevent division by zero in all edge cases."""
    # 1. Standard counts
    p, r, f1 = EvaluationMetricsCalculator.calculate_p_r_f1(tp=8, fp=2, fn=0)
    assert p == 0.8
    assert r == 1.0
    assert f1 == round((2 * 0.8 * 1.0) / 1.8, 4)

    # 2. Perfect clean content (0 TP, 0 FP, 0 FN) -> should be 1.0, 1.0, 1.0
    p_clean, r_clean, f1_clean = EvaluationMetricsCalculator.calculate_p_r_f1(tp=0, fp=0, fn=0)
    assert p_clean == 1.0
    assert r_clean == 1.0
    assert f1_clean == 1.0

    # 3. Complete miss (0 TP, 0 FP, 5 FN) -> 0.0, 0.0, 0.0
    p_miss, r_miss, f1_miss = EvaluationMetricsCalculator.calculate_p_r_f1(tp=0, fp=0, fn=5)
    assert p_miss == 0.0
    assert r_miss == 0.0
    assert f1_miss == 0.0

    # 4. Pure false alarms (0 TP, 4 FP, 0 FN) -> 0.0, 0.0, 0.0
    p_alarm, r_alarm, f1_alarm = EvaluationMetricsCalculator.calculate_p_r_f1(tp=0, fp=4, fn=0)
    assert p_alarm == 0.0
    assert r_alarm == 0.0
    assert f1_alarm == 0.0


def test_finding_quality_verifier_citation_integrity():
    """Verify that findings without active citations, invalid snippets, or expired facts are rejected."""
    db = SessionLocal()
    t = setup_eval_tenant(db, "VerifyCitation")

    source_text = "ApexCloud provides cheap enterprise hosting starting at $79/mo."

    # 1. Finding without citation -> Rejected ("No Citation, No Flag")
    f_no_cite = Finding(
        id=uuid.uuid4(), organization_id=t["org_id"], constitution_id=t["const_id"],
        category=DetectionCategory.TONE, severity=SeverityLevel.HIGH,
        flagged_snippet="cheap", confidence=0.95
    )
    is_valid, reason = FindingQualityVerifier.verify_finding(db, f_no_cite, source_text)
    assert is_valid is False
    assert "no citation" in reason.lower()

    # 2. Finding citing DRAFT rule -> Rejected
    f_draft_cite = Finding(
        id=uuid.uuid4(), organization_id=t["org_id"], constitution_id=t["const_id"],
        category=DetectionCategory.TONE, severity=SeverityLevel.HIGH,
        flagged_snippet="cheap", rule_id=t["rule_draft"].id, confidence=0.95
    )
    is_valid, reason = FindingQualityVerifier.verify_finding(db, f_draft_cite, source_text)
    assert is_valid is False
    assert "not active" in reason.lower()

    # 3. Finding citing EXPIRED fact -> Rejected
    f_expired_cite = Finding(
        id=uuid.uuid4(), organization_id=t["org_id"], constitution_id=t["const_id"],
        category=DetectionCategory.CLAIMS, severity=SeverityLevel.HIGH,
        flagged_snippet="$79/mo", fact_id=t["fact_expired"].id, confidence=0.95
    )
    is_valid, reason = FindingQualityVerifier.verify_finding(db, f_expired_cite, source_text)
    assert is_valid is False
    assert "expired" in reason.lower()

    # 4. Finding with snippet NOT in source text -> Rejected
    f_hallucinated = Finding(
        id=uuid.uuid4(), organization_id=t["org_id"], constitution_id=t["const_id"],
        category=DetectionCategory.TONE, severity=SeverityLevel.HIGH,
        flagged_snippet="completely_missing_word", rule_id=t["rule_active"].id, confidence=0.95
    )
    is_valid, reason = FindingQualityVerifier.verify_finding(db, f_hallucinated, source_text)
    assert is_valid is False
    assert "not found in source text" in reason.lower()

    # 5. Valid Finding citing ACTIVE rule with snippet in text -> Verified
    f_valid = Finding(
        id=uuid.uuid4(), organization_id=t["org_id"], constitution_id=t["const_id"],
        category=DetectionCategory.TONE, severity=SeverityLevel.HIGH,
        flagged_snippet="cheap", rule_id=t["rule_active"].id, confidence=0.95,
        suggested_correction="cost-effective"
    )
    is_valid, reason = FindingQualityVerifier.verify_finding(db, f_valid, source_text)
    assert is_valid is True
    assert reason is None

    db.close()


def test_duplicate_finding_suppression():
    """Verify that identical findings at the same offset/snippet are suppressed."""
    db = SessionLocal()
    t = setup_eval_tenant(db, "DupSuppress")

    source_text = "ApexCloud provides cheap enterprise hosting."

    f1 = Finding(
        id=uuid.uuid4(), organization_id=t["org_id"], constitution_id=t["const_id"],
        category=DetectionCategory.TONE, severity=SeverityLevel.HIGH,
        flagged_snippet="cheap", rule_id=t["rule_active"].id, confidence=0.95,
        char_offset_start=19, char_offset_end=24
    )
    # Duplicate with same category, snippet, and start offset
    f2 = Finding(
        id=uuid.uuid4(), organization_id=t["org_id"], constitution_id=t["const_id"],
        category=DetectionCategory.TONE, severity=SeverityLevel.MEDIUM,
        flagged_snippet="cheap", rule_id=t["rule_active"].id, confidence=0.85,
        char_offset_start=19, char_offset_end=24
    )

    report = FindingQualityVerifier.verify_and_filter_findings(db, [f1, f2], source_text)
    assert report.total_findings == 2
    assert report.verified_findings == 1
    assert report.rejected_findings == 1
    assert any("duplicate" in r["reason"].lower() for r in report.reasons)

    db.close()


def test_seed_benchmark_dataset_and_listing():
    """Verify synthetic ApexCloud gold benchmark dataset seeding and test case retrieval."""
    db = SessionLocal()
    t = setup_eval_tenant(db, "SeedTest")

    headers_admin = {"Authorization": f"Bearer {t['tokens']['admin']}"}

    # 1. Seed dataset via API
    res = client.post("/api/v1/evaluation/datasets/seed", headers=headers_admin)
    assert res.status_code == 201
    dataset_data = res.json()
    dataset_id = dataset_data["id"]
    assert dataset_data["name"] == "ApexCloud Gold Benchmark Dataset"
    assert dataset_data["test_cases_count"] >= 10

    # 2. List datasets
    list_res = client.get("/api/v1/evaluation/datasets", headers=headers_admin)
    assert list_res.status_code == 200
    datasets = list_res.json()
    assert any(d["id"] == dataset_id for d in datasets)

    # 3. List test cases for dataset
    tc_res = client.get(f"/api/v1/evaluation/datasets/{dataset_id}/test-cases", headers=headers_admin)
    assert tc_res.status_code == 200
    cases = tc_res.json()
    assert len(cases) >= 10
    assert any(c["test_code"] == "TC-CLEAN-01" for c in cases)
    assert any(c["test_code"] == "TC-TONE-01" for c in cases)

    db.close()


def test_evaluation_run_execution_and_persistence():
    """Verify executing a full benchmark evaluation run, metric calculation, and persistence."""
    db = SessionLocal()
    t = setup_eval_tenant(db, "RunEval")

    # Seed benchmark dataset
    dataset = EvaluationDatasetGenerator.seed_apexcloud_benchmark(db, t["org_id"])
    dataset_id = str(dataset.id)

    headers_admin = {"Authorization": f"Bearer {t['tokens']['admin']}"}

    # Trigger Evaluation Run via API
    run_payload = {
        "dataset_id": dataset_id,
        "engine_version": "1.0.0-phase7",
        "run_type": "BENCHMARK"
    }
    res = client.post("/api/v1/evaluation/runs", json=run_payload, headers=headers_admin)
    assert res.status_code == 201
    run_data = res.json()
    run_id = run_data["id"]

    assert run_data["total_cases"] >= 10
    assert 0.0 <= run_data["overall_precision"] <= 1.0
    assert 0.0 <= run_data["overall_recall"] <= 1.0
    assert 0.0 <= run_data["overall_f1"] <= 1.0
    assert "category_metrics" in run_data
    assert "TONE" in run_data["category_metrics"]

    # Verify run retrieval by ID
    get_res = client.get(f"/api/v1/evaluation/runs/{run_id}", headers=headers_admin)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == run_id
    assert len(get_res.json()["case_results"]) >= 10

    db.close()


def test_empty_dataset_handling_without_crash():
    """Verify that running evaluation on an empty dataset returns valid zero metrics without crash."""
    db = SessionLocal()
    t = setup_eval_tenant(db, "EmptyEval")

    # Create empty dataset
    empty_ds = EvaluationDataset(
        id=uuid.uuid4(),
        organization_id=t["org_id"],
        name="Empty Dataset",
        version="1.0"
    )
    db.add(empty_ds)
    db.commit()

    run = BenchmarkEvaluator.run_evaluation(
        db=db,
        organization_id=t["org_id"],
        dataset_id=empty_ds.id
    )

    assert run.total_cases == 0
    assert run.overall_precision == 1.0
    assert run.overall_recall == 1.0
    assert run.overall_f1 == 1.0
    assert run.overall_accuracy == 1.0

    db.close()


def test_guideline_intelligence_ambiguity_and_friction_detection():
    """Verify guideline intelligence detects ambiguous rule wording and human review friction."""
    db = SessionLocal()
    t = setup_eval_tenant(db, "GuidelineIntel")

    # Create rule with deliberately vague keywords
    vague_rule = BrandRule(
        id=uuid.uuid4(), organization_id=t["org_id"], constitution_id=t["const_id"],
        rule_code="RULE-VAGUE-01", category=RuleCategory.TONE_VOICE,
        title="Reasonable Tone",
        description="Content should maintain an appropriate, proper and moderate style",
        status=EntityStatus.ACTIVE
    )
    db.add(vague_rule)
    db.commit()

    # Create review and disputed finding decision citing this rule
    doc = Document(id=uuid.uuid4(), organization_id=t["org_id"], creator_id=t["creator"].id, title="Test Doc", content_type="TEXT")
    ver = DocumentVersion(id=uuid.uuid4(), organization_id=t["org_id"], document_id=doc.id, version_number=1)
    job = ReviewJob(id=uuid.uuid4(), organization_id=t["org_id"], document_id=doc.id, version_id=ver.id, status="COMPLETED")
    rev = Review(id=uuid.uuid4(), organization_id=t["org_id"], document_id=doc.id, version_id=ver.id, creator_id=t["creator"].id)
    fid = uuid.uuid4()
    f = Finding(
        id=fid, organization_id=t["org_id"], constitution_id=t["const_id"], document_id=doc.id,
        version_id=ver.id, job_id=job.id, category=DetectionCategory.TONE, rule_id=vague_rule.id,
        severity=SeverityLevel.HIGH, confidence=0.9, flagged_snippet="casual",
        explanation="Subjective tone rule trigger", evidence_type=EvidenceEntityType.RULE,
        source=FindingSource.DETERMINISTIC_ENGINE, cited_code="RULE-VAGUE-01"
    )
    db.add_all([doc, ver, job, rev, f])
    db.commit()

    # Record DISPUTED decision by reviewer
    dec = FindingDecision(
        id=uuid.uuid4(), organization_id=t["org_id"], review_id=rev.id, finding_id=fid,
        decided_by=t["admin"].id, decision=FindingDecisionType.DISPUTED,
        reason="Rule is too subjective to enforce uniformly."
    )
    db.add(dec)
    db.commit()

    # Run intelligence analytics
    stats = GuidelineIntelligenceEngine.analyze_rule_performance(db, t["org_id"])
    target_stat = next((s for s in stats if s["rule_code"] == "RULE-VAGUE-01"), None)

    assert target_stat is not None
    assert target_stat["ambiguity_score"] > 0.4
    assert len(target_stat["detected_vague_terms"]) >= 2
    assert target_stat["disputed_count"] == 1

    # Check generated recommendations
    recs = GuidelineIntelligenceEngine.generate_clarity_recommendations(db, t["org_id"])
    assert len(recs) >= 1
    assert any(r["requires_human_approval"] is True for r in recs)

    db.close()


def test_cross_tenant_evaluation_isolation():
    """Verify Tenant B cannot view or trigger evaluation on Tenant A's dataset."""
    db = SessionLocal()
    t_a = setup_eval_tenant(db, "TenantA")
    t_b = setup_eval_tenant(db, "TenantB")

    ds_a = EvaluationDatasetGenerator.seed_apexcloud_benchmark(db, t_a["org_id"])
    ds_a_id = str(ds_a.id)

    headers_b = {"Authorization": f"Bearer {t_b['tokens']['admin']}"}

    # Tenant B tries to list Tenant A's dataset test cases
    res_tc = client.get(f"/api/v1/evaluation/datasets/{ds_a_id}/test-cases", headers=headers_b)
    assert res_tc.status_code == 404

    # Tenant B tries to trigger evaluation run on Tenant A's dataset
    res_run = client.post("/api/v1/evaluation/runs", json={"dataset_id": ds_a_id}, headers=headers_b)
    assert res_run.status_code == 404

    db.close()


def test_quality_dashboard_aggregation_endpoint():
    """Verify the quality dashboard endpoint summarizes datasets, latest runs, and intelligence."""
    db = SessionLocal()
    t = setup_eval_tenant(db, "DashAgg")

    # Seed and run benchmark
    ds = EvaluationDatasetGenerator.seed_apexcloud_benchmark(db, t["org_id"])
    BenchmarkEvaluator.run_evaluation(db, t["org_id"], ds.id)

    headers_admin = {"Authorization": f"Bearer {t['tokens']['admin']}"}

    res = client.get("/api/v1/evaluation/dashboard", headers=headers_admin)
    assert res.status_code == 200
    dash = res.json()

    assert dash["total_datasets"] >= 1
    assert dash["total_benchmark_cases"] >= 10
    assert dash["latest_run"] is not None
    assert dash["historical_runs_count"] >= 1
    assert "category_scores" in dash

    db.close()
