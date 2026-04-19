# Test Report

- Task ID: `order-summary-dashboard-appservice-query-service-20260419T024628`
- Created: `2026-04-19T02:46:28`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `继续模块化重构：将 order-summary 与 dashboard 的查询实现体从 AppService 真实下沉到独立 query service，降低单体内部耦合并保持 facade/provider 与路由委托稳定`

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-runtime
- Tools: Windows PowerShell; Python 3.12.10; pytest 9.0.2
- Initial readable artifacts: prd.md; test-plan.md
- Initial withheld artifacts: execution-log.md; task-state.json
- Initial verdict before withheld inspection: yes

Record the tester's first-pass visibility honestly. In `blind-first-pass`, the tester should record `yes` only after writing an initial verdict before inspecting withheld artifacts.

## Results

Add one subsection per executed test case using the test case ids from `test-plan.md`.

Each subsection should use this shape:

`### T1: concise title`

- `Result: passed|failed|blocked|not_run`
- `Covers: P1-AC1`
- `Command run: exact command or manual action`
- `Environment proof: runtime, URL, browser session, fixture, or deployment proof`
- `Evidence refs: screenshot, video, trace, HAR, or log refs`
- `Notes: concise findings`

For `real-browser` validation, include at least one evidence ref that resolves to an existing non-task-artifact file, such as `evidence/home.png`, `evidence/trace.zip`, or `evidence/session.har`.

### T1: order-summary service 与 facade 回归

- Result: passed
- Covers: P1-AC1, P1-AC2, P2-AC2, P3-AC1
- Command run: `python -m pytest backend/tests/test_order_summary_query_service.py backend/tests/test_order_summary_query_facade.py backend/tests/test_dashboard_query_facade.py`
- Environment proof: platform win32; rootdir `D:\ProjectPackage\ProductionPlan`; Python 3.12.10; pytest 9.0.2
- Evidence refs: pytest terminal output (collected 6 items; `6 passed in 5.18s`)
- Notes: 相关 3 组用例均通过，未见失败或错误输出。

### T2: route delegation 与相关 facade 回归

- Result: passed
- Covers: P2-AC1, P3-AC1
- Command run: `python -m pytest backend/tests/test_schedules_query_facade.py backend/tests/test_app_queries_schedule_summary_dashboard_facades.py`
- Environment proof: platform win32; rootdir `D:\ProjectPackage\ProductionPlan`; Python 3.12.10; pytest 9.0.2
- Evidence refs: pytest terminal output (collected 4 items; `4 passed in 2.20s`)
- Notes: route delegation 与 app_queries facade 回归用例通过，未见失败或错误输出。

### T3: 测试报告结构校验

- Result: passed
- Covers: P3-AC2
- Command run: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id order-summary-dashboard-appservice-query-service-20260419T024628`
- Environment proof: executed on Windows PowerShell in repo root `D:\ProjectPackage\ProductionPlan`
- Evidence refs: validator output (`status: ok`)
- Notes: 首次校验提示缺少 T3 用例结果条目；补齐后重新运行校验已通过。

## Initial Verdict

- Outcome: pending
- Verified acceptance ids: P1-AC1, P1-AC2, P2-AC1, P2-AC2, P3-AC1
- Blocking prerequisites:
- Summary: 按 test-plan 执行 T1/T2 均通过，初步判断本轮下沉未破坏既有 facade/provider 与 route delegation 行为；仍需完成 T3 对 test-report 结构的校验。

## Final Verdict

- Outcome: passed
- Verified acceptance ids: P1-AC1, P1-AC2, P2-AC1, P2-AC2, P3-AC1, P3-AC2
- Blocking prerequisites:
- Summary: 按 test-plan 执行 T1/T2 均通过；T3 结构校验通过。本轮测试未发现 order-summary 下沉导致的回归信号。

## Open Issues

- None yet.
