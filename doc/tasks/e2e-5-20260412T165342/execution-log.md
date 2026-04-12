# Execution Log

- Task ID: `e2e-5-20260412T165342`
- Created: `2026-04-12T16:53:42`

## Phase P1

- Outcome: completed
- Acceptance ids: `P1-AC1`, `P1-AC2`, `P1-AC3`
- Changed paths:
  - `fronted/tests/e2e/simulation-calendar.e2e.spec.ts`
  - `fronted/src/legacy/features/schedule-calendar/scheduleCalendarPageUtils.js`
  - `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
  - `backend/app/services/app_service.py`
- Reviewed work:
  - Added a real-browser Playwright case that reads the highlighted simulation date from the calendar UI, clicks `advance one day` five times, checks the advancing date after every click, and then verifies reset returns the highlight to the seeded baseline.
  - Added one observable backend side-effect check by comparing reporting counts before the advance sequence, after five advances, and after reset.
  - Exposed `current_date` from `/api/masterdata/calendar-rules` and hydrated the calendar controller from that value so the UI starts from the seeded simulation baseline instead of the browser's local date.
- Validation run:
  - `npm --prefix fronted run lint`
  - `npm --prefix fronted run build`
  - `npm --prefix fronted run e2e:browser -- --grep "simulation advance"`
- Evidence refs:
  - `fronted/test-results/e2e/evidence-manifest.json`
  - `fronted/test-results/e2e/t1-simulation-advance-one-day-5-times-and-reset-simulation-0.png`
  - `fronted/test-results/e2e/t1-simulation-advance-one-day-5-times-and-reset-simulation-0.trace.zip`

## Phase P2

- Outcome: completed
- Acceptance ids: `P2-AC1`, `P2-AC2`, `P2-AC3`
- Changed paths:
  - `backend/app/services/app_service.py`
- Reviewed work:
  - First isolated browser execution failed for two real defects:
    - `simulation_state.current_date` was read via `SELECT ... current_date ...`, which SQLite resolved to the built-in `current_date` keyword and returned the actual day `2026-04-12` instead of the seeded row value `2026-04-10`.
    - `advance_simulation_one_day()` called `_rebuild_line_daily_actual_capacity_rows()` on `AppService`, but that helper no longer existed after the refactor to `LineDailyCapacityService`.
  - Fixed the simulation-state read to select `simulation_state.current_date AS current_date`.
  - Restored the missing actual-capacity rebuild path by delegating the private helper to `LineDailyCapacityService`.
  - Re-ran the same browser command without adding any fallback, mock, or silent downgrade logic.
- Validation run:
  - `python -m compileall backend\app`
  - `npm --prefix fronted run e2e:browser -- --grep "simulation advance"`
- Observed outcome:
  - Baseline date: `2026-04-10`
  - Final date after 5 advances: `2026-04-15`
  - Reset date: `2026-04-10`
  - Reporting count: `1 -> 31 -> 1`
- Evidence refs:
  - `fronted/test-results/playwright-output/simulation-calendar.e2e-si-68099--times-and-reset-simulation/error-context.md`
  - `fronted/test-results/e2e/evidence-manifest.json`
  - `fronted/test-results/e2e/browser-run-summary.json`

## Outstanding Blockers

- None.
