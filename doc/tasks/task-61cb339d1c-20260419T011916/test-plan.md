# Test Plan

- Task ID: `task-61cb339d1c-20260419T011916`
- Created: `2026-04-19T01:19:16`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `重构代码，按自上向下方式重新模块化，降低模块耦合度，优先梳理后端聚合服务和前端应用壳层的职责边界`

## Test Scope

验证本次模块化重构没有破坏 legacy 后端服务入口与 legacy 前端应用壳层装配。重点覆盖：

- 后端 legacy app provider 与 runtime 收口后的创建与调用路径。
- `JobDispatcher`、脚本、业务服务构造路径仍可用。
- legacy 前端应用壳层拆分后的导入关系、路由装配和 JSX 语法有效。

以下内容不在本次测试范围：

- 排产算法正确性的全量回归。
- ERP 联调。
- 全量 Playwright UI 流程。

本次改动是结构性重构，不引入新的 UI 交互流程，因此验证面使用 `real-runtime`，不要求 `real-browser`。

## Environment

- Windows PowerShell
- 仓库根目录：`D:\ProjectPackage\ProductionPlan`
- Python 3.12+
- Node.js + npm
- `fronted/node_modules` 已安装

## Accounts and Fixtures

- 后端测试使用仓库内自带 SQLite 临时库夹具，不依赖真实 ERP 凭据。
- 前端 lint 不依赖真实登录账号。
- 若运行时发现缺少 Python 包、Node 包或必要 fixture，必须立即失败并记录缺失前置条件。

## Commands

- `python -m pytest backend/tests/test_app_service_provider.py backend/tests/test_app_service_process_timeline.py backend/tests/test_app_service_schedule_trust.py backend/tests/test_app_service_batch_dispatch.py`
  - 预期信号：全部通过，输出 `24 passed`。
- `npm run lint`
  - cwd: `D:\ProjectPackage\ProductionPlan\fronted`
  - 预期信号：退出码为 0。

## Test Cases

### T1: 后端 provider/runtime 入口回归

- Covers: P1-AC1, P1-AC2, P1-AC3
- Level: unit
- Command: `python -m pytest backend/tests/test_app_service_provider.py`
- Expected: provider 可构造默认 runtime，也可复用显式注入的 runtime。

### T2: 后端 legacy 查询入口回归

- Covers: P3-AC1
- Level: unit
- Command: `python -m pytest backend/tests/test_app_service_process_timeline.py backend/tests/test_app_service_schedule_trust.py`
- Expected: 与 legacy 查询入口直接相关的工序时间线和排产信任口径测试通过。

### T3: 后端分发路径回归

- Covers: P1-AC1, P3-AC1
- Level: unit
- Command: `python -m pytest backend/tests/test_app_service_batch_dispatch.py`
- Expected: 任务分发仍能正确触达 legacy app 服务路径，测试全部通过。

### T4: 前端 legacy app shell 静态校验

- Covers: P2-AC1, P2-AC2, P2-AC3, P3-AC2
- Level: static
- Command: `npm run lint`
- Expected: legacy app shell 拆分后，前端代码通过 lint。

### T5: 测试报告结构校验

- Covers: P3-AC3
- Level: manual
- Command: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id task-61cb339d1c-20260419T011916`
- Expected: `test-report.md` 结构合法，可用于 completion gate。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | backend provider | 默认 runtime 与显式 runtime 注入可用 | unit | P1-AC1, P1-AC2, P1-AC3 | `test-report.md#T1` |
| T2 | backend query entry | legacy 查询入口未被模块化重构打断 | unit | P3-AC1 | `test-report.md#T2` |
| T3 | backend dispatcher | 任务分发路径仍可调用 legacy 服务 | unit | P1-AC1, P3-AC1 | `test-report.md#T3` |
| T4 | frontend legacy shell | App shell 拆分后导入与路由装配有效 | static | P2-AC1, P2-AC2, P2-AC3, P3-AC2 | `test-report.md#T4` |
| T5 | workflow artifacts | 测试报告结构满足 workflow 要求 | manual | P3-AC3 | `test-report.md#T5` |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-runtime
- Required tools: pytest, npm
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: Run against the real repo and installed local dependencies. Do not use mock results, fallback branches, or default-success placeholders.
- Escalation rule: Do not inspect withheld artifacts until the tester has written an initial verdict.

## Pass / Fail Criteria

- Pass when:
  - T1、T2、T3、T4、T5 全部通过。
  - 每个 acceptance id 都有对应测试覆盖与证据。
  - 没有未解释的失败或跳过项。
- Fail when:
  - 任一命令失败。
  - 任一 acceptance id 没有测试覆盖或证据。
  - 为了通过测试新增 fallback、mock 或 silent downgrade。

## Regression Scope

- `backend/app/api/routes/app_queries.py`
- `backend/app/services/job_dispatcher.py`
- `backend/scripts/import_mes_reportings_xlsx.py`
- `backend/scripts/import_balloon_daily_output.py`
- `fronted/src/components/legacy-app-page.tsx`
- `fronted/src/app/[[...slug]]/page.tsx`

## Reporting Notes

测试结果写入 `test-report.md`。每个测试用例必须记录实际命令、结果、证据和最终 verdict。tester 保持独立，不修改产品代码。
