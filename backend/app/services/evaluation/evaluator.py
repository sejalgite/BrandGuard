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
    """
    Computes finding-level precision, recall, F1-score, macro/micro averages,
    document-level classification accuracy (with True Negatives), and test-case pass rates
    with robust zero-division handling.
    """

    @staticmethod
    def calculate_p_r_f1(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
        """
        Calculate precision, recall, and F1.
        Handles zero-division gracefully without NaN or runtime exceptions:
        - If (tp + fp) == 0: precision is 1.0 if fn == 0 (no violations expected or predicted) else 0.0
        - If (tp + fn) == 0: recall is 1.0 if fp == 0 else 0.0
        - If (precision + recall) == 0: F1 is 0.0
        """
        if (tp + fp) > 0:
            precision = tp / (tp + fp)
        else:
            precision = 1.0 if fn == 0 else 0.0

        if (tp + fn) > 0:
            recall = tp / (tp + fn)
        else:
            recall = 1.0 if fp == 0 else 0.0

        if (precision + recall) > 0:
            f1 = (2 * precision * recall) / (precision + recall)
        else:
            f1 = 0.0

        return round(precision, 4), round(recall, 4), round(f1, 4)

    @staticmethod
    def calculate_document_accuracy(tp_doc: int, tn_doc: int, fp_doc: int, fn_doc: int) -> float:
        """
        Calculates document-level classification accuracy:
        Accuracy = (TP_doc + TN_doc) / (TP_doc + TN_doc + FP_doc + FN_doc)
        Explicitly accounts for True Negatives (clean documents with 0 findings).
        """
        total = tp_doc + tn_doc + fp_doc + fn_doc
        if total == 0:
            return 1.0
        return round((tp_doc + tn_doc) / total, 4)

    @staticmethod
    def calculate_test_case_pass_rate(passed_cases: int, total_cases: int) -> float:
        """
        Calculates the fraction of test cases where all expected findings were found
        with zero false positives (FP == 0 and FN == 0).
        """
        if total_cases == 0:
            return 1.0
        return round(passed_cases / total_cases, 4)

    @staticmethod
    def calculate_macro_averages(category_metrics: Dict[str, Dict[str, Any]]) -> Tuple[float, float, float]:
        """
        Calculates unweighted macro-averaged precision, recall, and F1 across evaluated categories.
        Categories with expected > 0 or predicted > 0 are considered evaluated.
        If no categories were evaluated, returns (1.0, 1.0, 1.0).
        """
        precisions = []
        recalls = []
        f1s = []

        for cat, m in category_metrics.items():
            if cat.startswith("_"):
                continue
            if m.get("expected", 0) > 0 or m.get("predicted", 0) > 0:
                precisions.append(m.get("precision", 0.0))
                recalls.append(m.get("recall", 0.0))
                f1s.append(m.get("f1", 0.0))

        if not precisions:
            return 1.0, 1.0, 1.0

        macro_p = sum(precisions) / len(precisions)
        macro_r = sum(recalls) / len(recalls)
        macro_f1 = sum(f1s) / len(f1s)

        return round(macro_p, 4), round(macro_r, 4), round(macro_f1, 4)


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
                if pred_snippet != exp_snippet:
                    return False

        return True

    @classmethod
    def evaluate_test_case(
        cls,
        db: Session,
        test_case: EvaluationTestCase,
        organization_id: uuid.UUID
    ) -> Tuple[Dict[str, Any], List[Tuple[Any, Dict[str, Any]]], List[Any], List[Dict[str, Any]]]:
        """
        Run the analysis engine on a single test case and evaluate results against ground truth.
        Returns:
            (serializable_result, matched_pairs, unmatched_predicted, unmatched_expected)
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
        matched_pairs: List[Tuple[Any, Dict[str, Any]]] = []

        # 3. Match predicted against expected (greedy 1-to-1 matching)
        for p_idx, pred in enumerate(verified_findings):
            for e_idx, exp in enumerate(expected_list):
                if e_idx not in matched_expected:
                    if cls.match_finding(pred, exp):
                        matched_predicted.add(p_idx)
                        matched_expected.add(e_idx)
                        matched_pairs.append((pred, exp))
                        break

        unmatched_predicted = [
            pred for p_idx, pred in enumerate(verified_findings)
            if p_idx not in matched_predicted
        ]
        unmatched_expected = [
            exp for e_idx, exp in enumerate(expected_list)
            if e_idx not in matched_expected
        ]

        tp = len(matched_predicted)
        fp = len(unmatched_predicted)
        fn = len(unmatched_expected)

        is_passed = (fp == 0 and fn == 0)

        result_dict = {
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

        return result_dict, matched_pairs, unmatched_predicted, unmatched_expected

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

        doc_tp = 0
        doc_tn = 0
        doc_fp = 0
        doc_fn = 0

        for tc in test_cases:
            res, matched_pairs, unmatched_pred, unmatched_exp = cls.evaluate_test_case(db, tc, organization_id)
            case_results.append(res)

            if res["passed"]:
                passed_cases += 1

            total_tp += res["tp"]
            total_fp += res["fp"]
            total_fn += res["fn"]

            # Document-level classification (True Negatives, True Positives, etc.)
            is_clean = tc.expected_compliant or (res["expected_count"] == 0)
            has_predicted = res["predicted_count"] > 0
            if not is_clean and has_predicted:
                doc_tp += 1
            elif is_clean and not has_predicted:
                doc_tn += 1
            elif is_clean and has_predicted:
                doc_fp += 1
            elif not is_clean and not has_predicted:
                doc_fn += 1

            # Category-wise metrics: attribute each finding to its ACTUAL category!
            for pred, exp in matched_pairs:
                cat = pred.category.value if hasattr(pred.category, "value") else str(pred.category)
                if cat in cat_counts:
                    cat_counts[cat]["tp"] += 1
                    cat_counts[cat]["expected"] += 1
                    cat_counts[cat]["predicted"] += 1

            for pred in unmatched_pred:
                cat = pred.category.value if hasattr(pred.category, "value") else str(pred.category)
                if cat in cat_counts:
                    cat_counts[cat]["fp"] += 1
                    cat_counts[cat]["predicted"] += 1

            for exp in unmatched_exp:
                cat = exp.get("category", "")
                if cat in cat_counts:
                    cat_counts[cat]["fn"] += 1
                    cat_counts[cat]["expected"] += 1

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

        # Overall Finding-level Micro metrics
        micro_p, micro_r, micro_f1 = EvaluationMetricsCalculator.calculate_p_r_f1(
            total_tp, total_fp, total_fn
        )

        # Macro averages across evaluated categories
        macro_p, macro_r, macro_f1 = EvaluationMetricsCalculator.calculate_macro_averages(category_metrics)

        # Test-case pass rate (fraction of cases with 0 FP and 0 FN)
        total_cases_count = len(test_cases)
        pass_rate = EvaluationMetricsCalculator.calculate_test_case_pass_rate(
            passed_cases, total_cases_count
        )

        # Document-level classification accuracy (explicitly accounting for True Negatives)
        doc_accuracy = EvaluationMetricsCalculator.calculate_document_accuracy(
            doc_tp, doc_tn, doc_fp, doc_fn
        )

        # Summary metadata embedded inside category_metrics for transparent reporting
        category_metrics["_summary"] = {
            "total_tp": total_tp,
            "total_fp": total_fp,
            "total_fn": total_fn,
            "micro_precision": micro_p,
            "micro_recall": micro_r,
            "micro_f1": micro_f1,
            "macro_precision": macro_p,
            "macro_recall": macro_r,
            "macro_f1": macro_f1,
            "test_case_pass_rate": pass_rate,
            "passed_cases": passed_cases,
            "total_cases": total_cases_count,
            "document_accuracy": doc_accuracy,
            "doc_tp": doc_tp,
            "doc_tn": doc_tn,
            "doc_fp": doc_fp,
            "doc_fn": doc_fn,
        }

        # Persist EvaluationRun
        eval_run = EvaluationRun(
            id=uuid.uuid4(),
            organization_id=organization_id,
            dataset_id=dataset.id,
            engine_version=engine_version,
            run_type=run_type,
            total_cases=total_cases_count,
            overall_precision=micro_p,
            overall_recall=micro_r,
            overall_f1=micro_f1,
            overall_accuracy=doc_accuracy,  # Document-level classification accuracy
            category_metrics=category_metrics,
            case_results=case_results,
            triggered_by=triggered_by,
            created_at=datetime.now(timezone.utc)
        )

        db.add(eval_run)
        db.commit()
        db.refresh(eval_run)

        return eval_run

