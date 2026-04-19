# Test Plan

- Task ID: `facade-app-queries-appservice-20260419T014536`
- Created: `2026-04-19T01:45:36`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `继续模块化重构：抽离订单池查询 facade，使 app_queries 不再直接依赖 AppService，并保持订单池/工序时间线查询行为稳定`

## Test Scope

验证订单池 facade 重构没有改变订单池相关查询行为，并确认路由层依赖已从 `AppService` 切换到独立 facade。

覆盖范围：

- 订单池列表、详情、工序时间线、物料查询相关后端测试。
- `app_queries.py` 的依赖切换。

不覆盖：

- 非订单池接口。
- 前端。
- ERP 联调。

## Environment

- Windows PowerShell
- 仓库根目录：`D:\ProjectPackage\ProductionPlan`
- Python 3.12+
- pytest 可用

## Accounts and Fixtures

- 依赖现有后端单元测试夹具，使用临时 SQLite 数据库。
- 不依赖真实账号、浏览器或 ERP 凭据。
- 若 pytest 无法运行，必须 fail fast。

## Commands

- `python -m pytest backend/tests/test_order_pool_query_facade_behavior.py backend/tests/test_app_service_process_timeline.py`
  - 预期信号：通过 facade 的订单池查询行为与工序时间线定向测试通过。
- `python -m pytest backend/tests/test_app_queries_order_pool_facade.py`
  - 预期信号：路由层 facade 依赖切换测试通过。

## Test Cases

### T1: 订单池 facade 查询行为回归

- Covers: P2-AC1
- Level: unit
- Command: `python -m pytest backend/tests/test_order_pool_query_facade_behavior.py backend/tests/test_app_service_process_timeline.py`
- Expected: 通过 facade 的订单池列表、工序时间线等定向测试通过。

### T2: app_queries facade 依赖切换

- Covers: P1-AC1, P1-AC2, P1-AC3, P2-AC2
- Level: unit
- Command: `python -m pytest backend/tests/test_app_queries_order_pool_facade.py`
- Expected: 订单池相关路由通过 facade 依赖提供服务实例，而不是直接注入 `AppService`。

### T3: 测试报告结构校验

- Covers: P3-AC1, P3-AC2
- Level: manual
- Command: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id facade-app-queries-appservice-20260419T014536`
- Expected: `test-report.md` 结构合法。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | order-pool queries | facade 重构后订单池查询行为保持稳定 | unit | P2-AC1 | `test-report.md#T1` |
| T2 | app_queries routing | 路由层切换为 facade 依赖，且 facade 边界保持聚焦 | unit | P1-AC1, P1-AC2, P1-AC3, P2-AC2 | `test-report.md#T2` |
| T3 | workflow artifacts | 测试报告结构满足 workflow 要求 | manual | P3-AC1, P3-AC2 | `test-report.md#T3` |

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
  - 订单池相关路由依赖切换明确且行为回归通过。
- Fail when:
  - 任一命令失败。
  - 发现为了保持通过而新增 fallback 或静默兼容逻辑。

## Regression Scope

- `backend/app/api/routes/app_queries.py`
- `backend/app/services/app_service.py`
- 新增 facade/provider 模块

## Reporting Notes

测试结果写入 `test-report.md`，tester 不修改产品代码。
