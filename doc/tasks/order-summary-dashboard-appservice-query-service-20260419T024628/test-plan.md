# Test Plan

- Task ID: `order-summary-dashboard-appservice-query-service-20260419T024628`
- Created: `2026-04-19T02:46:28`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `继续模块化重构：将 order_summary_query_service 与 dashboard_query_service 从薄包装推进为真实承接实现的 service，并让 AppService 对这两块公开查询降为委托入口`

## Test Scope

验证 order-summary 真实下沉后的 service 行为、现有 facade/provider 稳定性，以及 route delegation 不回退。

## Environment

- Windows PowerShell
- 仓库根目录：`D:\ProjectPackage\ProductionPlan`
- Python 3.12+
- pytest 可用

## Accounts and Fixtures

- 使用后端单元测试与临时 SQLite 夹具
- 不依赖真实账号或外部服务
- pytest 不可用时必须 fail fast

## Commands

- `python -m pytest backend/tests/test_order_summary_query_service.py backend/tests/test_order_summary_query_facade.py backend/tests/test_dashboard_query_facade.py`
  - 预期信号：service/facade 测试通过
- `python -m pytest backend/tests/test_schedules_query_facade.py backend/tests/test_app_queries_schedule_summary_dashboard_facades.py`
  - 预期信号：路由委托与其他 facade 回归通过

## Test Cases

### T1: order-summary service 与 facade 回归

- Covers: P1-AC1, P1-AC2, P2-AC2, P3-AC1
- Level: unit
- Command: `python -m pytest backend/tests/test_order_summary_query_service.py backend/tests/test_order_summary_query_facade.py backend/tests/test_dashboard_query_facade.py`
- Expected: order-summary service 真实实现可用，facade/provider 不回退

### T2: route delegation 与其他 facade 回归

- Covers: P2-AC1, P3-AC1
- Level: unit
- Command: `python -m pytest backend/tests/test_schedules_query_facade.py backend/tests/test_app_queries_schedule_summary_dashboard_facades.py`
- Expected: route delegation 与其余 facade 测试通过

### T3: 测试报告结构校验

- Covers: P3-AC2
- Level: manual
- Command: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id order-summary-dashboard-appservice-query-service-20260419T024628`
- Expected: `test-report.md` 结构合法

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | order-summary service | 真实下沉后的 service 与 facade 可用 | unit | P1-AC1, P1-AC2, P2-AC2, P3-AC1 | `test-report.md#T1` |
| T2 | route delegation | 路由委托与其他 facade 未被打断 | unit | P2-AC1, P3-AC1 | `test-report.md#T2` |
| T3 | workflow artifacts | 测试报告结构满足 workflow 要求 | manual | P3-AC2 | `test-report.md#T3` |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-runtime
- Required tools: pytest
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: Run against the real repo and local pytest runtime with no fallback behavior
- Escalation rule: Do not inspect withheld artifacts until the tester has written an initial verdict

## Pass / Fail Criteria

- Pass when:
  - T1、T2、T3 全部通过
  - order-summary 真实下沉未打断 facade/provider 与 route delegation
- Fail when:
  - 任一命令失败
  - 发现为了通过测试新增 fallback 或静默兼容逻辑

## Regression Scope

- `backend/app/services/order_summary_query_service.py`
- `backend/app/services/dashboard_query_service.py`
- `backend/app/services/app_service.py`
- `backend/app/api/routes/app_queries.py`

## Reporting Notes

测试结果写入 `test-report.md`，tester 不修改产品代码。
