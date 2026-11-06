"""
app/services/workflow/version_diff.py
Document Version Comparison Engine (Phase 6).
Computes structured text differences and finding status differentials
between two versions of the same document.
"""
import difflib
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.models.document import DocumentVersion
from app.models.finding import Finding, FindingStatus


class VersionDiffEngine:
    """Computes textual and compliance finding diffs between two versions."""

    @staticmethod
    def compare_versions(
        db: Session,
        version_1: DocumentVersion,
        version_2: DocumentVersion
    ) -> Dict[str, Any]:
        """
        Compare base version (version_1) against revised version (version_2).

        Returns:
            - text_diff: line-by-line unified diff and semantic summary
            - added_lines_count: int
            - removed_lines_count: int
            - score_delta: brand_health_score difference (v2 - v1)
            - new_findings: findings present in v2 but not v1
            - resolved_findings: findings in v1 that no longer trigger in v2
            - persistent_findings: findings remaining in both v1 and v2
        """
        text1 = version_1.extracted_text or version_1.raw_content or ""
        text2 = version_2.extracted_text or version_2.raw_content or ""

        lines1 = text1.splitlines()
        lines2 = text2.splitlines()

        differ = difflib.Differ()
        diff = list(differ.compare(lines1, lines2))

        added_lines = [l[2:] for l in diff if l.startswith("+ ")]
        removed_lines = [l[2:] for l in diff if l.startswith("- ")]
        unchanged_lines = [l[2:] for l in diff if l.startswith("  ")]

        # Health score delta
        score1 = float(version_1.brand_health_score or 0.0)
        score2 = float(version_2.brand_health_score or 0.0)
        score_delta = round(score2 - score1, 2)

        # Finding differentials
        f1_list = db.query(Finding).filter(
            Finding.version_id == version_1.id,
            Finding.organization_id == version_1.organization_id
        ).all()
        f2_list = db.query(Finding).filter(
            Finding.version_id == version_2.id,
            Finding.organization_id == version_2.organization_id
        ).all()

        f1_keys = {
            (f.category.value, f.flagged_snippet.strip().lower(), f.cited_code): f
            for f in f1_list
        }
        f2_keys = {
            (f.category.value, f.flagged_snippet.strip().lower(), f.cited_code): f
            for f in f2_list
        }

        persistent_keys = set(f1_keys.keys()) & set(f2_keys.keys())
        resolved_keys = set(f1_keys.keys()) - set(f2_keys.keys())
        new_keys = set(f2_keys.keys()) - set(f1_keys.keys())

        return {
            "v1_id": str(version_1.id),
            "v1_version_number": version_1.version_number,
            "v1_score": score1,
            "v2_id": str(version_2.id),
            "v2_version_number": version_2.version_number,
            "v2_score": score2,
            "score_delta": score_delta,
            "text_summary": {
                "added_lines_count": len(added_lines),
                "removed_lines_count": len(removed_lines),
                "total_lines_v1": len(lines1),
                "total_lines_v2": len(lines2),
            },
            "diff_lines": diff[:100],  # sample first 100 diff lines for display
            "findings_summary": {
                "v1_total": len(f1_list),
                "v2_total": len(f2_list),
                "resolved_count": len(resolved_keys),
                "new_count": len(new_keys),
                "persistent_count": len(persistent_keys),
            },
            "resolved_findings": [
                {
                    "category": k[0],
                    "snippet": f1_keys[k].flagged_snippet,
                    "cited_code": f1_keys[k].cited_code,
                    "severity": f1_keys[k].severity.value,
                }
                for k in resolved_keys
            ],
            "new_findings": [
                {
                    "category": k[0],
                    "snippet": f2_keys[k].flagged_snippet,
                    "cited_code": f2_keys[k].cited_code,
                    "severity": f2_keys[k].severity.value,
                }
                for k in new_keys
            ],
            "persistent_findings": [
                {
                    "category": k[0],
                    "snippet": f2_keys[k].flagged_snippet,
                    "cited_code": f2_keys[k].cited_code,
                    "severity": f2_keys[k].severity.value,
                }
                for k in persistent_keys
            ]
        }

