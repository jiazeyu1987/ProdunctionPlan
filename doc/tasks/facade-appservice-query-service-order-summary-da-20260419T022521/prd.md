# PRD

- Task ID: `facade-appservice-query-service-order-summary-da-20260419T022521`
- Created: `2026-04-19T02:25:21`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `继续模块化重构：将 facade 之下的查询实现从 AppService 内部下沉到独立 query service，优先处理 order-summary 与 dashboard 查询域，降低单体内部耦合`

## Goal

在已经完成路由层 facade 拆分的前提下，继续把查询实现从 `AppService` 内部下沉到独立 query service。首轮内部下沉以 `schedules` 为真下沉域，同时为 `order-summary` 与 `dashboard` 建立明确的 service 层承载骨架，减少后续继续拆分时对单体公开方法的直接依赖。

## Scope

- 新增 `schedules_query_service.py`，承接：
  - `get_current_schedule`
  - `list_current_schedule_tasks`
  - `list_schedule_snapshots`
- `AppService` 中上述 3 个公开方法改为委托到 `SchedulesQueryService`。
- `SchedulesQueryFacade` 改为依赖 `SchedulesQueryService`。
- 为 `order-summary` 与 `dashboard` 新增内部 query service 层骨架，并让对应 facade 依赖 service，而不是直接依赖 `AppService`。
- 调整相关 facade/provider 测试。

## Non-Goals

- 本轮不把 `order-summary` 与 `dashboard` 的完整实现体全部搬出 `AppService`。
- 不改写底层 SQL、权限规则和返回结构。
- 不改动命令接口、worker 和排产生成逻辑。
- 不引入 fallback service 或兼容双路径。

## Preconditions

- Python 3.12+ 与 pytest 可用。
- 现有后端测试夹具可运行。
- 缺少依赖或出现循环导入时必须立即修复或停止，不允许静默降级。

## Impacted Areas

- `backend/app/services/app_service.py`
- `backend/app/services/schedules_query_service.py`
- `backend/app/services/schedules_query_facade.py`
- `backend/app/services/schedules_query_facade_provider.py`
- `backend/app/services/order_summary_query_service.py`
- `backend/app/services/dashboard_query_service.py`
- `backend/app/services/order_summary_query_facade.py`
- `backend/app/services/dashboard_query_facade.py`
- `backend/tests/`

## Phase Plan

### P1: 下沉 schedules 查询实现

- Objective: 将 schedules 相关公开查询从 `AppService` 内部实现改为独立 query service 承接。
- Owned paths:
  - `backend/app/services/app_service.py`
  - `backend/app/services/schedules_query_service.py`
  - `backend/app/services/schedules_query_facade.py`
  - `backend/app/services/schedules_query_facade_provider.py`
- Dependencies:
  - 现有 schedules facade/provider
  - 现有 current schedule 表结构
- Deliverables:
  - 独立 schedules query service
  - `AppService` 委托到 schedules service

### P2: 为 order-summary/dashboard 建立内部 service 骨架

- Objective: 让 `order-summary` 与 `dashboard` facade 下方依赖显式 service 层，为后续更深下沉做准备。
- Owned paths:
  - `backend/app/services/order_summary_query_service.py`
  - `backend/app/services/dashboard_query_service.py`
  - 对应 facade/provider
- Dependencies:
  - 现有 facade/provider
  - 现有 `AppService` 公开方法
- Deliverables:
  - order-summary query service 骨架
  - dashboard query service 骨架
  - facade 改为依赖 service

### P3: 定向测试与工件闭环

- Objective: 用定向 pytest 验证 service 层改造没有打断 facade/provider 与路由委托，并补齐工件。
- Owned paths:
  - `backend/tests/`
  - `doc/tasks/facade-appservice-query-service-order-summary-da-20260419T022521/`
- Dependencies:
  - P1、P2 已完成
- Deliverables:
  - 通过的 pytest
  - `execution-log.md`
  - `test-report.md`

## Phase Acceptance Criteria

### P1

- P1-AC1: schedules facade/provider 依赖 `SchedulesQueryService`，不再直接依赖 `AppService` 的 schedules 公开方法实现。
- P1-AC2: `AppService` 的 schedules 三个公开方法改为委托到 `SchedulesQueryService`。
- Evidence expectation: 代码 diff、`execution-log.md#Phase-P1`

### P2

- P2-AC1: order-summary 与 dashboard facade 下方都有显式 query service 层。
- P2-AC2: facade/provider 层与测试完成同步，说明依赖结构已从 facade -> AppService 变为 facade -> service。
- Evidence expectation: 代码 diff、`execution-log.md#Phase-P2`

### P3

- P3-AC1: 定向 pytest 证明 schedules/order-summary/dashboard 的 facade/provider 与 route delegation 仍可用。
- P3-AC2: `validate_test_report.py` 与 `check_completion.py --apply` 通过。
- Evidence expectation: pytest 输出、`test-report.md#T1`、`test-report.md#T2`、`test-report.md#T3`

## Done Definition

- schedules 查询实现已从 `AppService` 中真实下沉到独立 service。
- order-summary 与 dashboard 已建立 service 层骨架。
- 定向 pytest 通过，工件闭环完成。

## Blocking Conditions

- 发现 service 下沉引入无法接受的循环导入或初始化副作用。
- 任一关键定向测试持续失败且根因超出本轮 service 层改造范围。
