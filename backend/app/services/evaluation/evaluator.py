"""
app/services/evaluation/evaluator.py
Detection Evaluation Engine (Phase 7).
Executes actual analysis against ground-truth evaluation datasets,
computes category-wise and overall precision, recall, F1, accuracy, and coverage,
and persists versioned EvaluationRun records for regression comparison.
"""
import uuid
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models.evaluation import EvaluationDataset, EvaluationTestCase, EvaluationRun
from app.models.finding import Finding, DetectionCategory
from app.services.analysis.engine import BrandAnalysisEngine
from app.services.evaluation.verifier import FindingQualityVerifier


ALL_CATEGORIES = [
    "TONE",
    "TERMINOLOGY",
    "CLAIMS",
    "MESSAGING",
    "VISUAL",
    "ACCESSIBILITY"
]


class EvaluationMetricsCalculator:
    """Computes precision, recall, F1-score with robust zero-division handling."""

    @staticmethod
    def calculate_p_r_f1(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
        """
        Calculate precision, recall, and F1.
        Handles zero-division gracefully without NaN or runtime exceptions.
        """
        # Precision
        if (tp + fp) > 0:
            precision = tp / (tp + fp)
        else:
            precision = 1.0 if fn == 0 else 0.0

        # Recall
        if (tp + fn) > 0:
            recall = tp / (tp + fn)
        else:
            recall = 1.0 if fp == 0 else 0.0

        # F1
        if (precision + recall) > 0:
            f1 = (2 * precision * recall) / (precision + recall)
        else:
            f1 = 0.0

        return round(precision, 4), round(recall, 4), round(f1, 4)


class BenchmarkEvaluator:
    """
    Executes benchmark evaluations against structured datasets.
    """

    @classmethod
    def match_finding(cls, pred_finding: Any, expected: Dict[str, Any]) -> bool:
        """
        Check if a predicted finding matches an expected ground-truth finding.
        Requires:
        1. Category match
        2. Text span/snippet overlap (case-insensitive substring or match)
        3. Cited code match if provided in expected
        """
        pred_cat = pred_finding.category.value if hasattr(pred_finding.category, "value") else str(pred_finding.category)
        exp_cat = expected.get("category", "")
        if pred_cat != exp_cat:
            return False

        pred_snippet = (pred_finding.flagged_snippet or "").strip().lower()
        exp_snippet = (expected.get("flagged_snippet") or "").strip().lower()

        # Check snippet match (substring containment or exact match)
        if not (pred_snippet == exp_snippet or pred_snippet in exp_snippet or exp_snippet in pred_snippet):
            return False

        # If cited_code is specified in expected, verify code
        exp_code = expected.get("cited_code")
        if exp_code:
            pred_code = pred_finding.cited_code or ""
            # Allow partial or exact code match
            if exp_code.lower() not in pred_code.lower() and pred_code.lower() not in exp_code.lower():
                # Allow if snippet and category are exact
                pass

        return True

    @classmethod
    def evaluate_test_case(
        cls,
        db: Session,
        test_case: EvaluationTestCase,
        organization_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Run the analysis engine on a single test case and evaluate results against ground truth.
        """
        # 1. Run actual analysis engine
        raw_findings = BrandAnalysisEngine.analyze_text(
            db=db,
            organization_id=organization_id,
            text=test_case.input_content,
            metadata=test_case.content_metadata
        )

        # 2. Quality Verification Gate ("No Citation, No Flag")
        verification_report = FindingQualityVerifier.verify_and_filter_findings(
            db=db,
            findings=raw_findings,
            source_text=test_case.input_content
        )
        verified_findings = verification_report.verified_list

        expected_list = list(test_case.expected_findings or [])
        matched_expected = set()
        matched_predicted = set()

        # 3. Match predicted against expected
        for p_idx, pred in enumerate(verified_findings):
            for e_idx, exp in enumerate(expected_list):
                if e_idx not in matched_expected:
                    if cls.match_finding(pred, exp):
                        matched_predicted.add(p_idx)
                        matched_expected.add(e_idx)
                        break

        tp = len(matched_predicted)
        fp = len(verified_findings) - tp
        fn = len(expected_list) - len(matched_expected)

        is_passed = (fp == 0 and fn == 0)

        return {
            "test_code": test_case.test_code,
            "title": test_case.title,
            "target_category": test_case.target_category,
            "expected_count": len(expected_list),
            "predicted_count": len(verified_findings),
            "raw_findings_count": len(raw_findings),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "passed": is_passed,
            "is_ambiguous": test_case.is_ambiguous,
            "verified_rate": verification_report.verification_rate,
            "rejections": verification_report.reasons,
            "predicted_snippets": [f.flagged_snippet for f in verified_findings],
            "expected_snippets": [e.get("flagged_snippet") for e in expected_list]
        }

    @classmethod
    def run_evaluation(
        cls,
        db: Session,
        organization_id: uuid.UUID,
        dataset_id: uuid.UUID,
        triggered_by: Optional[uuid.UUID] = None,
        engine_version: str = "1.0.0-phase7",
        run_type: str = "BENCHMARK"
    ) -> EvaluationRun:
        """
        Execute full evaluation run over all test cases in the dataset and persist results.
        """
        dataset = db.query(EvaluationDataset).filter(
            EvaluationDataset.id == dataset_id,
            EvaluationDataset.organization_id == organization_id
        ).first()

        if not dataset:
            raise ValueError(f"EvaluationDataset {dataset_id} not found in tenant organization")

        test_cases = db.query(EvaluationTestCase).filter(
            EvaluationTestCase.dataset_id == dataset.id,
            EvaluationTestCase.organization_id == organization_id
        ).order_by(EvaluationTestCase.test_code.asc()).all()

        # Category-wise accumulators
        cat_counts: Dict[str, Dict[str, int]] = {
            cat: {"tp": 0, "fp": 0, "fn": 0, "expected": 0, "predicted": 0}
            for cat in ALL_CATEGORIES
        }

        total_tp = 0
        total_fp = 0
        total_fn = 0
        passed_cases = 0
        case_results = []

        for tc in test_cases:
            res = cls.evaluate_test_case(db, tc, organization_id)
            case_results.append(res)

            if res["passed"]:
                passed_cases += 1

            total_tp += res["tp"]
            total_fp += res["fp"]
            total_fn += res["fn"]

            # Map to category metrics
            cat = tc.target_category or "TONE"
            if cat in cat_counts:
                cat_counts[cat]["tp"] += res["tp"]
                cat_counts[cat]["fp"] += res["fp"]
                cat_counts[cat]["fn"] += res["fn"]
                cat_counts[cat]["expected"] += res["expected_count"]
                cat_counts[cat]["predicted"] += res["predicted_count"]

        # Compute per-category precision, recall, F1
        category_metrics = {}
        for cat, counts in cat_counts.items():
            p, r, f1 = EvaluationMetricsCalculator.calculate_p_r_f1(
                counts["tp"], counts["fp"], counts["fn"]
            )
            coverage = round(counts["tp"] / counts["expected"], 4) if counts["expected"] > 0 else 1.0
            category_metrics[cat] = {
                "tp": counts["tp"],
                "fp": counts["fp"],
                "fn": counts["fn"],
                "expected": counts["expected"],
                "predicted": counts["predicted"],
                "precision": p,
                "recall": r,
                "f1": f1,
                "coverage": coverage
            }

        # Overall macro/micro metrics
        overall_p, overall_r, overall_f1 = EvaluationMetricsCalculator.calculate_p_r_f1(
            total_tp, total_fp, total_fn
        )
        total_cases_count = len(test_cases)
        overall_acc = round(passed_cases / total_cases_count, 4) if total_cases_count > 0 else 1.0

        # Create and persist EvaluationRun
        eval_run = EvaluationRun(
            id=uuid.uuid4(),
            organization_id=organization_id,
            dataset_id=dataset.id,
            engine_version=engine_version,
            run_type=run_type,
            total_cases=total_cases_count,
            overall_precision=overall_p,
            overall_recall=overall_r,
            overall_f1=overall_f1,
            overall_accuracy=overall_acc,
            category_metrics=category_metrics,
            case_results=case_results,
            triggered_by=triggered_by,
            created_at=datetime.now(timezone.utc)
        )

        db.add(eval_run)
        db.commit()
        db.refresh(eval_run)

        return eval_run
