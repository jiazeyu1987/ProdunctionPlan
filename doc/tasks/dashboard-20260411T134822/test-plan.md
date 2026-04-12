# Test Plan

- Task ID: `dashboard-20260411T134822`
- Created: `2026-04-11T13:48:22`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `Build a scheduler dashboard with default one-month range, showing order completion rate, equipment failure rate (machine count below default requirement), total capacity, daily capacity trend, and material consumption ranking with bar/pie charts.`

## Test Scope

- Validate end-to-end scheduler dashboard behavior from backend aggregation to frontend rendering.
- Validate date-range filtering (default one month + custom range).
- Validate KPI correctness for:
  - order completion rate
  - equipment failure rate
  - total capacity
- Validate chart rendering for:
  - daily capacity trend
  - material consumption ranking
- Validate scheduler-only access for the new dashboard route.

Out of scope:

- Existing schedule algorithm correctness beyond regression sanity.
- Workshop-manager dashboard variants.

## Environment

- Backend runtime: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Frontend runtime: `npm run dev` in `fronted`
- E2E DB: seeded runtime DB via existing browser E2E runner (`fronted/scripts/run-e2e-browser.mjs`)
- Validation surface: real-browser
- Required tools: playwright, node, npm, python

## Accounts and Fixtures

- Scheduler account: `scheduler_e2e / Passw0rd!`
- Workshop manager account: `manager_e2e / Passw0rd!` (used for access control check)
- Required fixture expectation:
  - seeded orders and reports exist in E2E runtime DB
  - daily capacity topology rows exist for scheduler lines

If fixture setup or runtime DB creation fails, tester must stop and report the missing prerequisite.

## Commands

1. Lint frontend code
- Command: `cd fronted && npm run lint`
- Expected success signal: exit code `0`.

2. Run browser E2E suite (real browser)
- Command: `cd fronted && npm run e2e:browser`
- Expected success signal: Playwright run passes and evidence files are generated under `fronted/test-results/`.

3. Optional focused dashboard case run
- Command: `cd fronted && npx playwright test tests/e2e/production-plan.e2e.spec.ts --grep "dashboard"`
- Expected success signal: dashboard test case passes.

4. Validate test report structure
- Command: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id dashboard-20260411T134822`
- Expected success signal: no schema/content validation failures.

## Test Cases

### T1: Backend dashboard API returns required payload

- Covers: P1-AC1, P1-AC2
- Level: integration
- Command: `GET /api/dashboard/scheduler?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` as scheduler token
- Expected: valid payload with `range`, `summary`, `daily_capacity`, `material_consumption`; invalid date ranges fail with explicit error.

### T2: KPI calculation semantics are correct

- Covers: P1-AC3, P1-AC4
- Level: integration
- Command: dashboard API call + compare spot-check values against seeded DB data
- Expected: equipment failure metric strictly follows `machine_count < required_machines`; summary values are numeric and non-fabricated.

### T3: Scheduler can open dashboard and see default month range

- Covers: P2-AC1, P2-AC2
- Level: e2e
- Command: Playwright scheduler login and open dashboard page
- Expected: route accessible from sidebar; default date range equals latest 1 month window.

### T4: Dashboard shows required KPI cards and charts

- Covers: P2-AC3, P2-AC4
- Level: e2e
- Command: Playwright assertions on KPI test ids and chart containers
- Expected: all required KPIs and chart blocks are visible; chart labels/values are rendered when data exists.

### T5: Non-scheduler access is blocked

- Covers: P2-AC1
- Level: e2e
- Command: login as workshop manager and navigate to dashboard route
- Expected: route is redirected or blocked by role guard.

### T6: Dashboard regression does not break existing scheduler flow

- Covers: P3-AC2
- Level: e2e
- Command: run existing production-plan E2E flow cases (`T2/T3/T4/T5`)
- Expected: existing tests still pass.

### T7: Dashboard-specific case is evidence-backed

- Covers: P3-AC1
- Level: e2e
- Command: run dashboard case with Playwright evidence output enabled
- Expected: passing dashboard case has trace/screenshot/video evidence refs in non-task-artifact files.

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | Backend API | payload shape and date validation | integration | P1-AC1, P1-AC2 | API response logs |
| T2 | Backend metrics | KPI and equipment-failure semantics | integration | P1-AC3, P1-AC4 | API output + seeded data checks |
| T3 | Frontend route/filter | scheduler access and default month range | e2e | P2-AC1, P2-AC2 | screenshot + trace |
| T4 | Frontend rendering | required KPIs and chart blocks | e2e | P2-AC3, P2-AC4 | screenshot + trace + video |
| T5 | Role guard | non-scheduler blocked from dashboard | e2e | P2-AC1 | screenshot + trace |
| T6 | Regression | existing scheduler journey remains green | e2e | P3-AC2 | Playwright report |
| T7 | Evidence completeness | dashboard case has concrete browser artifacts | e2e | P3-AC1 | trace/video paths |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: playwright, node, npm, python
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: use real backend + frontend runtime and real browser session; no mocked UI assertions.
- Escalation rule: do not inspect withheld artifacts until the tester writes an initial verdict.

## Pass / Fail Criteria

- Pass when:
  - all required dashboard ACs are verified by passing test cases
  - real-browser dashboard test evidence exists
  - regression cases pass
- Fail when:
  - any required KPI or chart block is missing or incorrect
  - role access control is violated
  - real-browser validation cannot execute
  - evidence is missing for passing browser cases

## Regression Scope

- Scheduler navigation/sidebar behavior
- Order summary page and data loading
- Daily capacity page and reporting path
- Existing E2E cases in `production-plan.e2e.spec.ts`

## Reporting Notes

- Tester writes results to `doc/tasks/dashboard-20260411T134822/test-report.md`.
- Browser evidence paths must point to files under `fronted/test-results/` (screenshots, trace, video).
- Tester must remain independent from implementation changes.
