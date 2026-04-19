# Test Report

- Task ID: `facade-appservice-query-service-order-summary-da-20260419T022521`
- Created: `2026-04-19T02:25:21`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `继续模块化重构：将 facade 之下的查询实现从 AppService 内部下沉到独立 query service，优先处理 order-summary 与 dashboard 查询域，降低单体内部耦合`

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-runtime
- Tools: Windows PowerShell; Python `3.12.10`; `pytest 9.0.2` (pluggy `1.6.0`)
- Initial readable artifacts: prd.md, test-plan.md
- Initial withheld artifacts: execution-log.md, task-state.json
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

### T1: facade/provider 与 service 依赖回归

- Result: passed
- Covers: P1-AC1, P1-AC2, P2-AC1, P2-AC2, P3-AC1
- Command run: `python -m pytest backend/tests/test_schedules_query_facade.py backend/tests/test_order_summary_query_facade.py backend/tests/test_dashboard_query_facade.py`
- Environment proof: `platform win32 -- Python 3.12.10, pytest-9.0.2, pluggy-1.6.0` (rootdir: `D:\ProjectPackage\ProductionPlan`)
- Evidence refs: inline pytest output: `6 passed in 5.65s`
- Notes: 无失败用例；facade/provider 回归测试通过。

### T2: 路由委托回归

- Result: passed
- Covers: P3-AC1
- Command run: `python -m pytest backend/tests/test_app_queries_schedule_summary_dashboard_facades.py`
- Environment proof: `platform win32 -- Python 3.12.10, pytest-9.0.2, pluggy-1.6.0` (rootdir: `D:\ProjectPackage\ProductionPlan`)
- Evidence refs: inline pytest output: `2 passed in 0.69s`
- Notes: schedules/order-summary/dashboard 路由委托用例均通过。

### T3: 测试报告结构校验

- Result: passed
- Covers: P3-AC2
- Command run: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id facade-appservice-query-service-order-summary-da-20260419T022521`
- Environment proof: same as T1/T2 (local PowerShell + Python/pytest)
- Evidence refs: inline validator output: `status: ok`
- Notes: 初次校验为 `status: error`（Environment Used 字段与 test-plan 不一致、且缺少 T3 条目）；修正报告后复跑校验通过。

## Initial Verdict

- Outcome: pending
- Verified acceptance ids: P1-AC1, P1-AC2, P2-AC1, P2-AC2, P3-AC1 (via T1/T2)
- Blocking prerequisites:
- Summary: T1/T2 已通过；尚未执行 T3（test-report 结构校验），因此先给出 pending。

## Final Verdict

- Outcome: passed
- Verified acceptance ids: P1-AC1, P1-AC2, P2-AC1, P2-AC2, P3-AC1, P3-AC2
- Blocking prerequisites:
- Summary: T1/T2 pytest 全部通过，T3 报告结构校验为 `status: ok`。

## Open Issues

- None yet.
