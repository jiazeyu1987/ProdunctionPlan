# Test Plan

- Task ID: `task-16baa18d28-20260419T222910`
- Created: `2026-04-19T22:29:10`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `删除解锁,锁单按钮增加冻结,解冻按钮`

## Test Scope

验证订单池页面单条与批量操作从“解锁”切换到“冻结/解冻”后的完整行为，包括前端按钮展示、批量文案与校验、后端命令处理、状态落库以及局部刷新链路。排程算法、ERP 同步和其他非本任务按钮不在本次测试范围内。

## Environment

- Windows 本地仓库：`D:\ProjectPackage\ProductionPlan`
- 后端测试使用仓库现有 Python 环境执行 `pytest`
- 前端测试使用 `fronted` 工作区中的 Playwright
- UI 验证运行在本地真实浏览器环境，不使用 mock UI 截图替代真实交互证据

## Accounts and Fixtures

- Playwright 用例使用仓库内现有 scheduler stub 登录态
- 订单池 e2e 用例使用测试内路由 stub 的订单池单条数据
- 后端测试使用临时 SQLite 数据库与测试内 seeded 订单
- 若 Playwright 浏览器或 Python 测试环境缺失，测试必须 fail fast 并记录缺失前提

## Commands

- `python -m pytest backend/tests/test_app_service_batch_dispatch.py -q`
  期望：批量命令服务相关回归通过，覆盖冻结/解冻状态变更与非法状态拒绝
- `python -m pytest backend/tests/test_dispatch_command_service.py -q`
  期望：底层调度命令服务基础能力通过，新增冻结/解冻路径可被批准并落库
- `npm run e2e:playwright -- tests/e2e/orders-pool-item-refresh.e2e.spec.ts`
  期望：订单池真实浏览器用例通过，并生成 trace/video/screenshot 证据

## Test Cases

### T0: 任务文档覆盖冻结命令与真实浏览器验证

- Covers: P1-AC1, P1-AC2
- Level: review
- Command: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_artifacts.py --cwd D:\ProjectPackage\ProductionPlan --task-id task-16baa18d28-20260419T222910`
- Expected: `prd.md` 与 `test-plan.md` 校验通过，且文档明确包含 `FREEZE` / `UNFREEZE` 命令链路、`Validation surface: real-browser` 与 `Required tools: playwright`。

### T1: 单条订单按钮切换为冻结语义

- Covers: P2-AC1, P2-AC3, P3-AC3
- Level: e2e
- Command: `npm run e2e:playwright -- tests/e2e/orders-pool-item-refresh.e2e.spec.ts`
- Expected: 单条订单初始显示“锁单”和“冻结”；执行冻结后显示“解冻”，页面中不再出现“解锁”入口。

### T2: 单条冻结/解冻仍走局部刷新

- Covers: P2-AC1, P2-AC3, P3-AC2
- Level: e2e
- Command: `npm run e2e:playwright -- tests/e2e/orders-pool-item-refresh.e2e.spec.ts`
- Expected: 点击冻结或解冻后，不新增整表 `/api/order-pool` 请求；页面只更新受影响订单，可以是本地受影响行更新或单条订单刷新。

### T3: 批量冻结/解冻命令服务更新状态

- Covers: P2-AC2, P2-AC4, P3-AC1
- Level: unit/integration
- Command: `python -m pytest backend/tests/test_app_service_batch_dispatch.py -q`
- Expected: `FREEZE` / `UNFREEZE` 可正确更新 `frozen_flag`，并写入命令审计记录。

### T4: 非法冻结状态 fail fast

- Covers: P2-AC4, P3-AC1
- Level: unit/integration
- Command: `python -m pytest backend/tests/test_app_service_batch_dispatch.py -q`
- Expected: 选中已冻结订单执行 `FREEZE` 或选中未冻结订单执行 `UNFREEZE` 时返回明确错误，不产生部分更新。

### T5: 调度命令批准链路支持冻结/解冻

- Covers: P2-AC4, P3-AC1
- Level: unit/integration
- Command: `python -m pytest backend/tests/test_dispatch_command_service.py -q`
- Expected: 创建并批准 `FREEZE` / `UNFREEZE` 命令后，订单状态按预期更新。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T0 | Task artifacts | 文档覆盖冻结命令与真实浏览器验证 | review | P1-AC1, P1-AC2 | `test-report.md` + `validate_artifacts.py` 输出 |
| T1 | Orders pool row actions | 单条按钮切换为冻结/解冻且无解锁入口 | e2e | P2-AC1, P2-AC3, P3-AC3 | `test-report.md` + Playwright 证据 |
| T2 | Orders pool refresh | 冻结/解冻后仅更新受影响订单且不整表刷新 | e2e | P2-AC1, P2-AC3, P3-AC2 | `test-report.md` + Playwright 证据 |
| T3 | Batch dispatch backend | 批量冻结/解冻更新状态与审计 | unit/integration | P2-AC2, P2-AC4, P3-AC1 | `test-report.md` + pytest 输出 |
| T4 | Batch dispatch backend | 非法冻结状态 fail fast | unit/integration | P2-AC4, P3-AC1 | `test-report.md` + pytest 输出 |
| T5 | Dispatch command service | 单命令批准链路支持冻结/解冻 | unit/integration | P2-AC4, P3-AC1 | `test-report.md` + pytest 输出 |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: playwright, pytest
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: Against the real repo state; UI paths must use a real browser session and record concrete evidence files.
- Escalation rule: Do not inspect `execution-log.md` or `task-state.json` until an initial verdict is written, unless the main agent explicitly asks for discrepancy analysis.

## Pass / Fail Criteria

- Pass when:
  - 单条与批量入口都完成从“解锁”到“冻结/解冻”的切换
  - `FREEZE` / `UNFREEZE` 前后端命令链路和测试全部通过
  - 真实浏览器证据证明局部刷新行为未退化
- Fail when:
  - 页面仍出现“解锁”入口
  - `FREEZE` / `UNFREEZE` 只改前端文案，没有真正落到后端状态
  - 冻结/解冻动作触发整表刷新，或测试失败/被跳过且无明确阻塞前提

## Regression Scope

- 订单池单条按钮：锁单、优先级调整、删除
- 订单池批量工具栏：批量锁单、批量提优先级
- 调度命令服务对现有 `LOCK` / `UNLOCK` / `PRIORITY_*` 命令的已有语义

## Reporting Notes

结果写入 `test-report.md`。真实浏览器用例必须引用至少一个现有的 trace、video、screenshot 或同类非任务产物证据文件。
