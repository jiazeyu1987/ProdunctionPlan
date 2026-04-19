# Test Plan

- Task ID: `app-queries-schedules-order-summary-dashboard-fa-20260419T021235`
- Created: `2026-04-19T02:12:35`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `继续模块化重构：拆分 app_queries 中剩余的 schedules、order-summary、dashboard 查询依赖，为每个业务域建立独立 facade，进一步降低路由层对 AppService 的直接耦合`

## Test Scope

验证 schedules、order-summary、dashboard 三类 facade 切分没有破坏路由层调用路径，并确认对应接口不再直接依赖 `AppService`。

覆盖范围：

- 三类 facade/provider 与委托测试
- `app_queries` 对应路由委托测试

不覆盖：

- 前端与浏览器验证
- 命令接口
- 排产生成或 worker 行为

## Environment

- Windows PowerShell
- 仓库根目录：`D:\ProjectPackage\ProductionPlan`
- Python 3.12+
- pytest 可用

## Accounts and Fixtures

- 使用后端单元测试与临时 SQLite 夹具。
- 不依赖真实账号或外部服务。
- 若 pytest 不可用，必须 fail fast。

## Commands

- `python -m pytest backend/tests/test_schedules_query_facade.py backend/tests/test_order_summary_query_facade.py backend/tests/test_dashboard_query_facade.py`
  - 预期信号：三类 facade/provider 与委托测试通过。
- `python -m pytest backend/tests/test_app_queries_schedule_summary_dashboard_facades.py`
  - 预期信号：路由层委托测试通过。

## Test Cases

### T1: facade provider 与委托回归

- Covers: P1-AC2, P2-AC2, P3-AC1
- Level: unit
- Command: `python -m pytest backend/tests/test_schedules_query_facade.py backend/tests/test_order_summary_query_facade.py backend/tests/test_dashboard_query_facade.py`
- Expected: 三类 facade/provider 能构造并把调用委托给底层服务。

### T2: app_queries 路由依赖切换

- Covers: P1-AC1, P2-AC1, P3-AC1
- Level: unit
- Command: `python -m pytest backend/tests/test_app_queries_schedule_summary_dashboard_facades.py`
- Expected: 路由层对应入口通过 facade 依赖执行，不再直接注入 `AppService`。

### T3: 测试报告结构校验

- Covers: P3-AC2
- Level: manual
- Command: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id app-queries-schedules-order-summary-dashboard-fa-20260419T021235`
- Expected: `test-report.md` 结构合法。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | facades | schedules/order-summary/dashboard facade provider 与委托可用 | unit | P1-AC2, P2-AC2, P3-AC1 | `test-report.md#T1` |
| T2 | app_queries routing | 剩余路由层切换到 facade 依赖 | unit | P1-AC1, P2-AC1, P3-AC1 | `test-report.md#T2` |
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
  - schedules/order-summary/dashboard 路由依赖切换明确且 facade 委托可用。
- Fail when:
  - 任一命令失败。
  - 发现为了通过测试新增 fallback 或静默兼容逻辑。

## Regression Scope

- `backend/app/api/routes/app_queries.py`
- 新增 schedules/order-summary/dashboard facade/provider 模块

## Reporting Notes

测试结果写入 `test-report.md`，tester 不修改产品代码。
