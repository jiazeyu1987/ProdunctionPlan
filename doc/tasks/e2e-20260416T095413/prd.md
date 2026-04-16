# PRD

- Task ID: `e2e-20260416T095413`
- Created: `2026-04-16T09:54:13`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `补全缺失的E2E测试用例`

## Goal

补齐当前仓库中最明显且可在本地真实运行的 E2E 缺口，使 `/schedule/lite` 与 `/test` 两个现有未覆盖页面具备可回归的 Playwright 用例，并把新增覆盖纳入仓库现有 E2E 运行方式与证据产物体系。

## Scope

- 为 `fronted/tests/e2e` 新增或扩展 Playwright 用例，覆盖：
- `fronted/src/legacy/pages/LiteSchedulerPage.jsx` 对应的 `/schedule/lite`
- `fronted/src/legacy/pages/TestToolsPage.jsx` 对应的 `/test`
- 复用现有登录、证据采集、Playwright 配置与报告目录：
- `fronted/tests/e2e/support/*`
- `fronted/playwright.config.ts`
- `fronted/package.json`
- 如为提升稳定性必须补少量页面级 `data-testid`，变更范围仅限上述两个页面及其直连组件。
- 更新任务工件与执行/测试证据：
- `doc/tasks/e2e-20260416T095413/execution-log.md`
- `doc/tasks/e2e-20260416T095413/test-report.md`

## Non-Goals

- 不把本任务扩展为所有未覆盖路由的全面 E2E 补齐。
- 不引入对真实 ERP、K3、外部库存系统的端到端集成覆盖承诺。
- 不为生产代码增加 fallback、mock 分支、兼容分支或静默降级。
- 不重构现有 Playwright 基础设施、认证流程或历史 E2E 用例。
- 不修复与新增覆盖无关的前端乱码、文案或业务逻辑问题。

## Preconditions

- 本地已安装 Node.js、npm、Python，且仓库依赖已安装完成。
- `fronted/node_modules` 可用，`@playwright/test` 已安装。
- `npm --prefix fronted run e2e:playwright` 可在本机启动前后端联跑。
- 后端 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` 可正常启动。
- 前端 `npm run dev` 可在 `http://127.0.0.1:2798` 启动。
- 现有 E2E 账号仍可用：
- `scheduler_e2e / Passw0rd!`
- `manager_e2e / Passw0rd!`
- `/schedule/lite` 的场景与快照依赖浏览器 `localStorage`，运行前应允许测试清理同源存储。
- `/test` 页面的本地校验路径必须无需真实外部 ERP 凭据；若页面核心行为只能依赖外部系统，则该前提缺失时必须 fail fast 并记录到 `task-state.json.blocking_prereqs`。

## Impacted Areas

- Playwright 测试入口与报告：
- `fronted/package.json`
- `fronted/playwright.config.ts`
- `fronted/test-results/`
- 现有 E2E 辅助：
- `fronted/tests/e2e/support/evidence.ts`
- `fronted/tests/e2e/support/ui.ts`
- `fronted/tests/e2e/support/constants.ts`
- 轻量排产本地状态与交互：
- `fronted/src/legacy/features/lite-scheduler/useLiteSchedulerPageController.js`
- `fronted/src/legacy/features/lite-scheduler/useLiteSnapshotManager.js`
- `fronted/src/legacy/features/lite-scheduler/storage.js`
- 测试工具页的 tab 与输入校验：
- `fronted/src/legacy/pages/TestToolsPage.jsx`
- 邻近回归面：
- 既有 `/schedule/calendar`、`/orders/pool`、`/dashboard/scheduler` E2E 不应被破坏。

## Phase Plan

### P1: 设计并补齐轻量排产 E2E

- Objective: 为 `/schedule/lite` 增加一个真实浏览器主流程用例，验证页面可达、关键操作可执行、浏览器本地状态可持久化与恢复。
- Owned paths:
- `fronted/tests/e2e/lite-scheduler.e2e.spec.ts`
- `fronted/src/legacy/pages/LiteSchedulerPage.jsx`
- `fronted/src/legacy/features/lite-scheduler/*`
- Dependencies:
- 现有 Playwright 登录辅助
- Lite Scheduler 现有 `localStorage` 存储实现
- Deliverables:
- 至少 1 条覆盖 `/schedule/lite` 的 Playwright 用例
- 必要的最小页面定位点补充
- 执行证据记录到 `execution-log.md`

### P2: 补齐测试工具页 E2E

- Objective: 为 `/test` 增加真实浏览器页面级 E2E，覆盖 tab 可达性、路由可访问性以及无需外部系统的本地校验行为。
- Owned paths:
- `fronted/tests/e2e/test-tools.e2e.spec.ts`
- `fronted/src/legacy/pages/TestToolsPage.jsx`
- Dependencies:
- 现有 Playwright 登录辅助
- `/test` 页现有前端输入校验逻辑
- Deliverables:
- 至少 1 条覆盖 `/test` 的 Playwright 用例
- 必要的最小页面定位点补充
- 执行证据记录到 `execution-log.md`

### P3: 回归执行与证据收口

- Objective: 运行新增用例与相邻回归命令，确认新增覆盖接入现有报告体系并形成可审计证据。
- Owned paths:
- `doc/tasks/e2e-20260416T095413/execution-log.md`
- `doc/tasks/e2e-20260416T095413/test-report.md`
- Dependencies:
- P1、P2 完成
- Playwright 可在本地生成截图、trace、HTML report
- Deliverables:
- 新增用例运行记录
- 相邻回归命令结果
- 完整测试证据引用

## Phase Acceptance Criteria

### P1

- P1-AC1: 调度员登录后可进入 `/schedule/lite`，且页面渲染出轻量排产工具栏与四个主 tab。
- P1-AC2: 用例可在真实浏览器中完成至少一条关键操作链，覆盖以下行为中的最少三项：切换排产模式、打开新增订单弹窗、保存场景快照、读取场景快照、推进一天、重置场景。
- P1-AC3: 用例必须验证 `localStorage` 持久化结果与 UI 状态一致，不能只做点击不校验副作用。
- Evidence expectation: Playwright trace、截图、`execution-log.md` 中的 P1 记录。

### P2

- P2-AC1: 调度员登录后可进入 `/test`，并能看到四个业务接口验证 tab。
- P2-AC2: 用例必须验证 tab 切换行为真实生效，而不是仅检查按钮存在。
- P2-AC3: 用例必须覆盖至少两个无需外部系统的本地输入校验分支，并确认页面展示明确错误提示或空态，不伪造真实 ERP 成功链路。
- Evidence expectation: Playwright trace、截图、`execution-log.md` 中的 P2 记录。

### P3

- P3-AC1: 新增 spec 可通过仓库现有 Playwright 命令独立运行并返回退出码 0。
- P3-AC2: 至少执行一条相邻回归命令，证明新增改动未破坏既有关键 E2E 入口。
- P3-AC3: `execution-log.md` 与 `test-report.md` 记录新增用例、执行命令、结果、风险与证据文件路径。
- Evidence expectation: `fronted/test-results/` 下的截图/trace/report 产物，以及任务工件中的命令与结果记录。

## Done Definition

- P1、P2、P3 全部完成并通过主代理 review gate。
- 每个 acceptance id 都有对应代码改动与证据引用。
- `/schedule/lite` 与 `/test` 各至少新增一条 Playwright E2E 用例。
- 新增用例纳入仓库现有运行方式，不需要额外私有脚本或手工步骤。
- 独立测试阶段给出通过结论，且 `test-report.md` 通过结构校验。

## Blocking Conditions

- Playwright、Node、Python、仓库依赖或前后端启动链路缺失。
- E2E 登录账号不可用，导致无法进入受保护页面。
- `/test` 页若其最小可验证行为也依赖不可获得的外部系统且不存在本地可验证分支。
- 新增覆盖若必须依赖 mock、fallback、静默忽略错误才能通过，则必须停止而不是继续实现。
