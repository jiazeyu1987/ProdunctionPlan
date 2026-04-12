# Test Plan

- Task ID: `task-23da952bd2-20260412T131549`
- Created: `2026-04-12T13:15:49+08:00`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `Add data backup and restore. The user can configure backup frequency and max retained backups, and the UI shows the timestamp for each backup.`

## Test Scope

Must validate:

- Backup config persistence (enabled, frequency_minutes, max_backups) stored in SQLite and readable after refresh and backend restart.
- Manual backup is executed as an async job and produces both a backup file and a backup record with created_at.
- Restore a specified backup as an async job, with explicit success/failure observability. Verify restore effect after backend restart using a config sentinel value.
- UI lists backups and shows per-backup created_at timestamp and correct ordering.
- Auto backup trigger (worker-driven) and retention (keep newest N, purge older).
- Fail-fast behavior: missing DB file, missing backup dir, missing backup file, locked restore target, invalid config must all fail with explicit error codes/messages (no silent downgrade).

Out of scope:

- Remote/offsite backups, encryption, compression, incremental backups.
- Multi-instance online restore guarantees (this task is scoped to the existing single-process worker model).

## Environment

- OS: Windows (PowerShell)
- Python: 3.12+ (matches `backend/Dockerfile`)
- Node.js: able to run `fronted/package.json` scripts
- Recommended DB: use an isolated E2E DB to avoid affecting `backend/data/production_plan.db`
  - `fronted/scripts/run-e2e-browser.mjs` seeds an isolated DB at `fronted/test-results/e2e/runtime/production_plan.e2e.db`
  - Alternatively, use the existing `backend/data/e2e/production_plan.e2e.db` used by `fronted/playwright.config.ts`
- Backup dir (must exist before starting backend):
  - Recommended: `backend/data/e2e/backups` or `fronted/test-results/e2e/runtime/backups`
  - Configure via `PRODUCTION_PLAN_BACKUP_DIR` (after implementation), and create the directory manually (fail-fast requires no auto-create).

## Accounts and Fixtures

- Use E2E seeded accounts (see `backend/scripts/seed_e2e_db.py` and `fronted/tests/e2e/support/constants.ts`):
  - Scheduler: `scheduler_e2e / Passw0rd!`
- Fixtures are local (seed script), no external services required.

If any required prerequisite is missing (DB file missing, backup dir missing, etc.), the tester must fail fast and record it.

## Commands

Backend automated check (no external services):

```powershell
python -m compileall backend\app
```

Frontend build and checks:

```powershell
npm --prefix fronted run lint
npm --prefix fronted run build
```

Browser validation (real-browser, playwright):

1) Evidence-producing browser E2E runner (recommended, seeds isolated DB and generates trace/screenshot manifest):

```powershell
npm --prefix fronted run e2e:browser -- --grep "backup"
```

2) Standard playwright E2E (uses `fronted/playwright.config.ts` webServer to start backend + frontend):

```powershell
npm --prefix fronted run e2e:playwright -- --grep "backup"
```

Expected success signals:

- All commands exit with code 0.
- Playwright produces reviewable evidence:
  - `fronted/test-results/e2e/evidence-manifest.json` (for `e2e:browser`)
  - `fronted/test-results/playwright-report` and `fronted/test-results/playwright-output` (for `e2e:playwright`)

## Test Cases

### T1: Backup config save and persisted reload (UI + job tracking)

- Covers: P1-AC1, P3-AC1
- Level: e2e
- Command: `npm --prefix fronted run e2e:browser -- --grep "backup config"`
- Expected: Masterdata page exposes a "Database Backup" surface; backup config supports enabled, frequency_minutes (minutes), max_backups; save action uses job tracking and reaches SUCCEEDED; after page refresh and backend restart the values remain unchanged; evidence is present via trace/screenshot referenced by `fronted/test-results/e2e/evidence-manifest.json`.

### T2: Manual backup creates a new backup record and UI shows created_at

- Covers: P1-AC2, P2-AC1, P3-AC2
- Level: e2e
- Command: `npm --prefix fronted run e2e:browser -- --grep "manual backup"`
- Expected: Clicking "Create Backup" enqueues and tracks a job to SUCCEEDED; backup list refresh shows a new top row with created_at (ISO semantics; second-level precision acceptable); evidence is present via trace/screenshot referenced by `fronted/test-results/e2e/evidence-manifest.json`.

### T3: Restore a specified backup and verify effect after backend restart (sentinel config)

- Covers: P2-AC2, P3-AC2
- Level: manual
- Command: `npm --prefix fronted run e2e:playwright -- --headed --grep "restore backup"`
- Expected: Save sentinel config frequency_minutes=60/max_backups=5, create manual backup A, change frequency_minutes to 120 and confirm UI shows it, restore backup A and confirm restore job SUCCEEDED with restored_backup_id=A, restart backend and confirm UI shows frequency_minutes back to 60; if atomic replace fails due to DB lock, the restore job FAILS with explicit error_code/message and operator guidance; capture screenshots (and trace if available).

### T4: Auto backup trigger and retention purge keeps only newest N backups

- Covers: P2-AC3, P1-AC2
- Level: manual
- Command: `npm --prefix fronted run e2e:playwright -- --headed --grep "auto backup retention"`
- Expected: Enable auto backup with frequency_minutes=1 and max_backups=2, keep backend+worker running long enough to create more than 2 backups, then refresh the list and confirm only the 2 newest records remain ordered by created_at desc and older backups are purged (records removed and files deleted); any purge failure is explicit and fails the job; capture screenshots (and optional read-only filesystem evidence).

### T5: Fail-fast observability when backup dir is missing or not writable

- Covers: P2-AC4, P3-AC2
- Level: manual
- Command: `Start backend with PRODUCTION_PLAN_BACKUP_DIR pointing to a non-existent directory (do not create it), then click "Create Backup" in the UI.`
- Expected: The backup job FAILS with a specific error_code (e.g. BACKUP_DIR_MISSING) and an error_message including the path; UI displays the failure details from the job and does not present success.

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | Masterdata UI + Backend config | Save/reload backup config and verify persistence | e2e | P1-AC1, P3-AC1 | `fronted/test-results/e2e/evidence-manifest.json` + trace/screenshot |
| T2 | Backup UI + Jobs | Manual backup succeeds; UI shows created_at | e2e | P1-AC2, P2-AC1, P3-AC2 | `fronted/test-results/e2e/evidence-manifest.json` + trace/screenshot |
| T3 | Restore + UI | Restore specified backup and verify after restart using sentinel config | manual | P2-AC2, P3-AC2 | screenshots + trace (if Playwright) |
| T4 | Auto trigger + Retention | Auto backups are triggered and purged to max_backups | manual | P2-AC3, P1-AC2 | screenshots + optional read-only fs evidence |
| T5 | Fail-fast | Missing backup dir causes explicit job failure visible in UI | manual | P2-AC4, P3-AC2 | screenshots (+ optional jobs API response) |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: playwright
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: run against the real repo and runtime. UI flows must be validated in a real browser via Playwright with concrete evidence files (trace/screenshot/manifest).
- Escalation rule: do not inspect withheld artifacts until an initial verdict is written, unless the main agent explicitly requests discrepancy analysis.

## Pass / Fail Criteria

- Pass when:
  - T1-T5 all pass.
  - Every acceptance id from PRD is covered by at least one test case and evidence is reviewable.
- Fail when:
  - Any acceptance fails, or any silent downgrade/mocked success behavior is observed.
  - UI cannot surface job failure details (error_code/message) or the jobs API does not reflect accurate job status.

## Regression Scope

- Existing masterdata config flows remain intact:
  - `GET /api/masterdata/config` still returns existing fields and frontend parsing does not break topology editing.
  - `POST /api/masterdata/config` job still saves existing line skeleton/topology/workshop manager settings.
- Job worker continues to process existing job types as before.

## Reporting Notes

Write results to `test-report.md` with:

- environment used (DB path, backup dir path, how backend/frontend were started)
- per-case results (pass/fail)
- evidence paths (manifest/trace/screenshot)
