# PRD

- Task ID: `order-summary-dashboard-appservice-query-service-20260419T024628`
- Created: `2026-04-19T02:46:28`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `继续模块化重构：将 order_summary_query_service 与 dashboard_query_service 从薄包装推进为真实承接实现的 service，并让 AppService 对这两块公开查询降为委托入口`

## Goal

把 `order-summary` 查询域从 facade 下方的薄包装推进为真正承接实现的 query service，并保持 `dashboard` 相关 facade/provider、route delegation 稳定，为下一轮继续下沉 `dashboard` 实现打基础。

## Scope

- 将 `get_order_summary` 与 `list_order_summary_workshop_managers` 的实现体下沉到 `backend/app/services/order_summary_query_service.py`
- `backend/app/services/app_service.py` 中对应两个公开方法改为委托入口
- 保持 `backend/app/services/dashboard_query_service.py` 作为 service 层骨架，并验证未被打断
- 补充 `backend/tests/test_order_summary_query_service.py`
- 复跑 order-summary / dashboard / schedules 相关 facade 与 route delegation 测试

## Non-Goals

- 本轮不把 `get_scheduler_dashboard` 的完整实现体全部搬出 `AppService`
- 不调整 HTTP 路径、权限规则、返回结构
- 不改动命令接口、worker、排产生成逻辑

## Preconditions

- Python 3.12+ 与 pytest 可用
- 后端测试夹具可运行
- 若出现循环导入或 pytest 失败，必须 fail fast

## Impacted Areas

- `backend/app/services/app_service.py`
- `backend/app/services/order_summary_query_service.py`
- `backend/app/services/dashboard_query_service.py`
- `backend/tests/test_order_summary_query_service.py`
- `backend/tests/test_order_summary_query_facade.py`
- `backend/tests/test_dashboard_query_facade.py`
- `backend/tests/test_schedules_query_facade.py`
- `backend/tests/test_app_queries_schedule_summary_dashboard_facades.py`

## Phase Plan

### P1: 真实下沉 order-summary 查询实现

- Objective:
  - 将 order-summary 两个公开查询方法的实现体搬到 `OrderSummaryQueryService`
- Owned paths:
  - `backend/app/services/order_summary_query_service.py`
  - `backend/app/services/app_service.py`
- Dependencies:
  - 现有 host helper
- Deliverables:
  - 真实实现版 `OrderSummaryQueryService`
  - 委托版 `AppService` 入口

### P2: 保持 facade/provider 与 dashboard service 稳定

- Objective:
  - 确保 facade/provider 与 route delegation 继续稳定，并保持 dashboard service 骨架可继续承接后续下沉
- Owned paths:
  - `backend/app/services/dashboard_query_service.py`
  - `backend/tests/`
- Dependencies:
  - P1 已完成
- Deliverables:
  - 通过的 facade/provider 测试
  - 通过的 route delegation 测试

### P3: 工件闭环

- Objective:
  - 记录执行与测试证据并通过 completion gate
- Owned paths:
  - `doc/tasks/order-summary-dashboard-appservice-query-service-20260419T024628/`
- Dependencies:
  - P1、P2 已完成
- Deliverables:
  - `execution-log.md`
  - `test-report.md`

## Phase Acceptance Criteria

### P1

- P1-AC1: `OrderSummaryQueryService` 不再是薄包装，而是承接 `get_order_summary` 与 `list_order_summary_workshop_managers` 的真实实现
- P1-AC2: `AppService` 对这两个公开方法降为委托入口
- Evidence expectation:
  - 代码 diff、`execution-log.md#Phase-P1`

### P2

- P2-AC1: facade/provider 与路由委托测试仍然通过
- P2-AC2: dashboard service 仍可稳定依赖当前内部 service 分层，不被这次下沉打断
- Evidence expectation:
  - pytest 输出、`execution-log.md#Phase-P2`

### P3

- P3-AC1: 定向 pytest 与 tester 复核通过
- P3-AC2: `validate_test_report.py` 与 `check_completion.py --apply` 通过
- Evidence expectation:
  - `test-report.md#T1`
  - `test-report.md#T2`
  - `test-report.md#T3`

## Done Definition

- order-summary 查询实现已真实下沉到独立 service
- `AppService` 中对应方法仅保留委托职责
- 定向测试与工件闭环完成

## Blocking Conditions

- 真实下沉引入不可接受的循环导入或行为回归
- 任一关键定向测试持续失败且根因超出本轮下沉范围
