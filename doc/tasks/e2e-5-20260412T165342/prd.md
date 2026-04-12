# PRD

- Task ID: `e2e-5-20260412T165342`
- Created: `2026-04-12T16:53:42+08:00`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `使用 e2e 测试点击推进一天 5 次并验证结果，再点击重置模拟并验证是否符合预期`

## Goal

用真实浏览器验证排期月历页的“推进一天 / 重置模拟”手动模拟链路，明确回答当前实现是否符合预期：

- 排产员在月历页连续点击“推进一天”5次后，模拟当前日期按天稳定推进。
- 推进过程中，后端模拟副作用真实发生且可观测。
- 点击“重置模拟”后，模拟当前日期和模拟副作用一起恢复到推进前基线。

如果验证过程中发现当前实现不符合预期，则在最小范围内修复，并用同一条 E2E 链路复验；不引入 fallback、mock 或静默降级。

## Scope

- 前端月历页人工模拟入口与可观测状态：
  - `fronted/src/legacy/pages/ScheduleCalendarPage.jsx`
  - `fronted/src/legacy/features/schedule-calendar/components/ScheduleCalendarSettingsPanel.jsx`
  - `fronted/src/legacy/features/schedule-calendar/components/ScheduleCalendarGrid.jsx`
  - `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
- 前端手动模拟命令客户端：
  - `fronted/src/legacy/features/dispatch-alert/commandClient.js`
- 真实浏览器 E2E 与证据产物：
  - `fronted/tests/e2e/*.spec.ts`
  - `fronted/tests/e2e/support/*`
  - `fronted/scripts/run-e2e-browser.mjs`
  - `fronted/playwright.config.ts`
- 必要时用于修复缺陷的后端模拟实现：
  - `backend/app/api/routes/commands.py`
  - `backend/app/services/job_dispatcher.py`
  - `backend/app/services/app_service.py`

## Non-Goals

- 不重做模拟算法，不改变“推进一天”与“重置模拟”的产品定义。
- 不扩展到完整重排、发布、报工闭环回归，除非验证该链路所必需。
- 不新增兼容分支、测试专用 fallback、或仅为让测试通过而隐藏真实错误。
- 不把本任务扩展为服务器发布任务。

## Preconditions

- Node.js / npm、Playwright、Python 可在本地运行。
- `fronted/scripts/run-e2e-browser.mjs` 能创建隔离 E2E 数据库并启动真实前后端。
- E2E 种子脚本可用：
  - `backend/scripts/seed_e2e_db.py`
- E2E 账号可用：
  - 排产员：`scheduler_e2e / Passw0rd!`
- 月历页模拟按钮对排产员可见并可点击：
  - `schedule-calendar-sim-advance-day-btn`
  - `schedule-calendar-sim-reset-btn`
- 页面存在可用于验证模拟当前日期的真实可观测信号：
  - `schedule-calendar-day-YYYY-MM-DD` 单元格
  - `lite-calendar-cell-current-day` 当前日高亮 class

若任一前置条件缺失，应停止并记录到 `task-state.json.blocking_prereqs`。

## Impacted Areas

- 前端当前日期显示逻辑依赖本地状态 `simulatedCurrentDate`，推进/重置后是否与后端返回一致是本次验证重点。
- 后端 `advance_simulation_one_day()` 与 `reset_manual_simulation()` 负责修改 `simulation_state`、创建/恢复快照、补写/回滚模拟报工与产能数据。
- E2E 需要同时验证 UI 与后端副作用，因此会复用：
  - `fronted/tests/e2e/support/backendClient.ts`
  - `fronted/tests/e2e/support/evidence.ts`
- 既有 E2E 套件已覆盖月历页重排与发布流程：
  - `fronted/tests/e2e/production-plan.e2e.spec.ts`
  本任务要在不破坏现有浏览器证据体系的前提下补充手动模拟覆盖。

## Phase Plan

### P1: Add Deterministic Browser Coverage For Manual Simulation Advance And Reset

- Objective:
  - 新增或扩展月历页 E2E，用真实浏览器驱动“推进一天”5次与“重置模拟”，并把预期锚定到稳定的页面/后端可观测值。
- Owned paths:
  - `fronted/tests/e2e/*.spec.ts`
  - `fronted/tests/e2e/support/*`
  - `fronted/scripts/run-e2e-browser.mjs`
  - `fronted/playwright.config.ts`
- Dependencies:
  - 月历页按钮与当前日高亮：
    - `fronted/src/legacy/features/schedule-calendar/components/ScheduleCalendarSettingsPanel.jsx`
    - `fronted/src/legacy/features/schedule-calendar/components/ScheduleCalendarGrid.jsx`
  - 模拟命令控制器：
    - `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
  - 后端手动模拟命令：
    - `backend/app/services/app_service.py`
- Deliverables:
  - 一个稳定的浏览器用例，能够：
    - 读取推进前基线日期
    - 连续点击“推进一天”5次
    - 校验每一步日期推进与成功消息
    - 校验后端副作用增加
    - 点击“重置模拟”
    - 校验日期与副作用恢复到基线

### P2: Execute The Simulation E2E And Judge Current Behavior Against Expected Outcome

- Objective:
  - 在隔离 E2E 运行时执行目标浏览器用例，判断当前实现是否符合预期；若发现缺陷，则最小范围修复并复验。
- Owned paths:
  - `fronted/tests/e2e/*.spec.ts`
  - `fronted/src/legacy/features/schedule-calendar/*`
  - `backend/app/services/app_service.py`
  - `backend/app/api/routes/commands.py`
  - `backend/app/services/job_dispatcher.py`
- Dependencies:
  - P1 中新增的 E2E 覆盖
  - `npm --prefix fronted run e2e:browser`
  - 真实浏览器证据文件与 manifest
- Deliverables:
  - 通过的目标 E2E 运行结果与证据文件
  - 若实现不符合预期，最小修复及复验结果
  - 对“是否符合预期”的明确结论，带具体日期与观测值

## Phase Acceptance Criteria

### P1

- P1-AC1: 存在一个稳定的真实浏览器用例，能够从页面真实可见的当前日高亮中提取基线日期，并在连续点击“推进一天”5次后，逐次校验日期按天推进。
- P1-AC2: 同一用例在点击“重置模拟”后，能够校验当前日高亮回到推进前基线日期，而不是停留在推进后的日期。
- P1-AC3: 同一用例会记录至少一个后端副作用基线（如报工数量），并验证“推进后变化、重置后恢复”。
- Evidence expectation: `execution-log.md` 记录新增/修改的 E2E 路径、断言方式、以及为何这些断言足以回答“是否符合预期”。

### P2

- P2-AC1: 目标浏览器 E2E 在隔离运行时可执行并生成真实证据文件（截图、trace、manifest 至少其一可用于 tester 复核）。
- P2-AC2: 最终结论明确包含具体日期与观测值，例如“基线日期是 2026-04-10，连续推进 5 次后变为 2026-04-15，重置后回到 2026-04-10”。
- P2-AC3: 如果初次运行发现实现不符合预期，修复后的复验必须通过，且未引入 fallback、mock 或静默降级。
- Evidence expectation: `execution-log.md` 与 `test-report.md` 都要包含目标 E2E 命令、环境路径、证据文件路径，以及最终是否符合预期的结论。

## Done Definition

- P1、P2 全部完成。
- 所有 acceptance ids 均有证据支持。
- 真实浏览器用例可在隔离 E2E 数据库上复现“推进一天 5 次 + 重置模拟”的完整链路。
- `test-report.md` 明确回答当前实现是否符合预期；若曾不符合，报告中还要说明修复后结果。
- `validate_test_report.py` 与 `check_completion.py --apply` 成功通过。

## Blocking Conditions

- 隔离 E2E 数据库无法创建或浏览器运行器无法启动真实前后端。
- 月历页当前日没有稳定可观测信号，导致无法判断推进/重置结果。
- 模拟命令接口无法被 E2E 账号调用，或调用后没有可追踪的成功/失败结果。
- 真实浏览器证据文件无法生成。
