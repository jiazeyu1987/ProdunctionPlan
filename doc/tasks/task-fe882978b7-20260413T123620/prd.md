# PRD

- Task ID: `task-fe882978b7-20260413T123620`
- Created: `2026-04-13T12:36:20`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `修改当前前端里的乱码问题、描述不正式问题，以及英文未转换为中文的问题`

## Goal

修复当前前端中真实会展示给用户的文案问题，确保相关页面不再出现英文提示、内部字段名、或不正式的中文描述，并保持现有业务行为不变。

## Scope

- `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
- `fronted/src/legacy/features/daily-capacity/useDailyCapacityController.js`
- `fronted/src/legacy/utils/i18n.js`
- `fronted/tests/e2e/copy-verification.spec.ts`
- `fronted/tests/e2e/simulation-calendar.e2e.spec.ts`

## Non-Goals

- 不修改后端接口返回结构或后端提示语生成逻辑。
- 不改动排产、报工、主数据等业务计算规则。
- 不重做页面布局、交互结构或视觉样式。
- 不引入兼容分支、降级路径或 mock 文案。

## Preconditions

- `fronted/node_modules` 已安装，可执行 `npm`、`eslint`、`next build`、`playwright test`。
- `fronted/playwright.config.ts` 指向的前后端启动命令可在当前工作区启动。
- `backend/data/e2e/production_plan.e2e.db` 与 `backend/data/e2e/backups` 可用于 e2e 运行。
- 若上述任一前置条件缺失，必须停止执行并记录到 `task-state.json.blocking_prereqs`。

## Impacted Areas

- 排产日历页面的“推进一天 / 重置模拟”成功提示链路。
- 当日产能页面的报工数量校验与错误提示链路。
- 前端通用英文消息转中文映射能力。
- 真实浏览器下的文案回归验证与模拟推进回归验证。

## Phase Plan

### P1: 修复当前可见文案与本地化逻辑

- Objective:
  修复当前真实用户流程中仍会暴露英文、内部字段名或不正式提示的前端文案。
- Owned paths:
  `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
  `fronted/src/legacy/features/daily-capacity/useDailyCapacityController.js`
  `fronted/src/legacy/utils/i18n.js`
- Dependencies:
  现有前端 API 封装、排产日历接口、当日产能报工接口。
- Deliverables:
  中文且正式的模拟提示语、中文化的报工校验错误、统一消息翻译辅助逻辑。

### P2: 更新回归用例并完成真实浏览器验证

- Objective:
  让相关 e2e 用例准确校验修复后的中文文案，并验证模拟推进与重置行为没有回归。
- Owned paths:
  `fronted/tests/e2e/copy-verification.spec.ts`
  `fronted/tests/e2e/simulation-calendar.e2e.spec.ts`
- Dependencies:
  P1 已完成且前后端可通过 Playwright 配置启动。
- Deliverables:
  更新后的 e2e 断言、通过的 lint/build/e2e 结果、可追溯测试证据。

## Phase Acceptance Criteria

### P1

- P1-AC1:
  排产日历页面在“推进一天”和“重置模拟”成功后，前端展示的提示语必须为正式中文；即使后端返回英文 `message`，界面也不能直接展示英文原文。
- P1-AC2:
  当日产能页面提交报工时，若报工数量为空、非数字或小于等于 0，错误提示必须为正式中文，且不能暴露诸如 `report_qty` 之类的内部字段名。
- P1-AC3:
  前端新增或调整的消息翻译逻辑只能转换已知英文消息，不得覆盖原本已经正确显示的中文提示。
- Evidence expectation:
  代码变更记录需指向上述路径；浏览器验证需显示中文提示语；lint/build 无新增错误。

### P2

- P2-AC1:
  文案回归用例需在真实浏览器中覆盖侧边栏、排产看板、当日产能、业务接口验证页与排产日历页的关键中文文案，并通过断言。
- P2-AC2:
  排产日历 e2e 用例需在真实浏览器中连续点击“推进一天”5 次，再点击“重置模拟”，并验证日期推进、提示语语言、以及报工副作用恢复均符合预期。
- P2-AC3:
  `npm --prefix fronted run lint` 与 `npm --prefix fronted run build` 必须通过。
- Evidence expectation:
  `test-report.md` 需引用 Playwright 证据文件与命令结果。

## Done Definition

- P1、P2 均标记为 `completed`。
- P1-AC1 至 P2-AC3 全部具备执行证据。
- 前端相关页面不再向用户展示本次范围内的英文提示、内部字段名或不正式描述。
- `test_status` 为 `passed`，且 `check_completion.py --apply` 校验通过。

## Blocking Conditions

- Playwright 无法启动前端或后端。
- e2e 依赖数据库或备份目录缺失。
- 当前仓库状态发生影响本任务的漂移，导致无法确认文案结果来自本次修改。
- 任何必须依赖后端变更才能完成前端文案修复的情况。
