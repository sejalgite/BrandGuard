# BrandGuard — Phase 5: Brand Analysis Engine Documentation & Quality Report

> **Branch:** `feature/phase-5-brand-analysis`  
> **Base Commit:** `c76d11adb180990e5eae39ea6de0540166eaf6cd` (Phase 4 complete)  
> **Status:** Completed, Audited & Verified  

---

## 1. Overview & Architecture

Phase 5 introduces the **Brand Analysis Engine**, an enterprise-grade compliance and verification pipeline that audits unstructured marketing and technical content against an organization's active **Brand Constitution**.

```
                           +----------------------------------------+
                           |       Document Ingestion & Extraction  |
                           |   (TXT, DOCX, PDF, PNG/JPG, OCR-ready) |
                           +-------------------+--------------------+
                                               |
                                               v
                           +----------------------------------------+
                           |      Structured Content & Segments     |
                           |  (paragraph offsets, headings, images) |
                           +-------------------+--------------------+
                                               |
                                               v
                    +------------------------------------------------------+
                    |          Brand Analysis Engine Orchestrator          |
                    |     (Active Brand Constitution Ground Truth)         |
                    +--------------------------+---------------------------+
                                               |
         +-----------------+-------------------+-----------------+-----------------+
         |                 |                   |                 |                 |
         v                 v                   v                 v                 v
  +--------------+  +--------------+    +--------------+  +--------------+  +--------------+
  | Terminology  |  | Claims/Facts |    | Tone & Voice |  |  Messaging   |  |    Visual    |
  |   Analyzer   |  |   Analyzer   |    |   Analyzer   |  |   Analyzer   |  |   Analyzer   |
  +--------------+  +--------------+    +--------------+  +--------------+  +--------------+
         |                 |                   |                 |                 |
         |                 |                   +--------+--------+                 |
         |                 |                            |                          |
         |                 |                   Optional Local Ollama               |
         |                 |                 (Offline Deterministic)               |
         |                 |                            |                          |
         +-----------------+-------------------+--------+--------------------------+
                                               |
                                               v
                               +-------------------------------+
                               |  Cross-Category Deduplication |
                               +---------------+---------------+
                                               |
                                               v
                               +-------------------------------+
                               |   Finding Verification Gate   |
                               | (snippet match, bounds check) |
                               +---------------+---------------+
                                               |
                                               v
                               +-------------------------------+
                               | Database Persistence & Scoring|
                               |  Brand Health Score (0-100)   |
                               |     Audit Trail Recording     |
                               +-------------------------------+
```

---

## 2. Six Analysis Categories

### 1. Terminology Analyzer (`terminology_analyzer.py`)
- **Objective:** Scan structured segments for prohibited brand terminology and recommend approved alternatives.
- **Mechanism:** Exact whole-word regex boundaries (`\b... \b`) matching against active entries in the `TermBank`.
- **False-Positive Prevention:** Does not flag partial substring matches (e.g., `"cheap"` inside `"cheapest"` is not matched).
- **Case-Sensitivity:** Respects the `is_case_sensitive` configuration flag per term.
- **Evidence Linking:** Links directly to `TermBank.id` with evidence type `TERM`.
- **Confidence:** `0.980` (exact regex whole-word match).

### 2. Claims & Fact Registry Analyzer (`claims_analyzer.py`)
- **Objective:** Detect outdated pricing, expired claims, contradictory specifications, and unsupported absolute/superlative statements.
- **Fact Status Handling:**
  - `ACTIVE` and non-expired facts: Used as ground truth for numerical/pricing comparison.
  - `ACTIVE` but expired facts: Trigger `NEEDS_REVIEW` with no suggested correction (expired claims must be re-certified).
  - `DRAFT` / `REJECTED` facts: Completely ignored — never referenced as approved ground truth.
- **Unsupported Claims:** Flagged only when governed by an active Brand Rule requiring substantiation.
- **Evidence Linking:** Links directly to `FactRegistry.id` with evidence type `FACT`.
- **Confidence:** `0.950` for active price contradiction, `0.850` for expired reference, `0.850` for unsupported claims.

### 3. Tone & Voice Analyzer (`tone_analyzer.py`)
- **Objective:** Enforce brand voice guidelines (grounded, objective, technical) and detect sensationalism or hyperbolic language.
- **Span Deduplication:** When a negative example (e.g., `"game-changing miracle"`) and a hyperbole pattern (`"game-changing"`) both match at overlapping character offsets, the engine keeps only the longest, most specific match.
- **Evidence Linking:** Links to `BrandRule.id` with evidence type `RULE`.
- **Confidence:** `0.920` for exact negative example match, `0.880` for rule-governed hyperbole patterns.

### 4. Messaging Alignment Analyzer (`messaging_analyzer.py`)
- **Objective:** Verify alignment with approved positioning pillars and prevent unapproved competitor disparagement.
- **Competitor Policy:** Neutral competitor mentions (e.g., `"migration from AWS"`) are **not** flagged. Only pairings of competitor names with explicit derogatory adjectives (e.g., `"inferior"`, `"failing"`, `"broken"`) within an applicable rule context trigger violations.
- **Evidence Linking:** Links to `BrandRule.id` with evidence type `RULE`.
- **Confidence:** `0.940` for negative example match, `0.910` for competitor disparagement.

### 5. Visual Consistency Analyzer (`visual_analyzer.py`)
- **Objective:** Validate image dimensions, aspect ratios, and color palettes against the approved `BrandAsset` library.
- **Pillow Pixel Analysis:** When image bytes are supplied, the analyzer loads the image with Pillow, samples pixel color frequencies, and extracts dominant RGB colors.
- **Color Distance Math:** Computes Euclidean RGB distance:
  $$\Delta E_{\text{RGB}} = \sqrt{(r_1 - r_2)^2 + (g_1 - g_2)^2 + (b_1 - b_2)^2}$$
  with a configurable tolerance of $60$ (approx. $\pm 24\%$ per channel).
- **Separation of Detection Methods:** Clearly distinguishes `PIXEL_ANALYSIS` (image file) from `TEXT_HEX_DETECTION` (hex code written in copy).
- **Evidence Linking:** Links to `BrandAsset.id` with evidence type `ASSET`.
- **Confidence:** `0.980` for dimensions, `0.950` for pixel color analysis, `0.900` for text hex code detection.

### 6. Accessibility Analyzer (`accessibility_analyzer.py`)
- **Objective:** Verify WCAG 2.1 Level AA digital accessibility standards.
- **WCAG Contrast Thresholds:**
  - Normal text ($< 18\,\text{pt}$ regular / $< 14\,\text{pt}$ bold): Minimum $4.5 : 1$.
  - Large text ($\ge 18\,\text{pt}$ regular / $\ge 14\,\text{pt}$ bold): Minimum $3.0 : 1$.
  - Calculated strictly from explicit foreground/background hex pairs found in design specs.
- **Heading Structure:** Identifies skipped heading levels (e.g., H1 followed immediately by H3).
- **Vague Link Text:** Detects non-descriptive CTAs (e.g., `"click here"`, `"read more"`).
- **Alt-Text Gap Detection:** Flags scanned image documents where OCR or extractable text is unavailable.
- **Evidence Linking:** Links to `BrandRule.id` with evidence type `RULE`.
- **Confidence:** `0.990` for mathematical contrast calculation, `0.950` for structural heading check, `0.910` for link text.

---

## 3. Finding Verification Gate (`engine.py`)

Every candidate finding passes through a verification gate prior to database persistence:
1. **Snippet Non-Empty:** Discards findings with empty or whitespace-only snippets.
2. **Text Presence:** Confirms the flagged snippet appears in the extracted document text (case-insensitive).
3. **Offset Bounds:** Validates that `char_offset_start` and `char_offset_end` fall within $[0, \text{len}(\text{raw\_text})]$.
4. **Span Consistency:** Verifies that the difference between start and end offsets aligns with the snippet length ($\pm 20$ characters tolerance for whitespace).
5. **Cross-Category Deduplication:** Eliminates identical snippets at identical character offsets across analyzer passes.

---

## 4. Local Ollama Integration (`ollama_client.py`)

- **Design Principle:** Zero external cost, 100% private and local.
- **Health Verification:** Fast connection check ($1.5\,\text{s}$ timeout) to `http://localhost:11434/api/tags`.
- **Graceful Offline Mode:** When Ollama is offline or uninstalled, the engine executes in **standalone deterministic mode** without failing.
- **No Hallucinated AI:** The UI and API explicitly communicate whether analysis completeness was `FULL` or `DETERMINISTIC_ONLY`.

---

## 5. Verification & Test Results

### Backend Test Suite
```
tests/test_analysis.py .................................... [  5 passed]
tests/test_analysis_quality.py ............................ [ 50 passed]
tests/test_auth.py ........................................ [ 22 passed]
tests/test_constitution.py ................................ [  9 passed]
tests/test_db_integrity.py ................................ [  1 passed]
tests/test_documents.py ................................... [ 12 passed]
tests/test_health.py ...................................... [  2 passed]
======================= 101 passed, 1 warning in 34.77s =======================
```

### Frontend Production Build
```
Route (app)                              Size     First Load JS
┌ ○ /                                    4.78 kB         128 kB
├ ○ /_not-found                          873 B          88.2 kB
├ ○ /analysis                            5.66 kB         124 kB
├ ƒ /analysis/[id]                       7.02 kB         125 kB
├ ○ /constitution                        4.08 kB         127 kB
├ ○ /constitution/assets                 5.91 kB         129 kB
├ ○ /constitution/facts                  5.7 kB          129 kB
├ ○ /constitution/rules                  5.21 kB         128 kB
├ ○ /constitution/terms                  4.77 kB         128 kB
├ ○ /documents                           6.06 kB         129 kB
├ ƒ /documents/[id]                      6.7 kB          130 kB
└ ○ /login                               5.94 kB         115 kB
+ First Load JS shared by all            87.3 kB
✓ Generating static pages (12/12)
✓ Compiled successfully
```

### Demo Script Execution
`python scripts/demo_phase5_analysis.py` successfully detected all 6 controlled violations with zero duplicate tone findings, appropriate severity scoring, and accurate deterministic mode reporting.

---

## 6. Known Limitations

1. **Local Ollama Optionality:** In the current environment, Ollama is offline; contextual LLM checks are cleanly bypassed while all 6 deterministic engines execute with 100% coverage.
2. **Design File Color Swatches:** Hex contrast is computed from stated color pairs in document text. Direct embedded raster image contrast maps require pixel-by-pixel luminance grids (scheduled for future enhancement).
