# Test Plan: Masterdata Tab "设备台账"

- Task ID: `tab-20260413T194138`
- Created: `2026-04-13T19:41:38`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request (CN): 在主数据里的主任配置与数据备份中间增加一个 tab `设备台账`；表结构符合截图；默认数据为截图设备行。

## Test Scope

Validate that:

- Masterdata top-level tabs include a new tab `设备台账` and it is positioned between `主任配置` and `数据备份`.
- The new tab can be opened via click and via deep-link `/masterdata?tab=equipment_ledger`.
- The `设备台账` panel renders a table whose structure matches the screenshot:
  - Base columns include `设备编码`, `车间现场设备名称`, `工序名称`, `设备负责人`, `标准/小时`.
  - Group header `1日` spans 8 child columns: `应开机时间`, `实际开机时间`, `维修`, `调试`, `有效生产时间`, `当日产能`, `不合格产能`, `异常分析`.
- The table is seeded with the 13 equipment rows listed in the PRD and default day-column values match the screenshot:
  - `有效生产时间` is `0` for each row.
  - `当日产能`, `不合格产能`, `异常分析` are blank by default.

Out of scope:

- Backend persistence and save/edit UX for the ledger.
- Import/export and bulk editing.

## Environment

Required tools:

- Node.js + npm
- Python 3.x
- Playwright (via `fronted` devDependencies)

Runtime expectations:

- Playwright is configured to start backend and frontend via `webServer` in [playwright.config.ts](/D:/ProjectPackage/ProductionPlan/fronted/playwright.config.ts).
- E2E base URLs are `http://127.0.0.1:8000` (backend) and `http://127.0.0.1:2798` (frontend).

Fail-fast rule:

- If web servers do not start or health checks fail, stop and record the missing prerequisite and error output (no fallback, no mocks).

## Accounts and Fixtures

Use existing e2e credentials from [constants.ts](/D:/ProjectPackage/ProductionPlan/fronted/tests/e2e/support/constants.ts):

- Scheduler: `scheduler_e2e` / `Passw0rd!`

If login fails, tests fail fast and capture evidence (trace/video + error text).

## Commands

All commands are run from `D:\ProjectPackage\ProductionPlan` unless otherwise noted.

Backend deps:

```powershell
python -m pip install -r backend/requirements.txt
```

Frontend deps:

```powershell
cd fronted
npm ci
```

Run all Playwright e2e:

```powershell
cd fronted
npm run e2e:playwright
```

Run only the new spec:

```powershell
cd fronted
npx playwright test tests/e2e/masterdata-equipment-ledger.e2e.spec.ts
```

Expected success signal for the Playwright commands: exit code 0 and HTML report under `fronted/test-results/playwright-report`.

## Test Cases

### T1: Tab Visible and Ordered Correctly

- Covers: P1-AC1
- Level: e2e
- Command: `npx playwright test tests/e2e/masterdata-equipment-ledger.e2e.spec.ts -g "T1"`
- Expected: Visiting `/masterdata` shows a tab button `设备台账` positioned between `主任配置` and `数据备份` in the top-level tablist.

### T2: Deep-Link Opens Equipment Ledger Tab

- Covers: P1-AC2
- Level: e2e
- Command: `npx playwright test tests/e2e/masterdata-equipment-ledger.e2e.spec.ts -g "T2"`
- Expected: Navigating to `/masterdata?tab=equipment_ledger` opens the `设备台账` panel and `data-testid="masterdata-equipment-ledger-panel"` is visible.

### T3: Table Header Structure Matches Screenshot

- Covers: P2-AC1
- Level: e2e
- Command: `npx playwright test tests/e2e/masterdata-equipment-ledger.e2e.spec.ts -g "T3"`
- Expected: The table header includes base columns ending with `标准/小时` and a grouped header `1日` with 8 child columns matching the PRD.

### T4: Seeded Rows and Default Day Values

- Covers: P2-AC2, P2-AC3
- Level: e2e
- Command: `npx playwright test tests/e2e/masterdata-equipment-ledger.e2e.spec.ts -g "T4"`
- Expected: The table shows 13 seeded rows and defaults match the screenshot (`有效生产时间` is `0` for all rows; `当日产能`/`不合格产能`/`异常分析` are blank by default).

### T5: New Spec Passes Under Repo E2E Runner

- Covers: P3-AC1
- Level: e2e
- Command: `npm run e2e:playwright -- masterdata-equipment-ledger.e2e.spec.ts`
- Expected: The new equipment-ledger spec passes on a clean run and produces Playwright evidence artifacts.

### T6: Regression - Backup E2E Still Passes

- Covers: P3-AC2
- Level: e2e
- Command: `npx playwright test tests/e2e/masterdata-backup.e2e.spec.ts`
- Expected: Existing Masterdata backup e2e spec passes after adding the new tab/panel.

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | Masterdata tabs | Tab exists + correct order | e2e | P1-AC1 | Playwright trace/video/screenshot |
| T2 | Masterdata routing | Deep-link opens tab | e2e | P1-AC2 | Playwright trace/video |
| T3 | Equipment ledger UI | Header structure (grouped) | e2e | P2-AC1 | Playwright trace + screenshot |
| T4 | Equipment ledger UI | Seeded rows + default day values | e2e | P2-AC2, P2-AC3 | Playwright trace/video |
| T5 | E2E runner | New spec passes via repo command | e2e | P3-AC1 | Playwright report artifacts |
| T6 | Masterdata backup | Regression check | e2e | P3-AC2 | Playwright report artifacts |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: playwright
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: Run against the real repo and runtime using Playwright webServer; collect concrete evidence (trace/video/screenshots).
- Escalation rule: Do not inspect withheld artifacts until the tester has written an initial verdict or the main agent explicitly requests discrepancy analysis.

## Pass / Fail Criteria

- Pass when: All cases T1-T6 pass and every acceptance id is covered with evidence artifacts recorded in `test-report.md`.
- Fail when: Any case fails, or web servers cannot start, or the UI diverges from the screenshot-confirmed headers/default values.

## Regression Scope

- Masterdata existing tabs: `工艺路线`, `设备拓扑`, `主任配置`, `数据备份` basic navigation.
- Existing e2e spec `masterdata-backup.e2e.spec.ts` remains passing.

## Reporting Notes

Write results to `doc/tasks/tab-20260413T194138/test-report.md` and reference Playwright artifacts under `fronted/test-results/`.

