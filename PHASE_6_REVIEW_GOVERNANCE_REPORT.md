# BrandGuard — Phase 6: Human Review, Approval & Governance Workflow Report

## Executive Summary

Phase 6 implements an enterprise-grade Human Review, Approval, Collaboration, and Governance Workflow on top of the completed Phase 1–5 BrandGuard platform. The system introduces a formal review queue, multi-role state machine governance, itemized finding decisions (Accept, Dismiss with mandatory justification, Dispute, Resolve), threaded discussions with hierarchical replies, automated document version diffing with score delta tracking, in-app notification dispatching, and cryptographic document locking upon final Brand Manager approval.

---

## 1. Database & Schema Architecture

### Migration: `0006_review_governance.py`
The schema extends the multi-tenant architecture while strictly maintaining composite foreign key isolation `(organization_id, ...)`.

- **Enums Created:**
  - `review_workflow_status`: `DRAFT`, `SUBMITTED`, `UNDER_REVIEW`, `CHANGES_REQUESTED`, `RESUBMITTED`, `PENDING_BRAND_APPROVAL`, `PENDING_LEGAL_APPROVAL`, `APPROVED`, `REJECTED`, `WITHDRAWN`
  - `finding_decision_type`: `ACCEPTED`, `DISMISSED`, `DISPUTED`, `RESOLVED`, `CORRECTION_REQUESTED`

- **Tables Created / Extended:**
  1. `reviews`: Core workflow lifecycle entity linking documents, versions, creators, assigned reviewers, legal reviewers, and final sign-off metadata.
  2. `review_history`: Append-only transition audit trail recording every workflow event, actor, from/to status, and explanation notes.
  3. `finding_decisions`: Persistent reviewer decisions per individual finding, including mandatory reasons for dismissals/disputes and suggested corrections.
  4. `notifications`: In-app notification queue with read-state tracking and duplicate alert suppression.
  5. `comments`: Extended with foreign key `review_id` to link threaded collaboration comments directly to reviews.

---

## 2. Centralized Workflow State Machine

The workflow state machine in `backend/app/services/workflow/state_machine.py` acts as the single source of truth for all lifecycle transitions:

### State Transitions Matrix:
- `DRAFT` → `SUBMITTED`, `WITHDRAWN`
- `SUBMITTED` → `UNDER_REVIEW`, `REJECTED`, `WITHDRAWN`
- `UNDER_REVIEW` → `CHANGES_REQUESTED`, `FORWARD_FOR_APPROVAL`, `REQUEST_LEGAL`, `APPROVE`, `REJECT`
- `CHANGES_REQUESTED` → `RESUBMITTED`, `WITHDRAWN`
- `RESUBMITTED` → `UNDER_REVIEW`, `CHANGES_REQUESTED`, `FORWARD_FOR_APPROVAL`, `REQUEST_LEGAL`, `APPROVE`, `REJECT`
- `PENDING_LEGAL_APPROVAL` → `APPROVE_LEGAL` (moves to `PENDING_BRAND_APPROVAL`), `REQUEST_CHANGES`, `REJECT`
- `PENDING_BRAND_APPROVAL` → `APPROVE`, `REQUEST_CHANGES`, `REQUEST_LEGAL`, `REJECT`

### Security Guardrails:
1. **Self-Approval Prevention:** Creators cannot approve their own submitted content under any circumstances unless operating as an Administrator.
2. **Mandatory Notes:** Transitioning to `REQUEST_CHANGES` or `REJECT` strictly requires non-empty explanatory notes (HTTP 422).
3. **Legal Gating:** If `legal_review_required=True`, final approval is blocked (HTTP 400) until the Legal Reviewer grants legal clearance (`APPROVE_LEGAL`).
4. **Document Version Locking:** Final approval sets `DocumentVersion.is_locked = True`, `version_status = APPROVED`, and `Document.lifecycle_status = APPROVED`. Locked versions are permanently immutable.

---

## 3. Document Version Comparison Engine

`backend/app/services/workflow/version_diff.py` computes automated diff metrics between any two document versions:
- Unified line-by-line textual diff with semantic line tags (`+`, `-`, ` `).
- Health score delta: `v2_score - v1_score`.
- Compliance finding status differential:
  - **Resolved findings:** Flagged in v1 but resolved in v2.
  - **New findings:** Introduced in v2.
  - **Persistent findings:** Violations present across both versions.

---

## 4. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/reviews` | Submit document version for review |
| `GET` | `/api/v1/reviews` | List organization reviews with status/assignee filters |
| `GET` | `/api/v1/reviews/queue/stats` | Queue statistics KPI aggregation |
| `GET` | `/api/v1/reviews/{id}` | Complete review detail with history & decisions |
| `POST` | `/api/v1/reviews/{id}/transition` | Execute state transition via state machine |
| `PATCH` | `/api/v1/reviews/{id}/assign` | Assign/reassign peer and legal reviewers |
| `POST` | `/api/v1/reviews/{id}/findings/{fid}/decision` | Record decision on finding (Accept/Dismiss/Dispute/Resolve) |
| `GET` | `/api/v1/reviews/{id}/comments` | Fetch threaded comments and nested replies |
| `POST` | `/api/v1/reviews/{id}/comments` | Post review comment or threaded reply |
| `GET` | `/api/v1/reviews/documents/{doc_id}/compare` | Compare two document versions (diff & score delta) |
| `GET` | `/api/v1/notifications` | Fetch current user notifications |
| `PATCH` | `/api/v1/notifications/{id}/read` | Mark individual notification as read |
| `POST` | `/api/v1/notifications/read-all` | Mark all user notifications as read |

---

## 5. Frontend User Experience

- **Review Queue (`/reviews`):**
  - KPI summary metric cards (Total, Submitted, In Review, Changes Requested, Pending Sign-off, Approved, My Queue).
  - Filterable by status tabs, text search, and "Assigned to Me".
  - "Submit Document for Review" modal with document selector, priority selector, due date, and submission context.
- **Review Workspace (`/reviews/[id]`):**
  - Document header with version pill, status badge, priority, and health score.
  - Contextual Role-Aware Action Bar:
    - Reviewers: "Start Review", "Request Changes", "Forward for Brand Approval", "Request Legal Review".
    - Brand Managers: "Approve & Lock Version", "Reject".
    - Legal Reviewers: "Approve Legal Sign-off", "Reject Legal".
    - Creators: "Resubmit Revised Version" (with version selector).
  - 4 Dynamic Workspaces:
    1. *Findings & Decisions:* Decision recording modal requiring mandatory justifications for dismissals.
    2. *Version Diff & Delta:* Line-by-line diff, score delta, and resolved findings summary.
    3. *Collaboration & Notes:* Hierarchical threaded commenting with user role badges.
    4. *Audit Timeline:* Chronological history of every transition, actor, and note.

---

## 6. Verification Results

### Backend Automated Test Suite
- **Phase 6 Review Suite:** 11 passed in 7.97s (`tests/test_reviews.py`)
- **Full Backend Suite:** 112 passed across all modules in 41.48s:
  - `tests/test_analysis.py`: 5 passed
  - `tests/test_analysis_quality.py`: 48 passed
  - `tests/test_auth.py`: 20 passed
  - `tests/test_constitution.py`: 9 passed
  - `tests/test_db_integrity.py`: 1 passed
  - `tests/test_documents.py`: 12 passed
  - `tests/test_health.py`: 2 passed
  - `tests/test_reviews.py`: 11 passed
  - **Pass Rate:** 100% (112 passed, 0 failed, 0 skipped)

### Frontend Production Build
- Command: `npm run build`
- All 13 Next.js routes generated successfully with 0 errors.

### ApexCloud End-to-End Demo Script
- Command: `python scripts/demo_phase6_review_workflow.py`
- Executed against PostgreSQL database. Verified complete lifecycle from initial ingestion through peer review, changes requested, v2 resubmission, version diff (+45 pts), and final brand sign-off locking version 2.
