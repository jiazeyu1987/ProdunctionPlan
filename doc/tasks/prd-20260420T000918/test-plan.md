# Test Plan

- Task ID: `prd-20260420T000918`
- Created: `2026-04-20T00:09:18`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `查看当前系统是否需要重构，如果需要则在保持前端界面不变的前提下，整理自上而下模块化、低耦合重构方案并写入 PRD`

## Test Scope

本测试计划用于验证后续重构执行阶段是否满足以下目标：

- 后端从大一统应用服务向分域模块拆分时，业务行为和 API 契约保持稳定
- 前端在拆分 page controller、feature service、共享调用层后，页面外观、布局、导航和关键交互不变
- Orders Pool、Schedule Calendar、Masterdata、Lite Scheduler 等高耦合页面在真实浏览器中仍可完成关键路径

本计划不覆盖：

- 新增业务功能验收
- 全量性能压测
- 部署脚本与服务器运维流程变更

## Environment

- OS: Windows
- Workspace: `D:\ProjectPackage\ProductionPlan`
- Backend runtime: Python 3.11+，可执行 FastAPI 应用与后端测试
- Frontend runtime: Node.js 20+，依赖安装自 `fronted/package-lock.json`
- Database: SQLite，本地初始化链路可用
- Browser validation: Playwright 真实浏览器
- 前端默认端口: `2798`
- 后端健康检查: `http://127.0.0.1:8000/api/health`

## Accounts and Fixtures

- 调度员角色账号，用于验证排程、订单池、主数据相关页面
- 车间主管角色账号，用于验证受限查询页面
- 一套可加载订单池、主数据、排程数据的真实或标准测试数据
- 若缺少任何账号、角色或数据集，测试必须失败并记录缺失项，不允许跳过相关用例

## Commands

- `python -m pytest backend/tests/test_app_service_provider.py backend/tests/test_app_queries_order_pool_facade.py backend/tests/test_app_queries_schedule_summary_dashboard_facades.py backend/tests/test_masterdata_query_facade.py backend/tests/test_schedules_query_facade.py`
  期望：全部通过，证明 provider/facade/查询入口在拆分后仍保持基本契约。
- `python -m pytest backend/tests/test_dispatch_command_service.py backend/tests/test_masterdata_command_service.py backend/tests/test_reporting_command_service.py backend/tests/test_app_service_batch_dispatch.py`
  期望：全部通过，证明命令编排链路在拆分后未破坏关键行为。
- `npm run lint`
  期望：前端拆分后无新增 lint 错误。
- `npm run e2e:playwright -- --grep "orders-pool|production-plan|lite-scheduler|masterdata"`
  期望：关键页面真实浏览器用例通过，并产出 Playwright 证据。
- `npm run e2e:browser`
  期望：浏览器批量执行链路可运行，用于执行阶段的回归补充。

## Test Cases

### T1: 后端现有分层入口保持可用

- Covers: P1-AC1, P1-AC3, P2-AC3
- Level: unit/integration
- Command: `python -m pytest backend/tests/test_app_service_provider.py backend/tests/test_app_queries_order_pool_facade.py backend/tests/test_app_queries_schedule_summary_dashboard_facades.py`
- Expected: provider、facade、查询路由委托关系保持稳定，未因重构回退为更粗粒度耦合。

### T2: 后端命令侧拆分后行为保持稳定

- Covers: P2-AC1, P2-AC2
- Level: unit/integration
- Command: `python -m pytest backend/tests/test_dispatch_command_service.py backend/tests/test_masterdata_command_service.py backend/tests/test_reporting_command_service.py`
- Expected: 命令服务职责清晰，命令路由与作业分发仍能正确委托到应用服务，不出现 fallback 或静默吞错。

### T3: Orders Pool 页面保形回归

- Covers: P1-AC2, P3-AC1, P3-AC2, P3-AC3, P4-AC2
- Level: e2e
- Command: `npm run e2e:playwright -- --grep "orders-pool"`
- Expected: 订单池页面布局、筛选、分页、详情、批量操作入口保持原有可见行为，Playwright 产出截图或 trace 证据。

### T4: Schedule Calendar 页面保形回归

- Covers: P1-AC2, P3-AC1, P3-AC3, P4-AC2
- Level: e2e
- Command: `npm run e2e:playwright -- --grep "production-plan|schedule|calendar"`
- Expected: 日历视图、版本切换、排程操作入口与日维度展示保持稳定，页面无结构性回归。

### T5: Masterdata 页面与主数据调用边界回归

- Covers: P2-AC2, P3-AC2, P3-AC3
- Level: integration/e2e
- Command: `npm run e2e:playwright -- --grep "masterdata"`
- Expected: 主数据加载、保存、工艺路线相关路径保持可用，前端页面未因 service 拆分产生界面变化。

### T6: Lite Scheduler 与执行关联页面冒烟

- Covers: P4-AC1, P4-AC2, P4-AC3
- Level: e2e
- Command: `npm run e2e:playwright -- --grep "lite-scheduler|production-plan"`
- Expected: 轻排产与关联关键页在真实浏览器下可打开并完成核心流程，若行为偏离则直接判定失败。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | Backend layering | provider/facade/query route remains stable | unit/integration | P1-AC1, P1-AC3, P2-AC3 | pytest output, `test-report.md` |
| T2 | Backend commands | command orchestration split preserves behavior | unit/integration | P2-AC1, P2-AC2 | pytest output, `test-report.md` |
| T3 | Orders Pool UI | controller split without UI change | e2e | P1-AC2, P3-AC1, P3-AC2, P3-AC3, P4-AC2 | Playwright screenshot/trace/video, `test-report.md` |
| T4 | Schedule Calendar UI | page structure and interactions remain stable | e2e | P1-AC2, P3-AC1, P3-AC3, P4-AC2 | Playwright screenshot/trace/video, `test-report.md` |
| T5 | Masterdata UI + service boundary | service split without page regression | integration/e2e | P2-AC2, P3-AC2, P3-AC3 | Playwright evidence, `test-report.md` |
| T6 | Regression smoke | critical scheduling flows remain intact | e2e | P4-AC1, P4-AC2, P4-AC3 | Playwright evidence, `test-report.md` |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: pytest, node, npm, playwright
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: 在真实仓库与真实运行时下执行。凡涉及界面、布局、交互、页面保形的验证，必须使用真实浏览器并保留截图、trace、video 或等效证据。
- Escalation rule: 在 tester 写出首轮结论前，不得查看 `execution-log.md` 或 `task-state.json`；只有主代理明确要求进行差异分析时才可放开。

## Pass / Fail Criteria

- Pass when:
  后端分层和命令拆分相关测试通过；前端关键页面在真实浏览器中保持界面与主流程稳定；没有新增 fallback、mock、静默降级或未解释的契约变化。
- Fail when:
  任一 acceptance id 无对应证据；任一关键命令失败；任一关键页面布局或交互发生变化；因环境缺失而无法完成验证；或通过 fallback 掩盖真实回归。

## Regression Scope

- `backend/app/api/routes/app_queries.py`
- `backend/app/api/routes/commands.py`
- `backend/app/services/app_service.py`
- `backend/app/services/job_dispatcher.py`
- `fronted/src/legacy/features/orders-pool/**`
- `fronted/src/legacy/features/schedule-calendar/**`
- `fronted/src/legacy/features/masterdata/**`
- `fronted/src/legacy/features/lite-scheduler/**`
- `fronted/src/legacy/shared/api/**`
- `fronted/src/legacy/pages/**`

## Reporting Notes

测试结果写入 `test-report.md`。

测试代理必须保持独立，不得修改产品代码，不得重写 PRD；若发现失败，只记录失败用例、证据与复现方式，并将修复工作交回执行方。
