# PRD

- Task ID: `task-61cb339d1c-20260419T011916`
- Created: `2026-04-19T01:19:16`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `重构代码，按自上向下方式重新模块化，降低模块耦合度，优先梳理后端聚合服务和前端应用壳层的职责边界`

## Goal

在不改变现有核心业务入口和主要调用契约的前提下，完成一轮可落地的顶层模块化重构：把后端遗留聚合服务的创建入口与依赖装配从业务实现中抽离出来，把前端 legacy 应用壳层拆成更清晰的导航、权限守卫、侧栏和路由装配模块，为后续继续拆分 `AppService` 建立稳定骨架。

## Scope

- 后端 legacy 聚合服务的组合根与统一 provider。
- `AppService` 的依赖装配显式化。
- `app_queries.py`、`job_dispatcher.py`、相关脚本统一通过 provider 获取 legacy 服务实例。
- 前端 `fronted/src/legacy/App.jsx` 的应用壳层模块化拆分。
- 与以上改动直接相关的定向测试、静态检查和任务工件。

## Non-Goals

- 不在本任务内一次性拆完 `backend/app/services/app_service.py` 全部业务逻辑。
- 不重写排产算法、报工流程、主数据流程或数据库结构。
- 不迁移 legacy 页面到 Next App Router 原生页面体系。
- 不引入 fallback、兼容分支、mock 数据或静默降级。

## Preconditions

- 本地 Python 环境可执行仓库后端测试命令。
- 本地 Node.js 依赖已安装，可执行前端 lint。
- 工作区中的现有代码和测试夹具可读。
- 若任一前置条件缺失，必须停止执行并记录到 `task-state.json.blocking_prereqs`。

## Impacted Areas

- `backend/app/services/app_service.py`
- `backend/app/services/legacy_runtime.py`
- `backend/app/services/app_service_provider.py`
- `backend/app/services/job_dispatcher.py`
- `backend/app/api/routes/app_queries.py`
- `backend/scripts/import_mes_reportings_xlsx.py`
- `backend/scripts/import_balloon_daily_output.py`
- `backend/tests/test_app_service_provider.py`
- `fronted/src/legacy/App.jsx`
- `fronted/src/legacy/app-shell/*`
- `fronted/src/components/legacy-app-page.tsx`
- `fronted/src/app/[[...slug]]/page.tsx`

## Phase Plan

### P1: 后端 Legacy App 组合根收口

- Objective: 建立单一 provider 和 runtime 容器，让 API 路由、任务分发器和脚本不再各自直连 `AppService(connection)` 的构造细节。
- Owned paths:
  - `backend/app/services/app_service.py`
  - `backend/app/services/legacy_runtime.py`
  - `backend/app/services/app_service_provider.py`
  - `backend/app/services/job_dispatcher.py`
  - `backend/app/api/routes/app_queries.py`
  - `backend/scripts/`
- Dependencies:
  - 现有 `ServiceFactory`
  - 现有 `LineDailyCapacityService`
  - 现有 legacy 业务方法契约
- Deliverables:
  - runtime 容器
  - app service provider
  - 统一后的服务获取入口

### P2: 前端 Legacy 应用壳层拆分

- Objective: 将 `fronted/src/legacy/App.jsx` 中的导航配置、权限守卫、侧边栏和路由装配拆到 `fronted/src/legacy/app-shell/`，让 `App.jsx` 仅保留认证分流和总装配。
- Owned paths:
  - `fronted/src/legacy/App.jsx`
  - `fronted/src/legacy/app-shell/`
  - `fronted/src/components/legacy-app-page.tsx`
  - `fronted/src/app/[[...slug]]/page.tsx`
- Dependencies:
  - 现有 `AuthContext`
  - 现有 legacy page components
  - 现有 React Router 路径
- Deliverables:
  - 独立的导航配置模块
  - 独立的权限守卫模块
  - 独立的侧栏和路由装配模块
  - 更薄的 `App.jsx`

### P3: 回归验证与工件闭环

- Objective: 用与改动范围匹配的后端定向测试和前端静态检查验证这次模块化重构没有打断已有入口，并补齐执行/测试证据。
- Owned paths:
  - `backend/tests/test_app_service_provider.py`
  - `backend/tests/test_app_service_process_timeline.py`
  - `backend/tests/test_app_service_schedule_trust.py`
  - `backend/tests/test_app_service_batch_dispatch.py`
  - `fronted/package.json`
  - `doc/tasks/task-61cb339d1c-20260419T011916/`
- Dependencies:
  - P1、P2 已完成
  - 可运行的本地测试命令
- Deliverables:
  - 通过的后端定向测试记录
  - 通过的前端 lint 记录
  - `execution-log.md` 与 `test-report.md`

## Phase Acceptance Criteria

### P1

- P1-AC1: 后端新增统一的 legacy app provider，`app_queries.py`、`job_dispatcher.py` 和相关脚本通过该 provider 获取服务实例。
- P1-AC2: `AppService` 的依赖装配被抽离为显式 runtime 容器，构造函数支持显式注入并保留现有业务调用方式。
- P1-AC3: provider 与 runtime 的新增测试通过，验证默认构造和显式注入均可用。
- Evidence expectation: 代码 diff、`backend/tests/test_app_service_provider.py`、`execution-log.md#Phase-P1`

### P2

- P2-AC1: `fronted/src/legacy/App.jsx` 降为薄入口，不再内联导航配置、守卫实现和完整路由表。
- P2-AC2: `fronted/src/legacy/app-shell/` 至少包含导航配置、权限守卫、侧栏和路由装配模块，并通过显式导出协作。
- P2-AC3: `legacy-app-page.tsx` 与 Next catch-all 入口仍保持 legacy 应用的宿主职责，不引入新的页面回退逻辑。
- Evidence expectation: 代码 diff、`npm run lint`、`execution-log.md#Phase-P2`

### P3

- P3-AC1: 与后端入口重构直接相关的定向测试通过，确认 provider/runtime/dispatch 路径可用。
- P3-AC2: 前端 lint 通过，确认壳层拆分后的模块导入、JSX 语法和路由装配有效。
- P3-AC3: `execution-log.md` 与 `test-report.md` 记录了每个 acceptance id 的证据，且没有未解释的失败或跳过项。
- Evidence expectation: 命令输出摘要、`test-report.md`、completion check

## Done Definition

- P1、P2、P3 全部完成并被记录为通过。
- 每个 acceptance id 都有执行证据和测试证据。
- 后端 provider/runtime 收口完成，前端 legacy 壳层拆分完成，现有公开入口保持稳定。
- 没有引入 fallback、mock、silent downgrade 或未记录的兼容分支。

## Blocking Conditions

- Python 或 Node 运行前置条件缺失，导致无法执行本任务要求的验证命令。
- 工作区存在直接阻断本次重构的未解析冲突或关键文件不可读。
- 发现需要为了保持通过而引入隐式兼容层、默认成功值或 silent fallback 时，必须停止并报告。
