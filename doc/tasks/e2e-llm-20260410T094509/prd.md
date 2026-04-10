# PRD

- Task ID: `e2e-llm-20260410T094509`
- Created: `2026-04-10T09:45:09`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `针对当前生产排期系统实现一套尽量全面的 E2E 测试，覆盖从重排到报工的完整流程，并加入 LLM 评测判断系统行为是否符合要求。`

## Goal

为当前生产排期系统建立一套可重复执行、使用真实浏览器和真实后端运行时的 E2E 验证体系。该体系必须在隔离 SQLite 数据库上运行，覆盖排产员与车间主任两个角色，至少完整验证一次“重排 -> 发布 -> 当日产能维护 -> 产能审计 -> 报工 -> 订单汇总”的业务闭环，并在浏览器证据基础上增加一次 LLM 评测，给出是否符合系统要求的机器可读结论。

## Scope

- `backend/scripts/seed_e2e_db.py`：创建独立 E2E SQLite 数据库并写入确定性测试数据。
- `fronted` 下的 Playwright 配置、E2E 测试用例、测试辅助脚本、测试数据常量、浏览器证据输出。
- 为稳定自动化而添加的前端 `data-testid`、轻量运行辅助逻辑或测试可观测性增强。
- LLM 评测脚本与完整测试入口，要求浏览器执行结果和结构化证据能被 Codex CLI 消费。
- `doc/tasks/e2e-llm-20260410T094509/*` 任务工件与执行/测试证据更新。

## Non-Goals

- 不重构现有业务流程或替换当前 React 壳。
- 不修改用户已有未提交业务数据或复用现有生产/开发 SQLite 数据库作为测试库。
- 不引入 mock 服务、假成功返回、兼容性兜底或静默降级。
- 不覆盖 ERP 联调、导入脚本或与本任务无关的历史页面修复。

## Preconditions

- 可用的 `python`、`node`、`npm` 运行环境。
- `backend/requirements.txt` 依赖已安装，`fronted/node_modules` 可用。
- Playwright Chromium 浏览器已安装，或可通过 `npx playwright install chromium` 安装。
- 测试运行时可占用 `127.0.0.1:2798`（前端）和 `127.0.0.1:8000`（后端）。
- 允许在仓库内创建独立 E2E SQLite 文件，且测试只允许指向该隔离数据库。
- 执行完整 `LLM` 评测时必须使用本机可直接执行的 `codex` CLI 与当前本机有效登录态/配置；`evaluate.mjs` 直接复用当前 `codex login status` 所对应的本地配置，不依赖 `OPENAI_API_KEY` 或 `OPENAI_MODEL`。
- 若以上任一前置条件缺失，必须停止执行并记录到 `task-state.json.blocking_prereqs`。

## Impacted Areas

- 前端认证与导航：`fronted/src/legacy/App.jsx`、`fronted/src/legacy/auth/*`
- 排产日历：`fronted/src/legacy/pages/ScheduleCalendarPage.jsx`、`fronted/src/legacy/features/schedule-calendar/*`
- 当日产能与审计：`fronted/src/legacy/pages/DailyCapacityPage.jsx`、`DailyCapacityAuditPage.jsx`、`fronted/src/legacy/features/daily-capacity/*`
- 报工：`fronted/src/legacy/pages/ExecutionWipPage.jsx`、`fronted/src/legacy/features/execution-wip/*`
- 订单汇总与生产订单：`fronted/src/legacy/pages/OrderSummaryPage.jsx`、`OrdersPoolPage.jsx`、相关 controller/service
- 后端鉴权、异步 job、排产、报工、当日产能与订单汇总：`backend/app/auth.py`、`backend/app/api/routes/*`、`backend/app/services/app_service.py`、`backend/app/services/line_daily_capacity_service.py`
- 任务工件：`doc/tasks/e2e-llm-20260410T094509/*`

## Phase Plan

### P1: 隔离运行时与确定性数据基线

- Objective: 提供一个不会污染当前业务库的独立 E2E 数据库与固定账号/产线/订单/工序数据，使重排、发布、产能维护、报工和汇总都能在同一数据集中真实执行。
- Owned paths:
  - `backend/scripts/seed_e2e_db.py`
  - `backend/data/e2e/`
  - 如有必要的前端/后端启动辅助脚本
- Dependencies:
  - `backend/sqlite/001_init.sql`
  - `backend/app/db.py`
  - `backend/app/auth.py`
  - `backend/app/services/app_service.py`
  - `backend/app/services/line_daily_capacity_service.py`
- Deliverables:
  - 可重复创建/覆盖的 E2E SQLite 种子脚本
  - 固定账号、权限、产线拓扑、工艺路线、订单和初始业务状态
  - 可被 Playwright `webServer` 使用的固定运行约定

### P2: 真实浏览器 E2E 覆盖

- Objective: 基于真实前后端运行时实现浏览器 E2E，用例覆盖排产员与车间主任核心路径，并至少跑通一次“重排到报工”的完整链路。
- Owned paths:
  - `fronted/playwright.config.*`
  - `fronted/tests/e2e/**`
  - `fronted/src/legacy/**` 中为自动化稳定性增加的最小可观测性改动
- Dependencies:
  - P1 生成的隔离数据库与启动约定
  - `fronted/package.json`
  - `fronted/src/legacy/pages/*`
  - `fronted/src/legacy/features/*`
- Deliverables:
  - Playwright 配置与测试辅助工具
  - 排产员/车间主任真实浏览器用例
  - 非任务工件证据文件（截图、trace、JSON 证据）

### P3: LLM 评测接入

- Objective: 在浏览器执行完成后，使用结构化证据和系统要求通过 Codex CLI 做独立评测，并输出机器可读结论。
- Owned paths:
  - `fronted/scripts/run-e2e.mjs`
  - `fronted/tests/e2e/llm/**`
  - `fronted/tests/e2e/results/**`
- Dependencies:
  - P2 产出的结构化浏览器证据
  - 可执行的 `codex` CLI
  - 当前本机 `codex login status` 可用，且 provider 能完成真实结构化评测请求
- Deliverables:
  - 严格校验 Codex ChatGPT 鉴权状态的 LLM 评测器
  - 浏览器结果 + LLM 评测的统一入口命令
  - 机器可读评测结果文件与 Codex 执行日志

### P4: 证据归档与交付闭环

- Objective: 以 workflow 要求更新执行记录、测试报告与任务状态，使每个 acceptance id 都有代码和测试证据可追踪。
- Owned paths:
  - `doc/tasks/e2e-llm-20260410T094509/execution-log.md`
  - `doc/tasks/e2e-llm-20260410T094509/test-report.md`
  - `doc/tasks/e2e-llm-20260410T094509/task-state.json`
- Dependencies:
  - P1-P3 的实现与运行证据
  - spec-driven-delivery workflow scripts
- Deliverables:
  - reviewed execution log
  - reviewed test report
  - completion gate 所需状态更新与证据引用

## Phase Acceptance Criteria

### P1

- P1-AC1: `seed_e2e_db.py` 每次运行都生成一份独立的 SQLite E2E 数据库，不读取或覆盖用户当前业务数据库。
- P1-AC2: 种子数据至少包含 1 个排产员账号、1 个车间主任账号、车间主任产线权限、可用于排产的工艺路线/产线拓扑/订单/能力绑定/订单状态数据。
- P1-AC3: 用种子库启动系统后，可以真实执行排产生成、发布、当日产能保存、产能审计查询、报工和订单汇总查询。
- Evidence expectation: 种子脚本命令输出、数据库断言、隔离库路径、运行时健康检查。

### P2

- P2-AC1: Playwright E2E 至少有一个排产员用例完整覆盖“登录 -> 重排生成草稿 -> 发布草稿 -> 修改当日产能 -> 查看产能审计 -> 报工 -> 在订单汇总中看到结果”。
- P2-AC2: E2E 还要覆盖相邻高价值页面和角色约束，至少包括生产订单页、报工页、订单汇总页、车间主任可见产线/报工范围。
- P2-AC3: 每个通过的浏览器用例都输出至少一个真实证据文件，并写入结构化证据清单供后续 LLM 评测消费。
- Evidence expectation: Playwright 报告、截图、trace、结构化 evidence manifest。

### P3

- P3-AC1: `npm run e2e` 或等价主入口必须先跑浏览器测试，再跑 Codex LLM 评测；若本机 Codex 登录态不可用，或当前 provider 无法完成真实评测请求（例如连续 `503 Service Unavailable`），必须明确失败，不能跳过。
- P3-AC2: LLM 评测输入必须包含系统要求、关键业务断言和浏览器证据摘要，输出必须是机器可读 verdict，并能据此决定整套 E2E 成败。
- Evidence expectation: 评测请求输入摘要、LLM verdict JSON、主入口命令日志。

### P4

- P4-AC1: `execution-log.md`、`test-report.md` 和 `task-state.json` 对每个 acceptance id 都有对应证据引用和状态更新。
- P4-AC2: 只有在浏览器 E2E 与 LLM 评测都通过后，任务才允许进入 completion gate；否则保留明确失败或阻塞原因。
- Evidence expectation: workflow 脚本输出、任务工件中的 evidence refs、completion check 结果。

## Done Definition

- P1-P4 全部完成，且所有 acceptance id 状态为 `completed`。
- 真实浏览器 E2E 通过，证据文件存在且可追踪。
- LLM 评测返回 `pass` 级别结论，且没有 unresolved blocker。
- `test-report.md` 通过结构校验，`check_completion.py --apply` 成功。
- 全部改动保持当前前端壳不变，仅做测试所需最小增强。

## Blocking Conditions

- `codex` CLI 不可用，或本机 `codex login status` 不可用，导致无法执行完整 LLM 评测。
- 当前本机 Codex 所配置的 provider 返回持续性 `503 Service Unavailable` / `No available providers`，导致无法生成 LLM verdict。
- Playwright 浏览器无法安装或本机端口被占用，导致真实浏览器环境无法启动。
- 隔离数据库未能初始化，或排产/报工所需主数据不足导致关键链路不可执行。
- 任何步骤需要 mock、默认成功、兼容性兜底或静默跳过才能继续。
