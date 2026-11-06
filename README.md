# BrandGuard

> **AI-Native Multi-Tenant Brand Governance & Verification Engine**  
> Current Branch: `feature/phase-7-evaluation-intelligence`  
> Checkpoints:
> - Stable Backup: `backup/phase2-phase3-stable` (`f76c436`)
> - Phase 4 Checkpoint: `c76d11a`
> - Phase 5 Completion: `c7fadbb`
> - Phase 6 Completion: `f545825` (Human Review, Approval & Governance Workflow)
> - Phase 7 Completion: Evaluation, Reliability & Intelligence (121 backend tests passing, 0 errors, 14 Next.js routes)

---

## Overview

BrandGuard is a deterministic, multi-tenant brand governance platform designed to enforce brand guidelines, verify factual marketing claims, govern terminology, and manage brand assets across enterprise organizations.

This repository contains the complete, tested, and operational implementation of:
- **Phase 1: Project Foundation** — Multi-tenant database architecture (PostgreSQL 18 with pgvector), composite foreign key referential integrity, FastAPI backend, and Next.js frontend foundation.
- **Phase 2: Authentication & RBAC** — Multi-tenant organization bootstrap, secure registration, password hashing (bcrypt), JWT with cryptographic `jti` and revocation tracking, 7 distinct enterprise roles, double-submit cookie CSRF protection, sliding-window rate limiting, and strictly append-only audit logging.
- **Phase 3: Brand Constitution Builder** — Full-stack Brand Rules engine with human approval gate, Fact Registry with conflict detection and automated expiration tracking, Term Bank with prohibited/preferred terms and case-sensitivity, Brand Asset Library with color swatches and file upload validation.
- **Phase 4: Content Ingestion & Document Extraction** — High-performance ingestion for TXT, DOCX, multi-page PDF, and raster images (PNG, JPG), structured segmentation (paragraphs, headings, metadata), and graceful OCR fallback.
- **Phase 5: Brand Analysis Engine** — Multi-category compliance engine across Terminology, Claims & Facts, Tone & Voice, Messaging Alignment, Visual Consistency (Pillow pixel analysis), and WCAG 2.1 Accessibility. Includes finding verification gate, duplicate suppression, and local Ollama support.
- **Phase 6: Human Review, Approval & Governance Workflow** — Centralized review state machine with self-approval prevention and legal gating, finding-level decision tracking (accept/dismiss/dispute/resolve), threaded collaboration with hierarchical replies, automated version diff engine (line-by-line diff, score delta, resolved violations), immutable document version locking upon approval, and in-app notifications.
- **Phase 7: Evaluation, Reliability & Intelligence** — Precision and Recall benchmarking across all 6 compliance categories, "No Citation, No Flag" finding verification gate, linguistic guideline ambiguity scoring, review friction analysis, conflicting rule detection, human-in-the-loop recommendations, and dedicated Evaluation Dashboard UI.

---

## Project Structure

```
BrandGuard/
├── backend/
│   ├── alembic/
│   │   ├── versions/
│   │   │   ├── 0001_initial_schema.py      # Core multi-tenant tables & composite keys
│   │   │   ├── 0002_add_revoked_tokens.py  # JWT token revocation tracking
│   │   │   └── 0003_draft_expired_status.py# DRAFT & EXPIRED entity status enum values
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── audit.py                    # Audit log query endpoints
│   │   │   ├── auth.py                     # Bootstrap, login, register, logout, CSRF
│   │   │   ├── constitution.py             # Rules, facts, terms, assets, conflict detection
│   │   │   ├── health.py                   # System health, DB, pgvector, AI status
│   │   │   └── users.py                    # User management & role administration
│   │   ├── audit/
│   │   │   └── audit_logger.py             # Append-only audit logger
│   │   ├── auth/
│   │   │   ├── csrf.py                     # Double-submit cookie CSRF protection
│   │   │   ├── dependencies.py             # Auth dependencies & token verification
│   │   │   ├── jwt.py                      # JWT encode/decode with jti & revocation check
│   │   │   ├── password.py                 # Bcrypt password hashing
│   │   │   ├── rate_limiter.py             # Sliding-window rate limiter
│   │   │   └── rbac.py                     # 7-role permissions matrix
│   │   ├── models/                         # SQLAlchemy composite-key data models
│   │   ├── schemas/                        # Pydantic validation schemas
│   │   ├── config.py                       # Pydantic BaseSettings & env configuration
│   │   ├── database.py                     # SessionLocal & DB engine
│   │   └── main.py                         # FastAPI app entry point
│   ├── tests/
│   │   ├── conftest.py                     # DB fixtures & test client
│   │   ├── test_auth.py                    # 22 auth, RBAC, CSRF, & rate-limit tests
│   │   ├── test_constitution.py            # 9 Constitution CRUD & conflict tests
│   │   ├── test_db_integrity.py            # Referential integrity test
│   │   └── test_health.py                  # Health check & root endpoints
│   ├── .env.example                        # Backend environment variable template
│   ├── alembic.ini                         # Alembic database migration config
│   └── requirements.txt                    # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── constitution/
│   │   │   │   ├── assets/page.tsx         # Brand Asset Library (colors, logos, upload)
│   │   │   │   ├── facts/page.tsx          # Fact Registry (claims, expiration, conflict dialog)
│   │   │   │   ├── rules/page.tsx          # Brand Rules (categories, workflow, review)
│   │   │   │   ├── terms/page.tsx          # Term Bank (prohibited/preferred pairs)
│   │   │   │   └── page.tsx                # Constitution Hub overview & demo seed
│   │   │   ├── login/page.tsx              # Multi-tenant Sign In / Register / Bootstrap
│   │   │   ├── layout.tsx                  # Root layout
│   │   │   └── page.tsx                    # Main system dashboard
│   │   ├── components/
│   │   │   ├── auth/ProtectedRoute.tsx     # Client-side permission guard
│   │   │   └── layout/                     # Navbar and Sidebar navigation
│   │   └── lib/
│   │       ├── api.ts                      # Axios client with CSRF & Bearer interceptors
│   │       └── auth.tsx                    # Auth context & permission helper
│   ├── .env.example                        # Frontend environment variable template
│   ├── package.json
│   ├── tailwind.config.js
│   └── tsconfig.json
├── docs/
│   └── PHASE_2_PHASE_3_REPORT.md           # Full Phase 2 & 3 verification report
├── .gitignore                              # Comprehensive sensitive & runtime file exclusions
└── README.md                               # Project documentation & recovery instructions
```

---

## Environment Variables

### Backend (`backend/.env`)
Copy `backend/.env.example` to `backend/.env`:
```bash
cp backend/.env.example backend/.env
```

| Variable | Description | Example / Default |
|---|---|---|
| `ENVIRONMENT` | Environment mode (`development` / `production`) | `development` |
| `DEBUG` | Enable debug mode | `True` |
| `API_V1_STR` | API prefix | `/api/v1` |
| `PROJECT_NAME` | Project name | `"BrandGuard API"` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://brandguard_user:password@localhost:5435/brandguard` |
| `DB_POOL_SIZE` | SQLAlchemy connection pool size | `10` |
| `DB_MAX_OVERFLOW` | Maximum pool overflow | `20` |
| `SECRET_KEY` | JWT signing secret key (min 32 bytes) | *(secure random secret)* |
| `ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL in minutes | `480` |
| `BACKEND_CORS_ORIGINS` | Allowed CORS origins | `["http://localhost:3000","http://127.0.0.1:3000"]` |
| `OLLAMA_BASE_URL` | Optional local Ollama endpoint | `http://localhost:11434` |
| `GEMINI_API_KEY` | Optional Google Gemini API key | *(optional)* |

### Frontend (`frontend/.env.local`)
Copy `frontend/.env.example` to `frontend/.env.local`:
```bash
cp frontend/.env.example frontend/.env.local
```

| Variable | Description | Example / Default |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Base URL for FastAPI backend v1 API | `http://localhost:8000/api/v1` |

---

## Database Setup & Migrations

BrandGuard requires PostgreSQL with the `pgvector` extension. In development, it runs on port `5435`:

1. **Verify Database Service**:
   Ensure PostgreSQL is running and accepting connections on port `5435`.
   ```bash
   psql -p 5435 -U brandguard_user -d brandguard -c "SELECT version();"
   ```

2. **Run Migrations**:
   From the `backend/` directory:
   ```bash
   cd backend
   python -m alembic upgrade head
   ```

3. **Migration History**:
   - `0001_initial_schema`: Core multi-tenant tables with composite keys and strict organization scoping.
   - `0002_add_revoked_tokens`: Token revocation blacklist table for secure logout.
   - `0003_draft_expired_status`: Added `DRAFT` and `EXPIRED` values to the `entity_status` enum.

---

## Running the Application

### 1. Backend Service (FastAPI)
```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
- API Docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/v1/health`

### 2. Frontend Application (Next.js)
```bash
cd frontend
npm install
npm run build
npm run start -- -p 3000
```
- Application UI: `http://localhost:3000`
- Login & Bootstrap: `http://localhost:3000/login`
- Constitution Hub: `http://localhost:3000/constitution`

---

## Test Execution

### Backend Test Suite (pytest)
From `backend/`:
```bash
cd backend
python -m pytest tests/ -v
```
Expected output: **34 passed** (22 auth/RBAC tests, 9 Constitution tests, 1 DB integrity test, 2 health check tests).

### Frontend Production Build
From `frontend/`:
```bash
cd frontend
npm run build
```
Expected output: **0 TypeScript errors, 8/8 routes compiled successfully**.

---

## Security Architecture (Phase 2)

1. **CSRF Protection**: Double-submit cookie pattern. Cookie-authenticated requests require a matching `X-CSRF-Token` header. Bearer token requests remain exempt.
2. **Rate Limiting**: Sliding-window rate limiter protecting login (`5 failed / 5 min`), IP rate limit (`30 / 5 min`), and organization bootstrap (`20 / 10 min`).
3. **Role-Based Access Control (RBAC)**: 7 enterprise roles with fine-grained permissions:
   - `ADMIN` — Tenant administrator; user role assignment, full governance.
   - `BRAND_MANAGER` — Brand Constitution manager; approves/rejects rules & facts.
   - `CONTENT_CREATOR` — Authors draft rules, facts, and content.
   - `EXTERNAL_AGENCY` — Scoped external agency access.
   - `REVIEWER` — Content reviewer.
   - `LEGAL_REVIEWER` — Regulatory and legal compliance review.
   - `LEADERSHIP` — Read-only executive visibility and reporting.
4. **Token Revocation**: Logout blacklists the JWT `jti` in the database, preventing token reuse.
5. **Cookie Security**: `Secure` cookie flag dynamically toggled by environment (`True` in production, `False` in development).
6. **Append-Only Audit Logs**: Database-enforced immutable audit logs for security and compliance events.

---

## How to Restore This Checkpoint

To restore or clone this exact verified Phase 2 & Phase 3 state:

```bash
# Clone the repository
git clone https://github.com/sejalgite/BrandGuard.git
cd BrandGuard

# Checkout the stable backup branch
git checkout backup/phase2-phase3-stable

# Configure backend environment
cd backend
cp .env.example .env
pip install -r requirements.txt
python -m alembic upgrade head
python -m pytest tests/ -v

# Configure frontend environment
cd ../frontend
cp .env.example .env.local
npm install
npm run build
```
