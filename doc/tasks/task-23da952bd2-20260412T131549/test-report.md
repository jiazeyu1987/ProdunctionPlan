# Test Report

- Task ID: `task-23da952bd2-20260412T131549`
- Created: `2026-04-12T13:15:49`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `增加数据备份、恢复功能，可设置备份频率、最大备份个数，并展示每条备份时间`

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-browser
- Tools: playwright, python, npm
- Initial readable artifacts: prd.md, test-plan.md
- Initial withheld artifacts: execution-log.md, task-state.json
- Initial verdict before withheld inspection: yes
- Runtime DB path: `D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\runtime\production_plan.e2e.db` for the seeded browser runner, plus `D:\ProjectPackage\ProductionPlan\backend\data\e2e\production_plan.e2e.db` for isolated Playwright checks.
- Runtime backup dirs: `D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\runtime\backups`, `D:\ProjectPackage\ProductionPlan\backend\data\e2e\backups`, and missing-dir negative case `D:\ProjectPackage\ProductionPlan\backend\data\e2e\backups-missing`.

Record the tester's first-pass visibility honestly. In `blind-first-pass`, the tester should record `yes` only after writing an initial verdict before inspecting withheld artifacts.

## Results

Add one subsection per executed test case using the test case ids from `test-plan.md`.

Each subsection should use this shape:

`### T1: concise title`

- `Result: passed|failed|blocked|not_run`
- `Covers: P1-AC1`
- `Command run: exact command or manual action`
- `Environment proof: runtime, URL, browser session, fixture, or deployment proof`
- `Evidence refs: screenshot, video, trace, HAR, or log refs`
- `Notes: concise findings`

For `real-browser` validation, include at least one evidence ref that resolves to an existing non-task-artifact file, such as `evidence/home.png`, `evidence/trace.zip`, or `evidence/session.har`.

### T1: Backup config save and persisted reload (UI + job tracking)

- Result: passed
- Covers: P1-AC1, P3-AC1
- Command run: `npm --prefix fronted run e2e:browser -- --grep "T1 backup config save, manual backup, and restore"`
- Environment proof: Seeded browser runner against `D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\runtime\production_plan.e2e.db` with backend `http://127.0.0.1:8000` and frontend `http://127.0.0.1:2798/masterdata?tab=backup_config`.
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\evidence-manifest.json, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t1-backup-config-save-manual-backup-and-restore-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t1-backup-config-save-manual-backup-and-restore-0.trace.zip
- Notes: Scheduler saved enabled=`1`, `frequency_minutes=1`, `max_backups=2`; UI success state appeared and a reload after restore showed `frequency_minutes=1`, proving persisted config round-trips through the browser flow.

### T2: Manual backup creates a new backup record and UI shows created_at

- Result: passed
- Covers: P1-AC2, P2-AC1, P3-AC2
- Command run: `npm --prefix fronted run e2e:browser -- --grep "T1 backup config save, manual backup, and restore"`
- Environment proof: Same seeded browser session as T1; manual backup was triggered from the Masterdata backup panel against `D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\runtime\backups`.
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\evidence-manifest.json, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t1-backup-config-save-manual-backup-and-restore-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t1-backup-config-save-manual-backup-and-restore-0.trace.zip
- Notes: The browser run created backup `6b4e06ee25f242cfa33544ea32b0537d`, refreshed the top row in the list, and displayed a non-empty `created_at` cell for that backup.

### T3: Restore a specified backup and verify effect after backend restart (sentinel config)

- Result: passed
- Covers: P2-AC2, P3-AC2
- Command run: `npm --prefix fronted run e2e:browser -- --grep "T1 backup config save, manual backup, and restore"`
- Environment proof: Same seeded browser session as T1/T2; the scenario changed `frequency_minutes` from `1` to `2`, restored the just-created backup, and then reloaded the Masterdata backup tab to confirm the restored value.
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\evidence-manifest.json, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t1-backup-config-save-manual-backup-and-restore-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t1-backup-config-save-manual-backup-and-restore-0.trace.zip
- Notes: Restore succeeded for backup `6b4e06ee25f242cfa33544ea32b0537d`; the browser-visible success message required backend restart, and the post-restore reload showed `frequency_minutes` returned from `2` to `1`.

### T4: Auto backup trigger and retention purge keeps only newest N backups

- Result: passed
- Covers: P2-AC3, P1-AC2
- Command run: `python backend\scripts\seed_e2e_db.py --output backend\data\e2e\production_plan.e2e.db --force --json` ; `python backend\scripts\prepare_auto_backup_retention_e2e.py --db-path backend\data\e2e\production_plan.e2e.db --backup-dir backend\data\e2e\backups` ; `npm --prefix fronted run e2e:playwright -- --grep "T4 auto backup retention"`
- Environment proof: Prepared isolated backend E2E DB `D:\ProjectPackage\ProductionPlan\backend\data\e2e\production_plan.e2e.db`, invoked real worker auto-backup logic via `prepare_auto_backup_retention_e2e.py`, then opened `http://127.0.0.1:2798/masterdata?tab=backup_config` in Playwright to verify the retained rows shown to the scheduler.
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\evidence-manifest.json, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t4-auto-backup-retention-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t4-auto-backup-retention-0.trace.zip
- Notes: The UI showed exactly two retained AUTO backups, both with visible timestamps, and the backend-backed list remained sorted newest-first after retention.

### T5: Fail-fast observability when backup dir is missing or not writable

- Result: passed
- Covers: P2-AC4, P3-AC2
- Command run: `python backend\scripts\seed_e2e_db.py --output backend\data\e2e\production_plan.e2e.db --force --json` ; `$env:PRODUCTION_PLAN_E2E_BACKUP_DIR='D:\ProjectPackage\ProductionPlan\backend\data\e2e\backups-missing'; npm --prefix fronted run e2e:playwright -- --grep "T5 missing backup dir fail fast"`
- Environment proof: Playwright started backend against `D:\ProjectPackage\ProductionPlan\backend\data\e2e\production_plan.e2e.db` with `PRODUCTION_PLAN_E2E_BACKUP_DIR` pointing to a non-existent directory, then triggered “立即备份” from the Masterdata backup panel.
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\evidence-manifest.json, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t5-missing-backup-dir-fail-fast-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t5-missing-backup-dir-fail-fast-0.trace.zip
- Notes: The UI surfaced `BACKUP_DIR_MISSING` together with a Chinese explanation (`备份目录不存在，请先创建后再重试。`), confirming fail-fast error visibility without silent downgrade.

## Final Verdict

- Outcome: passed
- Verified acceptance ids: P1-AC1, P1-AC2, P2-AC1, P2-AC2, P2-AC3, P2-AC4, P3-AC1, P3-AC2
- Blocking prerequisites:
- Summary: Real-browser validation covered backup config save/reload, manual backup, restore, auto-backup retention visibility, and missing-backup-dir fail-fast behavior. All PRD acceptance ids have at least one passing browser-backed case and the evidence files exist under `fronted/test-results/e2e`.

## Open Issues

- None yet.
