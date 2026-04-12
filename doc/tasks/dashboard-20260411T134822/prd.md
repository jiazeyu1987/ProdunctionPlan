# PRD

- Task ID: `dashboard-20260411T134822`
- Created: `2026-04-11T13:48:22`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `Build a scheduler dashboard with default one-month range, showing order completion rate, equipment failure rate (machine count below default requirement), total capacity, daily capacity trend, and material consumption ranking with bar/pie charts.`

## Goal

Deliver a scheduler-only dashboard page that provides period-based operational analytics and visual trends, with default range set to one month and chart-based presentation for fast planning decisions.

## Scope

- Add a scheduler dashboard query API that accepts a date range and returns aggregated metrics plus chart-ready series.
- Add dashboard calculations for:
  - order completion rate in selected period
  - equipment failure rate in selected period based on `machine_count < required_machines`
  - total capacity summary
  - daily capacity trend
  - material consumption ranking
- Add a new scheduler dashboard page and route in the legacy frontend shell.
- Add chart components (bar and pie) using local UI code (no external chart dependency required).
- Add or update E2E coverage for dashboard visibility and core metric rendering.

## Non-Goals

- No changes to schedule generation algorithm behavior.
- No changes to existing order summary business semantics outside required reuse.
- No new fallback branches, mock data, graceful degradation, or silent data-source switching.
- No workshop-manager dashboard scope expansion in this task.

## Preconditions

- Backend service and SQLite schema include required tables with valid data for:
  - `work_reports`
  - `daily_line_capacity_plan`
  - `daily_line_capacity_actual`
  - `masterdata_line_topology`
  - `production_orders`
  - `material_issue_items`
- Frontend can call backend through `NEXT_PUBLIC_BACKEND_BASE_URL`.
- Scheduler login is available.
- If any required table/data is missing for a requested range, API must fail fast with explicit error detail; do not fabricate values.

## Impacted Areas

- Backend:
  - `backend/app/api/routes/app_queries.py`
  - `backend/app/services/app_service.py`
- Frontend:
  - `fronted/src/legacy/App.jsx`
  - new dashboard feature files under `fronted/src/legacy/features/`
  - new page under `fronted/src/legacy/pages/`
  - `fronted/src/app/layout.tsx` style imports (if adding a new page stylesheet)
- Tests:
  - `fronted/tests/e2e/production-plan.e2e.spec.ts`
  - `fronted/tests/e2e/support/backendClient.ts` (if new helper is needed)

## Phase Plan

### P1: Backend Scheduler Dashboard Query API

- Objective: Implement a single backend query endpoint that returns all dashboard metrics and chart data for a date range.
- Owned paths:
  - `backend/app/api/routes/app_queries.py`
  - `backend/app/services/app_service.py`
- Dependencies:
  - existing `get_order_summary` and reporting/capacity tables
  - auth role checks in `app_queries` routes
- Deliverables:
  - new GET API route for scheduler dashboard
  - validated date-range input and fail-fast errors
  - response payload containing metrics, daily series, and material ranking

### P2: Frontend Dashboard Page and Charts

- Objective: Add a scheduler dashboard UI with default one-month filter, metric cards, and chart sections.
- Owned paths:
  - `fronted/src/legacy/App.jsx`
  - `fronted/src/legacy/pages/*` (new dashboard page)
  - `fronted/src/legacy/features/*` (new controller/query/chart modules)
  - `fronted/src/legacy/styles/pages/*` and `fronted/src/app/layout.tsx` (if new page css is added)
- Dependencies:
  - P1 API payload contract
  - existing auth + scheduler-only nav pattern
- Deliverables:
  - route and sidebar entry for scheduler dashboard
  - default one-month range behavior
  - metric cards for required KPIs
  - bar/pie charts for trends and ranking

### P3: Dashboard Validation and Regression

- Objective: Validate the dashboard using real browser E2E and targeted regression checks.
- Owned paths:
  - `fronted/tests/e2e/production-plan.e2e.spec.ts`
  - `fronted/tests/e2e/support/backendClient.ts` (if needed)
  - task artifacts under `doc/tasks/dashboard-20260411T134822/`
- Dependencies:
  - P1 and P2 implementation
  - existing Playwright runtime and seeded E2E DB flow
- Deliverables:
  - at least one dashboard E2E case
  - evidence files from real-browser run
  - updated execution and test artifacts with AC evidence refs

## Phase Acceptance Criteria

### P1

- P1-AC1: API validates `start_date` and `end_date` (`YYYY-MM-DD`) and rejects invalid range with explicit error.
- P1-AC2: API response includes these top-level groups: `range`, `summary`, `daily_capacity`, `material_consumption`.
- P1-AC3: `summary` includes order completion rate, equipment failure rate, and total capacity values sourced from real tables only.
- P1-AC4: Equipment failure rate uses explicit rule `machine_count < required_machines` on daily capacity rows within selected range.
- Evidence expectation: backend query response samples, validation command output, and code references for calculation rules.

### P2

- P2-AC1: Scheduler can access dashboard route from sidebar; non-scheduler roles cannot access it.
- P2-AC2: Dashboard defaults to one-month range and allows custom start/end date query.
- P2-AC3: Dashboard renders required KPI cards and chart blocks:
  - order completion rate
  - equipment failure rate
  - total capacity
  - daily capacity trend chart
  - material consumption ranking chart
- P2-AC4: Charts use bar/pie format and render non-empty labels/values when data exists.
- Evidence expectation: UI screenshots and real-browser traces showing dashboard rendering and filter updates.

### P3

- P3-AC1: Playwright includes at least one scheduler dashboard case that verifies route access and required KPI/chart presence.
- P3-AC2: Regression checks for existing scheduler flow still pass after dashboard integration.
- Evidence expectation: Playwright run output and generated evidence artifacts in `fronted/test-results/`.

## Done Definition

- All phases P1-P3 are marked `completed`.
- Every acceptance id is marked `completed` with evidence refs in `execution-log.md` and/or `test-report.md`.
- Real-browser dashboard validation passes.
- `validate_test_report.py` and `check_completion.py --apply` pass for this task id.

## Blocking Conditions

- Required backend tables or date-range records are missing and prevent truthful metric calculation.
- Scheduler auth/route preconditions are missing.
- Real-browser validation cannot run in current environment.
- Any step would require mock or fallback behavior not explicitly requested by user.
