# PRD

- Task ID: `prd-20260420T000918`
- Created: `2026-04-20T00:09:18`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `查看当前系统是否需要重构，如果需要则在保持前端界面不变的前提下，整理自上而下模块化、低耦合重构方案并写入 PRD`

## Goal

本次评估结论是：当前系统需要重构，但应采用“前端界面不变、接口契约尽量不变、从入口层到领域能力层逐层拆分”的渐进式重构方案，而不是推倒重写。

需要重构的主要依据如下：

- 后端存在超大核心服务：[backend/app/services/app_service.py](D:\ProjectPackage\ProductionPlan\backend\app\services\app_service.py) 约 313 KB，包含约 183 个 `def`，承担排产、主数据、订单池、报工、仿真、导入等多类职责。
- 后端命令入口仍明显依赖 `AppService` 聚合处理，[backend/app/api/routes/commands.py](D:\ProjectPackage\ProductionPlan\backend\app\api\routes\commands.py) 与 [backend/app/services/job_dispatcher.py](D:\ProjectPackage\ProductionPlan\backend\app\services\job_dispatcher.py) 中仍存在多条 `LEGACY_*` 分发链路。
- 前端页面壳层较薄，但控制器过大，[fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js](D:\ProjectPackage\ProductionPlan\fronted\src\legacy\features\orders-pool\page\useOrdersPoolPageController.js) 约 1573 行，承担查询、筛选、分页、批量命令、乐观更新、物料树、URL 状态等复合职责。
- 前端已出现“新壳包旧核”的过渡结构：[fronted/src/app/[[...slug]]/page.tsx](D:\ProjectPackage\ProductionPlan\fronted\src\app\[[...slug]]\page.tsx) 通过 Next 页面桥接 [fronted/src/components/legacy-app-page.tsx](D:\ProjectPackage\ProductionPlan\fronted\src\components\legacy-app-page.tsx) 与 legacy React Router 应用，说明当前架构适合增量迁移。
- 查询侧已经开始分层，[backend/app/api/routes/app_queries.py](D:\ProjectPackage\ProductionPlan\backend\app\api\routes\app_queries.py) 使用 facade/provider 组合，但命令侧仍未完成同等级拆分，系统整体分层不一致。

本 PRD 的目标是形成一套可执行的模块化重构蓝图，要求保持现有前端页面布局、交互入口、API 对外契约和业务行为基线不发生无意变化。

## Scope

本次重构规划范围包括：

- 后端入口层：`backend/app/main.py`、`backend/app/api/router.py`、`backend/app/api/routes/*.py`
- 后端应用服务层：`backend/app/services/app_service.py`、`backend/app/services/job_dispatcher.py`、`backend/app/services/*_command_service.py`
- 后端运行时和装配层：`backend/app/services/app_service_provider.py`、`backend/app/services/legacy_runtime.py`
- 后端查询 facade/provider 与既有仓储、gateway 的对齐方式
- 前端应用壳层与路由桥接：`fronted/src/app/**`、`fronted/src/components/legacy-app-page.tsx`、`fronted/src/legacy/app-shell/**`
- 前端 feature 控制器层：订单池、排程日历、主数据、轻排产、执行看板等 `use*Controller` / `page controller` 文件
- 前端共享调用层：`fronted/src/legacy/shared/api/**`、各 feature `queryClient` / `commandClient` / `service` 文件
- 现有测试资产与回归边界：`backend/tests/**`、`fronted/tests/e2e/**`

## Non-Goals

- 不修改现有前端页面视觉样式、页面布局、导航结构和主要交互路径。
- 不在本阶段新增业务功能、字段、报表口径或角色权限策略。
- 不主动改动对外 API 路径、请求字段、响应字段，除非 PRD 后续执行阶段先建立兼容契约并经确认。
- 不引入 fallback、兼容分支、静默降级或 mock 行为来掩盖重构风险。
- 不在本次 PRD 中直接替换数据库、框架或部署方式。

## Preconditions

执行该 PRD 后续阶段前，需要满足以下前置条件：

- 可读取并运行当前仓库代码，工作目录为 `D:\ProjectPackage\ProductionPlan`
- Python 运行环境可用，且能够执行 `backend/tests/**` 中的 pytest/unittest 测试
- Node.js 与 `fronted/package-lock.json` 对应依赖可安装并执行 `npm run lint`、`npm run e2e:playwright`
- Playwright 浏览器依赖已安装，可运行真实浏览器回归
- SQLite 数据库初始化链路可用，至少可支撑后端单测与查询 facade 验证
- 排产、订单池、主数据相关现有接口契约可被读取和比对
- 若后续执行阶段需要联调，必须具备可登录系统的真实账号和必要角色

若任一前置条件缺失，必须停止执行并在 `task-state.json.blocking_prereqs` 中记录，不允许以 fallback 或跳过验证代替。

## Impacted Areas

可能受影响的入口、调用链、契约与验证点如下：

- 后端应用聚合根：[backend/app/services/app_service.py](D:\ProjectPackage\ProductionPlan\backend\app\services\app_service.py)
- 后端命令入口：[backend/app/api/routes/commands.py](D:\ProjectPackage\ProductionPlan\backend\app\api\routes\commands.py)
- 后端查询入口：[backend/app/api/routes/app_queries.py](D:\ProjectPackage\ProductionPlan\backend\app\api\routes\app_queries.py)
- 作业分发与运行时装配：[backend/app/services/job_dispatcher.py](D:\ProjectPackage\ProductionPlan\backend\app\services\job_dispatcher.py), [backend/app/services/legacy_runtime.py](D:\ProjectPackage\ProductionPlan\backend\app\services\legacy_runtime.py), [backend/app/services/app_service_provider.py](D:\ProjectPackage\ProductionPlan\backend\app\services\app_service_provider.py)
- 订单池前端控制器与页面：[fronted/src/legacy/pages/OrdersPoolPage.jsx](D:\ProjectPackage\ProductionPlan\fronted\src\legacy\pages\OrdersPoolPage.jsx), [fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js](D:\ProjectPackage\ProductionPlan\fronted\src\legacy\features\orders-pool\page\useOrdersPoolPageController.js)
- 排程日历控制器：[fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js](D:\ProjectPackage\ProductionPlan\fronted\src\legacy\features\schedule-calendar\useScheduleCalendarController.js)
- 主数据 feature 服务与引导：[fronted/src/legacy/features/masterdata/service.js](D:\ProjectPackage\ProductionPlan\fronted\src\legacy\features\masterdata\service.js), [fronted/src/legacy/features/masterdata/page/useMasterdataBootstrap.js](D:\ProjectPackage\ProductionPlan\fronted\src\legacy\features\masterdata\page\useMasterdataBootstrap.js)
- 前端桥接入口：[fronted/src/app/[[...slug]]/page.tsx](D:\ProjectPackage\ProductionPlan\fronted\src\app\[[...slug]]\page.tsx), [fronted/src/components/legacy-app-page.tsx](D:\ProjectPackage\ProductionPlan\fronted\src\components\legacy-app-page.tsx)
- 现有回归资产：[backend/tests/test_app_service_provider.py](D:\ProjectPackage\ProductionPlan\backend\tests\test_app_service_provider.py), [backend/tests/test_app_queries_order_pool_facade.py](D:\ProjectPackage\ProductionPlan\backend\tests\test_app_queries_order_pool_facade.py), [backend/tests/test_app_queries_schedule_summary_dashboard_facades.py](D:\ProjectPackage\ProductionPlan\backend\tests\test_app_queries_schedule_summary_dashboard_facades.py), [fronted/tests/e2e/production-plan.e2e.spec.ts](D:\ProjectPackage\ProductionPlan\fronted\tests\e2e\production-plan.e2e.spec.ts), [fronted/tests/e2e/lite-scheduler.e2e.spec.ts](D:\ProjectPackage\ProductionPlan\fronted\tests\e2e\lite-scheduler.e2e.spec.ts)

## Phase Plan

### P1: 建立分层重构基线与边界契约

- Objective:
  明确系统的入口层、应用编排层、领域能力层、基础设施层边界，冻结“前端界面不变、API 契约不随意变化”的重构约束，并为后续拆分建立目标模块图。
- Owned paths:
  `backend/app/api/**`, `backend/app/services/app_service.py`, `backend/app/services/job_dispatcher.py`, `fronted/src/app/**`, `fronted/src/components/**`, `fronted/src/legacy/app-shell/**`, `fronted/src/legacy/pages/**`
- Dependencies:
  当前 API 路由、前端页面入口、角色权限与现有测试清单
- Deliverables:
  目标分层说明、模块职责矩阵、禁止变更清单、迁移顺序说明

### P2: 后端按业务域拆分命令编排，收缩 AppService

- Objective:
  将 `AppService` 从“大一统应用服务”重构为按业务域划分的应用编排器，至少形成订单池、排程、主数据、报工/执行、测试工具等清晰边界，并让命令入口与 JobDispatcher 面向显式服务接口而不是继续堆叠 `LEGACY_*` 分支。
- Owned paths:
  `backend/app/services/app_service.py`, `backend/app/services/job_dispatcher.py`, `backend/app/services/*_command_service.py`, `backend/app/services/*_provider.py`, `backend/app/api/routes/commands.py`
- Dependencies:
  P1 输出的边界契约；现有 facade/provider 组织方式；仓储和 gateway 现状
- Deliverables:
  新的后端模块划分方案、候选服务清单、命令路由到应用服务的映射规则、迁移优先级

### P3: 前端在不改界面的前提下拆分 page controller

- Objective:
  保留现有页面 JSX、样式类名、路由与可见交互，将超大 controller 拆成查询 hook、命令 hook、筛选/选择状态 hook、URL 状态同步 hook、派生 view-model 计算模块与纯工具模块，降低页面与业务逻辑耦合。
- Owned paths:
  `fronted/src/legacy/features/orders-pool/**`, `fronted/src/legacy/features/schedule-calendar/**`, `fronted/src/legacy/features/masterdata/**`, `fronted/src/legacy/features/lite-scheduler/**`, `fronted/src/legacy/features/execution-wip/**`
- Dependencies:
  P1 的页面不变约束；P2 的后端契约稳定面；现有 `queryClient` / `commandClient` / `service` 文件
- Deliverables:
  前端控制器拆分策略、共享 API 调用边界、页面保形清单、模块目录建议

### P4: 建立分阶段回归与验收机制

- Objective:
  在每次模块迁移后用后端单测、API 契约验证与前端真实浏览器回归确认行为不变，确保重构是“低耦合迁移”而不是“功能重写”。
- Owned paths:
  `backend/tests/**`, `fronted/tests/e2e/**`, `fronted/playwright.config.ts`, `doc/tasks/prd-20260420T000918/**`
- Dependencies:
  P1-P3 输出的接受标准和模块边界
- Deliverables:
  分层回归矩阵、关键冒烟清单、执行顺序与放行规则

## Phase Acceptance Criteria

### P1

- P1-AC1: 明确给出当前系统“需要重构”的结论，并用代码现状证明耦合点主要集中在后端 `AppService`、`JobDispatcher` 与前端超大 page controller。
- P1-AC2: 明确前端不变更范围，包括页面布局、样式、路由、导航、主要交互路径和 API 外部契约。
- P1-AC3: 给出目标分层结构，至少包含入口层、应用编排层、领域能力层、基础设施层，并说明各层依赖方向只能自上而下。
- Evidence expectation:
  `prd.md` 中包含代码现状依据、分层定义和禁止变更边界。

### P2

- P2-AC1: 后端重构方案不再允许 `AppService` 持续承载跨域职责，必须给出可拆分的域服务清单。
- P2-AC2: 命令入口与 JobDispatcher 的职责必须被定义为“路由/派发 + 应用服务调用”，而不是继续扩散业务细节。
- P2-AC3: 查询侧已有 facade/provider 模式要被保留并作为命令侧重构参考，不允许回退为更粗粒度耦合结构。
- Evidence expectation:
  `prd.md` 中明确列出候选后端模块、职责、调用边界和迁移顺序。

### P3

- P3-AC1: 前端 Orders Pool、Schedule Calendar 等超大 controller 必须拆为多个职责单一的 hook 或纯函数模块，页面组件接口保持稳定。
- P3-AC2: 共享 API 调用必须下沉到 feature service 或 shared api 层，页面与大型 controller 不再直接混合查询、命令、派生计算和持久化逻辑。
- P3-AC3: 拆分方案必须保证 JSX 结构、CSS 类名和用户可见文案不因重构被意外改写。
- Evidence expectation:
  `prd.md` 中明确列出前端拆分单元、保形约束和目录级迁移策略。

### P4

- P4-AC1: 每个阶段都要定义最小可验证回归集，覆盖后端契约、前端页面冒烟和关键业务流。
- P4-AC2: UI 验证必须使用真实浏览器，不允许仅依赖静态阅读或假定页面未变。
- P4-AC3: 若任一重构步骤导致接口或页面行为偏离现状，必须阻塞继续执行，而不是加 fallback 掩盖差异。
- Evidence expectation:
  `test-plan.md` 覆盖全部 acceptance id，并定义真实浏览器与后端测试命令。

## Done Definition

本任务完成的定义如下：

- 已在 PRD 中明确判断当前系统需要重构，并说明原因
- 已给出自上而下、低耦合、可分阶段执行的重构方案
- 已明确前端界面不变、API 契约尽量稳定、禁止 fallback 的约束
- 每个阶段都有稳定 phase id 与 acceptance id
- `test-plan.md` 已覆盖所有 acceptance id，并为后续执行提供独立验证路径
- 后续执行阶段只有在每个 phase 的验收标准和回归证据都满足时才可继续

## Blocking Conditions

以下情况必须阻塞后续执行，不允许用 fallback、mock、静默降级或跳过验证替代：

- 无法确认现有页面结构、API 契约或关键业务行为基线
- 后端测试环境不可运行，导致无法验证 `AppService` 拆分是否保持行为一致
- Playwright 或真实浏览器环境不可用，导致无法确认“前端界面不变”
- 发现某一模块实际上承担跨域副作用，但调用链与数据契约未梳理清楚
- 拆分过程需要改动接口或页面行为，但尚未形成显式迁移契约与用户确认
