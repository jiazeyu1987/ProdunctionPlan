# Test Plan

- Task ID: `excel-xlsx-20260413T195434`
- Created: `2026-04-13T19:54:34`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `Extend reporting to import the real workbook format, add strict resource mapping, support xlsx preview/commit, and keep same-day capacity compare working without fallback.`

## Test Scope

Validate three outcomes:

- The extended reporting model persists and returns the real workbook business fields required by the UI.
- The `.xlsx` preview and commit flow parses multiple sheets, fails fast with explicit row-level errors, and only persists rows that pass strict validation.
- The upgraded UI shows real reporting fields and imported rows remain compatible with the existing `当日产能` comparison flow.

Out of scope for this round:

- Bulk historical workbook migration for all past reporting files.
- Fuzzy mapping, automatic master-data creation, or compatibility fallback behavior.
- Complex business calculations on low-frequency optional fields beyond verifying that the fields can be persisted and displayed safely.

## Environment

- Workspace: `D:\ProjectPackage\ProductionPlan`
- Backend runtime: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Frontend runtime: `npm run dev` in `fronted`
- Browser validation: Playwright with a real local browser session
- Database strategy: temp SQLite databases for backend tests and the repo E2E SQLite setup for browser tests
- Workbook fixture: [棘突 造影导管(1).xlsx](D:/ProjectPackage/%E6%A3%98%E7%AA%81%20%E9%80%A0%E5%BD%B1%E5%AF%BC%E7%AE%A1(1).xlsx)

## Accounts and Fixtures

- Existing scheduler or reporting-capable account from the repo E2E fixtures
- Seeded orders, products, processes, and reporting resource mappings that cover:
  - one successful imported row
  - one row rejected for missing order
  - one row rejected for missing or ambiguous mapping
- Same-day line capacity audit fixtures for at least one imported report row so the compare modal can be revalidated

If any required fixture cannot be seeded, the validation must fail fast and record the missing prerequisite.

## Commands

- `python -m unittest backend.tests.test_reporting_capacity_compare backend.tests.test_reporting_excel_import`
  - Expected success signal: all targeted backend tests pass
- `npm run build`
  - Expected success signal: frontend production build completes without compile errors
- `npx playwright test tests/e2e/reporting-capacity-compare.e2e.spec.ts tests/e2e/reporting-xlsx-import.e2e.spec.ts`
  - Expected success signal: workbook import and compare browser cases pass and produce Playwright evidence artifacts

## Test Cases

### T1: Extended reporting fields persist and query correctly

- Covers: P1-AC1, P1-AC3
- Level: unit
- Command: `python -m unittest backend.tests.test_reporting_excel_import`
- Expected: persisted report rows contain the required workbook fields and the reporting list query returns those fields without placeholder-only values

### T2: Strict resource mapping resolves unique line scope

- Covers: P1-AC2, P1-AC4
- Level: unit
- Command: `python -m unittest backend.tests.test_reporting_excel_import`
- Expected: unique mappings resolve successfully, missing or ambiguous mappings raise explicit errors, and imported rows preserve the exact compare scope used by capacity compare

### T3: Workbook preview returns row-level validation for all sheets

- Covers: P2-AC1, P2-AC2
- Level: unit/integration
- Command: `python -m unittest backend.tests.test_reporting_excel_import`
- Expected: preview parses the workbook sheets, returns source sheet and row provenance, and reports row-level validation status with explicit failure reasons

### T4: Workbook commit persists only valid rows

- Covers: P2-AC3, P2-AC4
- Level: unit/integration
- Command: `python -m unittest backend.tests.test_reporting_excel_import`
- Expected: commit writes only rows that passed strict validation and never invents default workshop, line, process, or master-data values

### T5: Browser import flow previews workbook and surfaces failures

- Covers: P3-AC1, P3-AC4
- Level: e2e
- Command: `npx playwright test tests/e2e/reporting-xlsx-import.e2e.spec.ts`
- Expected: selecting a workbook shows a preview grid and any invalid rows display explicit row-level failure messages before commit

### T6: Browser import success refreshes the reporting list with real fields

- Covers: P3-AC1, P3-AC2
- Level: e2e
- Command: `npx playwright test tests/e2e/reporting-xlsx-import.e2e.spec.ts`
- Expected: a successful commit refreshes the reporting list and shows order number, dispatch number, product, process, resource, operator, section leader, quantity, and `当日产能`

### T7: Imported report rows still support same-day capacity comparison

- Covers: P3-AC3
- Level: e2e
- Command: `npx playwright test tests/e2e/reporting-capacity-compare.e2e.spec.ts tests/e2e/reporting-xlsx-import.e2e.spec.ts`
- Expected: imported rows with valid mapped scope can open the compare modal, select same-day audits, persist the chosen compare value, and keep the red/green color rules

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | reporting model | extended fields persist and query | unit | P1-AC1, P1-AC3 | `backend.tests.test_reporting_excel_import` output |
| T2 | resource mapping | strict unique mapping and compare compatibility | unit | P1-AC2, P1-AC4 | `backend.tests.test_reporting_excel_import` output |
| T3 | preview API | workbook parsed into row-level preview results | unit/integration | P2-AC1, P2-AC2 | `backend.tests.test_reporting_excel_import` output |
| T4 | commit API | only valid rows are persisted | unit/integration | P2-AC3, P2-AC4 | `backend.tests.test_reporting_excel_import` output |
| T5 | frontend import UI | preview and failure states in browser | e2e | P3-AC1, P3-AC4 | Playwright video, trace, or screenshot evidence |
| T6 | reporting list UI | imported data renders real business fields | e2e | P3-AC1, P3-AC2 | Playwright video, trace, or screenshot evidence |
| T7 | capacity compare | imported rows continue to support compare flow | e2e | P3-AC3 | Playwright video, trace, or screenshot evidence |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: playwright, python, unittest, npm
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: validation must run against the actual repository, local backend, local frontend, the real workbook fixture, and a real browser session
- Escalation rule: do not inspect withheld artifacts until the tester has recorded an initial verdict

## Pass / Fail Criteria

- Pass when:
  - all targeted backend tests pass
  - frontend build passes
  - browser tests prove preview, failure messaging, successful commit, and post-import compare compatibility
  - every PRD acceptance id is verified by at least one passing case with evidence
- Fail when:
  - any import path silently defaults missing mapping or master data
  - workbook preview omits sheet or row provenance
  - imported rows lose required business fields in query or list output
  - imported rows no longer support strict same-day capacity compare matching

## Regression Scope

- Existing manual reporting create and delete flows
- Existing reporting list ordering and filters
- Existing daily capacity audit query filters
- Existing `当日产能` compare modal behavior and red/green rendering
- Existing backend reporting delete and actual-capacity rebuild behavior

## Reporting Notes

Write validation results to `test-report.md`.

Each passing browser case must include non-task-artifact Playwright evidence such as a trace, video, screenshot, or HAR file.
