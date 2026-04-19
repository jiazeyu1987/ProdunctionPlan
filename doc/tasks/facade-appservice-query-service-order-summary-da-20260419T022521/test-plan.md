# Test Plan

- Task ID: `facade-appservice-query-service-order-summary-da-20260419T022521`
- Created: `2026-04-19T02:25:21`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `继续模块化重构：将 facade 之下的查询实现从 AppService 内部下沉到独立 query service，优先处理 order-summary 与 dashboard 查询域，降低单体内部耦合`

## Test Scope

验证 schedules 的真实 query service 下沉，以及 order-summary/dashboard 的 service 层骨架改造，没有破坏 facade/provider 与 route delegation。

覆盖范围：

- schedules/order-summary/dashboard facade/provider 测试
- 对应路由委托测试

不覆盖：

- 前端
- worker
- 命令接口

## Environment

- Windows PowerShell
- 仓库根目录：`D:\ProjectPackage\ProductionPlan`
- Python 3.12+
- pytest 可用

## Accounts and Fixtures

- 使用后端单元测试与临时 SQLite 夹具。
- 不依赖真实账号或外部服务。
- 若 pytest 不可用或出现循环导入，必须 fail fast。

## Commands

- `python -m pytest backend/tests/test_schedules_query_facade.py backend/tests/test_order_summary_query_facade.py backend/tests/test_dashboard_query_facade.py`
  - 预期信号：facade/provider 与 service 依赖测试通过。
- `python -m pytest backend/tests/test_app_queries_schedule_summary_dashboard_facades.py`
  - 预期信号：路由层委托测试通过。

## Test Cases

### T1: facade/provider 与 service 依赖回归

- Covers: P1-AC1, P1-AC2, P2-AC1, P2-AC2, P3-AC1
- Level: unit
- Command: `python -m pytest backend/tests/test_schedules_query_facade.py backend/tests/test_order_summary_query_facade.py backend/tests/test_dashboard_query_facade.py`
- Expected: facade/provider 和 service 依赖结构可用，测试通过。

### T2: 路由委托回归

- Covers: P3-AC1
- Level: unit
- Command: `python -m pytest backend/tests/test_app_queries_schedule_summary_dashboard_facades.py`
- Expected: schedules/order-summary/dashboard 路由委托测试通过。

### T3: 测试报告结构校验

- Covers: P3-AC2
- Level: manual
- Command: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id facade-appservice-query-service-order-summary-da-20260419T022521`
- Expected: `test-report.md` 结构合法。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | services/facades | facade/provider 与 service 依赖结构可用 | unit | P1-AC1, P1-AC2, P2-AC1, P2-AC2, P3-AC1 | `test-report.md#T1` |
| T2 | app_queries routing | 路由委托未被 service 改造打断 | unit | P3-AC1 | `test-report.md#T2` |
| T3 | workflow artifacts | 测试报告结构满足 workflow 要求 | manual | P3-AC2 | `test-report.md#T3` |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-runtime
- Required tools: pytest
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: Run against the real repo and local pytest runtime with no fallback behavior.
- Escalation rule: Do not inspect withheld artifacts until the tester has written an initial verdict.

## Pass / Fail Criteria

- Pass when:
  - T1、T2、T3 全部通过。
  - service 层改造未打断 facade/provider 与路由委托。
- Fail when:
  - 任一命令失败。
  - 发现为了通过测试新增 fallback 或静默兼容逻辑。

## Regression Scope

- `backend/app/services/app_service.py`
- `backend/app/services/schedules_query_service.py`
- `backend/app/services/order_summary_query_service.py`
- `backend/app/services/dashboard_query_service.py`
- `backend/app/api/routes/app_queries.py`

## Reporting Notes

测试结果写入 `test-report.md`，tester 不修改产品代码。
