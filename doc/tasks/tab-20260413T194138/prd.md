# PRD: Masterdata Tab "设备台账"

- Task ID: `tab-20260413T194138`
- Created: `2026-04-13T19:41:38`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request (CN): 在主数据里的主任配置与数据备份中间增加一个 tab `设备台账`；设备台账里的数据结构符合截图表结构；默认数据写入截图中的设备行数据。

## Goal

In the legacy Masterdata page (`/masterdata`), add a new top-level tab named `设备台账` positioned between `主任配置` and `数据备份`. When active, the new tab shows a table matching the provided screenshot structure, seeded by default with the 13 equipment rows visible in the screenshot.

## Scope

- Legacy frontend Masterdata navigation: add a new tab entry between Director Config and Backup.
- `设备台账` panel: render a table with the required multi-row header (group header `1日`) and seed rows.
- Deep-linking: allow opening via `/masterdata?tab=<new-tab-key>` consistent with existing patterns.
- Automated coverage: add Playwright e2e assertions for the new tab + table rendering; keep existing backup e2e passing.

## Non-Goals

- No backend persistence unless explicitly requested.
  - Current `GET /api/masterdata/config` does not expose an equipment-ledger field; adding DB tables and API schema is out of scope for this task as written.
- No edit/save UX, no inline validations, no import/export, no "add 1000 rows" behavior unless explicitly asked.
- No redesign of the Masterdata page layout beyond inserting this tab and its panel.

## Screenshot Reference (Source of Truth)

Header labels and default cell values are confirmed against the stored screenshot crops:

- `doc/tasks/tab-20260413T194138/header_left.png`
- `doc/tasks/tab-20260413T194138/header_mid.png`
- `doc/tasks/tab-20260413T194138/header_right.png`
- `doc/tasks/tab-20260413T194138/rows_left.png`
- `doc/tasks/tab-20260413T194138/rows_right.png`

## Preconditions

- Node.js + npm available.
- Python available for the FastAPI server used by Playwright `webServer`.
- Dependencies installed:
  - `cd fronted; npm ci`
  - `python -m pip install -r backend/requirements.txt`
- Ports `2798` and `8000` available (Playwright config defaults).

If any item is missing, stop and record it as a blocking prereq (executor-owned action).

## Impacted Areas

- Frontend Masterdata:
  - `fronted/src/legacy/pages/MasterdataPage.jsx`
  - `fronted/src/legacy/features/masterdata/page/constants.js`
  - `fronted/src/legacy/features/masterdata/page/useMasterdataConfigPanelsController.js`
  - `fronted/src/legacy/features/masterdata/MasterdataConfigPanels.jsx`
  - `fronted/src/legacy/features/masterdata/**` (new panel component + seed data)
- E2E tests:
  - New spec under `fronted/tests/e2e/`
  - Regression: existing `fronted/tests/e2e/masterdata-backup.e2e.spec.ts`

## UI Requirements

### Tab Placement and Navigation

- Add a new top-level tab button labeled `设备台账` in Masterdata's tablist.
- Placement must be between the existing `主任配置` and `数据备份` buttons.
- Deep-link via query param:
  - Existing pattern: `/masterdata?tab=backup_config`
  - Proposed new key: `/masterdata?tab=equipment_ledger`
  - Note: `EQUIPMENT_TAB = "equipment"` already exists in `page/constants.js` and is currently mapped to `DEVICE_CONFIG_TAB` for legacy compatibility; do not repurpose it.

### Table Structure

Table columns must match the screenshot:

- Base columns:
  - `设备编码`
  - `车间现场设备名称`
  - `工序名称`
  - `设备负责人`
  - `标准/小时`
- Grouped header:
  - First header row includes group header `1日` spanning 8 child columns.
  - Second header row lists the child columns:
    - `应开机时间`
    - `实际开机时间`
    - `维修`
    - `调试`
    - `有效生产时间`
    - `当日产能`
    - `不合格产能`
    - `异常分析`

### Default Seed Data (Visible Rows)

Seed exactly the 13 rows visible in the screenshot:

1. A03079/B09312 | 旋转接头自动组装机/旋转接头点胶机 | 机器点胶旋转接头*2 | 钟凤霞 | 1960
2. A03272 | 旋塞阀护帽组装机 | 机器组装高压旋塞阀上护帽 | 钟凤霞 | 1400
3. A03284 | 高压旋塞阀组装机 | 机器组装高压旋塞阀 | 钟凤霞 | 1350
4. A03048 | 高频热合机 | 双气囊式止血带长片+气囊 | 钟凤霞 | 294
5. A03049 | 高频热合机 | 双气囊式止血带焊接通孔 | 钟凤霞 | 181
6. A03229-2 | 激光打标机 | 5F/6F新手柄护套 | 钟凤霞 | 700
7. A05066 | 高频热合机 | 双气囊式止血带焊接勾毛面*2（24cm） | 钟凤霞 | 173
8. A05067 | 高频热合机 | 双气囊止血带封边焊接 | 钟凤霞 | 421
9. A05176 | 高频热合机 | 双气囊式止血带软管通孔 | 钟凤霞 | 170
10. A05177/B03061 | 高频热合机/模温调节机 | 双气囊式止血带焊接大小囊 | 钟凤霞 | 450
11. B09473 | 高频热合机 | 双气囊式止血带短片勾面 | 钟凤霞 | 310
12. B09474 | 高频热合机 | 双气囊式止血带短片毛面 | 钟凤霞 | 185
13. B13013 | 激光打标机 | 刻印骨穿针 | 钟凤霞 | 60

### Default Values for Day Group Columns

- `应开机时间`, `实际开机时间`, `维修`, `调试` default to blank.
- `有效生产时间` defaults to `0` for each seeded row.
- `当日产能`, `不合格产能`, `异常分析` default to blank.

## Phase Plan

Use stable phase ids. Do not renumber ids after execution has started.

### P1: Add Masterdata Tab Entry Point

- Objective:
  - Add new top-level tab button `设备台账` between `主任配置` and `数据备份`.
  - Support deep-linking via `tab` query param (recommended key `equipment_ledger`).
- Owned paths:
  - `fronted/src/legacy/pages/MasterdataPage.jsx`
  - `fronted/src/legacy/features/masterdata/page/constants.js`
  - `fronted/src/legacy/features/masterdata/page/useMasterdataConfigPanelsController.js`
- Dependencies:
  - Must not break existing `/masterdata?tab=backup_config` and related flows.
- Deliverables:
  - New tab constant and selection logic.
  - Stable selectors: add `data-testid` for the new tab button and panel.

### P2: Implement "设备台账" Panel and Table Rendering

- Objective:
  - Render table with the two-row header and seeded data.
- Owned paths:
  - `fronted/src/legacy/features/masterdata/MasterdataConfigPanels.jsx`
  - New panel component under `fronted/src/legacy/features/masterdata/` (e.g. `EquipmentLedgerPanel.jsx`)
  - New seed module under the same feature directory.
- Dependencies:
  - Display-only; must not require backend schema changes.
- Deliverables:
  - Panel with `data-testid="masterdata-equipment-ledger-panel"`.
  - Table with `data-testid="equipment-ledger-table"`.

### P3: Add Playwright E2E Coverage

- Objective:
  - Verify tab insertion and table rendering in a real browser.
  - Keep existing Masterdata Backup e2e passing.
- Owned paths:
  - New `fronted/tests/e2e/masterdata-equipment-ledger.e2e.spec.ts` (recommended filename)
- Dependencies:
  - `fronted/playwright.config.ts` webServer must start backend + frontend successfully.
- Deliverables:
  - E2E checks for header structure and seeded row visibility.

## Phase Acceptance Criteria

### P1

- P1-AC1: Masterdata tab list includes `设备台账` and it is positioned between `主任配置` and `数据备份`.
- P1-AC2: `/masterdata?tab=equipment_ledger` opens the `设备台账` panel and marks the tab active.
- Evidence expectation:
  - Playwright trace/video and/or screenshot showing tab order and active panel.

### P2

- P2-AC1: `设备台账` table header structure matches screenshot, including group header `1日` and 8 child columns.
- P2-AC2: Table contains the 13 seeded rows and each row's first 5 columns match the seed data strings/numbers.
- P2-AC3: Default day-group values match the confirmed screenshot behavior:
  - `有效生产时间` is `0` for each seeded row.
  - `当日产能`, `不合格产能`, `异常分析` are blank by default.
- Evidence expectation:
  - Playwright evidence capturing header and at least the first and last seed rows.

### P3

- P3-AC1: New Playwright e2e spec passes via repo command.
- P3-AC2: Existing `fronted/tests/e2e/masterdata-backup.e2e.spec.ts` remains passing (regression).
- Evidence expectation:
  - Playwright report artifacts under `fronted/test-results/` and recorded evidence per test helper conventions.

## Done Definition

- P1, P2, P3 completed and each acceptance id has evidence recorded in `execution-log.md` and/or `test-report.md`.
- `cd fronted; npm run e2e:playwright` succeeds on a clean run.
- No fallback logic, mocks, or silent downgrades were introduced to force "success".

## Blocking Conditions

- Playwright cannot start real web servers using `fronted/playwright.config.ts` (backend health check or frontend startup fails).
- `cd fronted; npm ci` fails (cannot install required frontend dependencies).
- `python -m pip install -r backend/requirements.txt` fails (cannot start e2e backend server).
