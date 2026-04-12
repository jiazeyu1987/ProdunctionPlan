# PRD

- Task ID: `task-23da952bd2-20260412T131549`
- Created: `2026-04-12T13:15:49+08:00`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `Add data backup and restore. The user can configure backup frequency and max retained backups, and the UI shows the timestamp for each backup.`

## Goal

Add first-class backup and restore for the ProductionPlan SQLite database with:

- Persisted backup configuration: frequency and max retention.
- Manual backup and restore executed asynchronously as jobs (trackable via the existing jobs system).
- UI entry point (Masterdata page is acceptable) to configure settings, list backups with timestamps, and trigger backup/restore.
- Strict fail-fast behavior: if prerequisites are missing (DB file, backup dir, backup file, restore target locked, etc.), return an explicit error and stop. No silent downgrade, no mock, no hidden fallbacks.

## Scope

- Backend (FastAPI + SQLite):
  - Persist backup config and backup metadata in SQLite, maintained by the existing schema init + migration flow (`backend/sqlite/001_init.sql` and `backend/app/db.py:migrate_database_schema`).
  - Expose backup config and backup list via the existing masterdata config query path (prefer extending `GET /api/masterdata/config`), and add command endpoints for manual backup/restore using the existing commands -> jobs enqueue pattern.
  - Implement auto-backup triggering under the existing worker lifecycle (`backend/app/main.py` starts a single `JobWorker`), and enforce retention after each successful backup.
  - Define explicit AppError codes/messages for all failure modes (fail-fast).

- Frontend (Next + legacy masterdata page):
  - Add a visible entry point on `fronted/src/legacy/pages/MasterdataPage.jsx` for "Database Backup".
  - Show backup settings (frequency, max retained) and backup list (each with created_at timestamp).
  - Use the existing job tracking helper (`fronted/src/legacy/services/api.js:postContractAndTrackJob`) for save/backup/restore actions and display job status and errors.

## Non-Goals

- No remote/offsite backup, object storage, encryption, compression, differential/incremental backup.
- No implicit fallback behavior:
  - Do not auto-create the backup directory.
  - Do not auto-backup the current DB before restore.
- No guarantee of "online restore without restart". Restore will attempt an atomic DB file replacement; if the target DB file is locked/in use, restore must fail fast and instruct the operator to stop the service and retry.
- No external schedulers (cron, Celery, Redis). Auto-backup is only driven by the existing `JobWorker` process when it is running.

## Preconditions

- SQLite DB file exists:
  - DB path is configured by `PRODUCTION_PLAN_DB_PATH` in `backend/app/config.py` (default `backend/data/production_plan.db`).
  - If missing, backend already fails fast via `ensure_database_exists()`.
- Backup directory exists and is writable:
  - Add `PRODUCTION_PLAN_BACKUP_DIR` (suggest default `backend/data/backups`).
  - If missing or not writable, backup/restore jobs must fail fast with an explicit error code and include the path in the message. Do not create the directory.
- Restore requires the DB file to be atomically replaceable:
  - If `os.replace` fails due to file locks or permissions, restore must fail fast and instruct to stop the backend process and retry.

## Impacted Areas

- Backend config:
  - `backend/app/config.py`
- SQLite schema init + migrations:
  - `backend/sqlite/001_init.sql`
  - `backend/app/db.py`
- Masterdata config query/save chain:
  - `backend/app/services/app_service.py:get_masterdata_config`
  - `backend/app/services/app_service.py:save_masterdata_config` (executed via `LEGACY_MASTERDATA_CONFIG_SAVE` job)
- Commands -> jobs enqueue + dispatch:
  - `backend/app/api/routes/commands.py`
  - `backend/app/services/job_dispatcher.py`
  - `backend/app/worker.py`
- Frontend masterdata entry + parsing + API wrappers:
  - `fronted/src/legacy/pages/MasterdataPage.jsx`
  - `fronted/src/legacy/features/masterdata/dataTransformUtils.js:parseConfigResponse`
  - `fronted/src/legacy/features/masterdata/queryClient.js`
  - `fronted/src/legacy/features/masterdata/commandClient.js`
- E2E (real browser):
  - `fronted/tests/e2e/*` (add backup-focused cases using existing evidence harness)

## Phase Plan

### P1: Persist Backup Config + Backup Records and Expose via Queries

- Objective:
  - Persist backup config (enabled, frequency, max retention) and backup records (created_at, file path, etc.) in SQLite. Return them through the masterdata config query path (prefer extending `GET /api/masterdata/config`).
- Owned paths:
  - `backend/sqlite/001_init.sql`
  - `backend/app/db.py`
  - `backend/app/config.py`
  - `backend/app/services/app_service.py`
  - `backend/app/api/routes/app_queries.py` (if a dedicated query endpoint is added; default is to extend existing config response)
- Dependencies:
  - Existing masterdata config query: `GET /api/masterdata/config` implemented via `backend/app/api/routes/app_queries.py` -> `AppService.get_masterdata_config()`.
  - Existing masterdata config save: `POST /api/masterdata/config` enqueues a job via `backend/app/api/routes/commands.py` and executes `AppService.save_masterdata_config()` via `JobDispatcher`.
  - Existing migration entrypoint: `backend/app/db.py:prepare_database()`.
- Deliverables:
  - New tables (names can be adjusted but must be consistent and migrated):
    - `app_backup_config(singleton_key PRIMARY KEY, enabled_flag INTEGER, frequency_minutes INTEGER, max_backups INTEGER, updated_at TEXT)`
    - `app_backup_records(backup_id PRIMARY KEY, created_at TEXT, trigger TEXT, backup_path TEXT, size_bytes INTEGER, created_by_user_id TEXT, created_by_username TEXT)`
  - Extend `GET /api/masterdata/config` response:
    - `data.backup_config: { enabled_flag, frequency_minutes, max_backups, updated_at }`
    - `data.backup_records: [{ backup_id, created_at, trigger, size_bytes, created_by_username }]` sorted by `created_at DESC`
  - Extend `save_masterdata_config(payload)` to accept and persist `backup_config` (without breaking existing validations for line skeletons/topology/workshop manager scopes).

### P2: Manual Backup/Restore Jobs + Auto Backup Trigger + Retention + Fail-Fast

- Objective:
  - Implement manual backup and restore as asynchronous jobs. Add an in-process auto-backup trigger in the existing `JobWorker` loop. Enforce retention (delete oldest beyond max). Ensure fail-fast errors are explicit and observable in job records.
- Owned paths:
  - `backend/app/api/routes/commands.py`
  - `backend/app/services/job_dispatcher.py`
  - `backend/app/worker.py`
  - `backend/app/services/backup_service.py` (recommended new module to centralize backup/restore/purge logic)
- Dependencies:
  - Existing jobs persistence and tracking: `jobs` table, `backend/app/repositories/jobs.py`, `GET /api/jobs/{job_id}`.
  - Worker execution model: `backend/app/worker.py:JobWorker` processes jobs one-by-one.
- Deliverables:
  - New command endpoints (example routes; must follow the commands enqueue pattern):
    - `POST /api/masterdata/backups/create` -> enqueue `DB_BACKUP_CREATE` (manual)
    - `POST /api/masterdata/backups/{backup_id}/restore` -> enqueue `DB_BACKUP_RESTORE`
  - New job types in `JobDispatcher`:
    - `DB_BACKUP_CREATE` (manual)
    - `DB_BACKUP_CREATE_AUTO` (auto)
    - `DB_BACKUP_RESTORE`
  - Backup implementation constraints:
    - Create a consistent SQLite snapshot using SQLite backup API (`sqlite3.Connection.backup(...)`) or equivalent consistency-safe approach.
    - Backup filename must embed a timestamp and backup_id.
    - Missing backup dir, missing DB file, or write failures must raise `AppError` and fail the job with explicit `error_code` and `error_message`.
  - Restore implementation constraints:
    - Only allow restore by `backup_id` that exists in `app_backup_records`.
    - Validate that the backup file exists. If missing: fail fast.
    - Use "copy to temp file, then atomic replace" (`os.replace`) to avoid partial writes.
    - If atomic replace fails due to file locks: fail fast. Do not attempt alternate downgrade paths.
    - On success, job result must include `restored_backup_id` and `restored_at`, and UI must clearly state that a backend restart is required for all connections to use the restored DB.
  - Auto backup trigger:
    - Add a throttled check in `JobWorker` loop (e.g. once per 60 seconds) that reads `app_backup_config`.
    - If enabled and due (based on last auto backup record time), enqueue `DB_BACKUP_CREATE_AUTO`.
    - Use deterministic `request_id` (e.g. minute-granularity timestamp) to prevent duplicate enqueues within the same window (leveraging `jobs.request_id` uniqueness behavior).
  - Retention:
    - After each successful backup, keep only the newest `max_backups` records (by created_at). For older ones: delete the file first, then delete the DB record.
    - If file deletion or record deletion fails, fail the job and report the error (no silent ignore).

### P3: Frontend UI Entry + Interactions + Job Tracking

- Objective:
  - Add a "Database Backup" surface in the Masterdata page to edit settings, list backups with timestamps, and trigger manual backup/restore with job tracking.
- Owned paths:
  - `fronted/src/legacy/pages/MasterdataPage.jsx`
  - `fronted/src/legacy/features/masterdata/page/constants.js` (add a new tab constant if implemented as a tab)
  - `fronted/src/legacy/features/masterdata/dataTransformUtils.js`
  - `fronted/src/legacy/features/masterdata/queryClient.js`
  - `fronted/src/legacy/features/masterdata/commandClient.js`
  - `fronted/src/legacy/features/masterdata/BackupPanel.jsx` (recommended new component)
  - `fronted/tests/e2e/*.spec.ts` (add backup-focused tests)
- Dependencies:
  - Masterdata bootstrap loading: `fronted/src/legacy/features/masterdata/service.js` loads `/api/masterdata/config`.
  - Job tracking: `fronted/src/legacy/services/api.js:postContractAndTrackJob`.
- Deliverables:
  - UI shows:
    - Backup config form: enabled, frequency_minutes (explicit unit: minutes), max_backups.
    - Manual "Create Backup" button: triggers a job and shows job state and errors.
    - Backup list: shows created_at, trigger (AUTO/MANUAL), size, and provides a Restore action.
    - Restore action includes an explicit confirmation and a post-success note "Restart backend required".
  - Saving config reuses `POST /api/masterdata/config` job (`LEGACY_MASTERDATA_CONFIG_SAVE`) and refreshes config and backup list after completion.

## Phase Acceptance Criteria

### P1

- P1-AC1: Backup config (enabled_flag, frequency_minutes, max_backups) is persisted in SQLite and remains consistent after refresh and backend restart.

Verification: `GET /api/masterdata/config` returns `data.backup_config` with `enabled_flag`, `frequency_minutes`, `max_backups`, and `updated_at`; saving via the existing masterdata config command (job-based) persists the values; values remain consistent after a backend restart.

- P1-AC2: Backup list is queryable and each backup record includes `backup_id` and `created_at` (ISO 8601) sorted by newest first.

Verification: `GET /api/masterdata/config` (or a dedicated query endpoint if chosen) returns `data.backup_records[]` and each item includes `backup_id` and `created_at`; list is sorted by newest first.

Evidence expectation: Repeatable API checks for GET/POST + GET, and the returned payload includes the new fields.

### P2

- P2-AC1: Manual backup can be triggered as a job and, on success, produces both a backup file under `PRODUCTION_PLAN_BACKUP_DIR` and a corresponding `app_backup_records` entry with correct created_at semantics.

Verification: the manual backup command enqueues a job; the job transitions to SUCCEEDED; the backup file exists under `PRODUCTION_PLAN_BACKUP_DIR`; `app_backup_records` includes a new record for the job output.

- P2-AC2: Restore a specified backup can be triggered as a job and is both successful and fail-fast observable.

Verification: restore command enqueues a job; on success, job result includes `restored_backup_id` and `restored_at`; if `backup_id` does not exist or the backup file is missing, the job fails with explicit `error_code`/`error_message`; if the DB file is locked and atomic replace fails, the job fails fast with an explicit error and an operator action message (stop service and retry).

- P2-AC3: Auto backup is triggered by the worker when enabled, and retention keeps only the newest `max_backups` backups.

Verification: when `backup_config.enabled_flag=1`, the worker auto-enqueues `DB_BACKUP_CREATE_AUTO` based on `frequency_minutes`; after more than `max_backups` backups exist, only the newest `max_backups` remain and older backup files are deleted along with their records; auto enqueue is idempotent per time window (no duplicates).

- P2-AC4: Backup and restore are strict fail-fast with explicit errors and no silent downgrade.

Verification: missing prerequisites must cause explicit failure (DB file missing; backup dir missing/not writable; `backup_id` not found; backup file missing; restore target cannot be atomically replaced; invalid config values); failed jobs expose `error_code` and `error_message` via the jobs API and the UI can display them.

Evidence expectation: Jobs API shows SUCCEEDED/FAILED states and explicit error details; no silent ignores.

### P3

- P3-AC1: UI provides a discoverable entry point to edit backup config and uses job tracking to show progress and errors; on success, the UI refresh shows persisted values.

Verification: Masterdata page includes a "Database Backup" surface; config save shows job progress and errors; after job success and refresh, UI reflects the persisted config.

- P3-AC2: UI lists backups with per-backup created_at timestamps and supports manual backup and restore interactions with job tracking.

Verification: UI shows per-backup `created_at` timestamp and ordering; "Create Backup" triggers a job and the new record appears after success; "Restore" triggers a job and shows explicit success/failure; on success, UI states that restart is required and post-restart refresh reflects restored DB state (e.g. config sentinel value reverts).

Evidence expectation: Real-browser (playwright) trace + screenshot evidence proves entry point, config persistence, list timestamps, and manual backup/restore with job tracking.

## Done Definition

- All phases P1-P3 completed.
- All acceptance criteria (P1-AC1 through P3-AC2) are verified by test cases in `test-plan.md` with concrete evidence (trace/screenshot/manifest) for real-browser validations.
- No fallback/mock/silent downgrade behaviors were introduced.

## Blocking Conditions

- `PRODUCTION_PLAN_DB_PATH` points to a missing SQLite file.
- `PRODUCTION_PLAN_BACKUP_DIR` is missing or not writable (and the implementation must fail fast rather than creating it).
- The runtime environment cannot atomically replace the DB file for restore (restore cannot be completed).
- Auto-backup cannot be implemented under the existing `JobWorker` lifecycle and external schedulers are disallowed; the task must stop rather than introducing implicit fallback.
