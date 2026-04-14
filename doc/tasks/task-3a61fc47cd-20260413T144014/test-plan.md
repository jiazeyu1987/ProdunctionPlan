# Test Plan

- Task ID: `task-3a61fc47cd-20260413T144014`
- Created: `2026-04-13T14:40:14`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `排产看板里的每日产能变化增加成两组，一个是产线，一个是工序；可以选择产线，可以选择工序，展示一段时间之内的工序与产线变化；图表改成折线图；去掉每日产能趋势（计划）的统计。`

## Test Scope

验证排产看板接口是否正确返回按产线和按工序聚合的每日产能变化序列，验证前端是否按要求渲染两个可筛选折线图并移除旧计划趋势图，同时回归 KPI、物料消耗排行和看板中文文案。看板之外的业务流程不在本次专项测试范围内，除非它们与看板数据对账直接耦合。

## Environment

- 工作区：`D:\ProjectPackage\ProductionPlan`
- 前端：Next.js 本地应用，通过仓库现有 Playwright 配置启动
- 后端：仓库内 FastAPI 服务与 E2E 测试数据库
- 浏览器：Playwright 启动的真实 Chromium 会话
- 平台假设：Windows PowerShell，可执行 `npm`、`python` 与 Playwright

## Accounts and Fixtures

- 调度员账号：用于访问 `/dashboard/scheduler`
- 看板测试数据：E2E 数据库中存在可用于订单汇总、每日产能、物料消耗排行的真实数据
- 30 天对账夹具：沿用 `production-plan.e2e.spec.ts` 中的播种逻辑，为固定日期范围写入报工与停机影响数据
- 若上述账号、数据库或播种路径缺失，测试必须立即失败并记录缺失前提

## Commands

- `npm --prefix fronted run lint`
  预期：ESLint 成功退出且无错误
- `npm --prefix fronted run build`
  预期：前端生产构建成功
- `npm --prefix fronted run e2e:playwright -- --grep "T6 scheduler dashboard metrics and charts|T8 scheduler dashboard 30-day correctness reconciliation"`
  预期：排产看板关键 E2E 用例通过，并产出 trace/video/screenshot 等 Playwright 证据
- `npm --prefix fronted run e2e:playwright -- tests/e2e/copy-verification.spec.ts --grep "T1 sidebar dashboard metadata copy"`
  预期：看板文案校验用例通过，并确认标题、图表标签和筛选项为正式中文

## Test Cases

### T1: 看板接口按产线与工序聚合对账

- Covers: P1-AC1, P1-AC2, P1-AC3, P1-AC4, P3-AC1
- Level: e2e
- Command: `npm --prefix fronted run e2e:playwright -- --grep "T8 scheduler dashboard 30-day correctness reconciliation"`
- Expected:
  在 30 天真实播种数据下，独立计算出的按产线和按工序每日产能变化结果与 `/api/dashboard/scheduler` 返回结果逐项一致，且现有汇总指标、物料排行仍可用

### T2: 看板页面双筛选折线图交互

- Covers: P2-AC1, P2-AC2, P2-AC3, P2-AC4, P3-AC2
- Level: e2e
- Command: `npm --prefix fronted run e2e:playwright -- --grep "T6 scheduler dashboard metrics and charts"`
- Expected:
  页面展示“产线每日产能变化”和“工序每日产能变化”两张折线图，存在对应筛选控件，旧“每日产能趋势（计划）”图表不再出现，KPI 与物料排行仍正常显示

### T3: 看板中文文案与无障碍标签校验

- Covers: P2-AC3, P3-AC3
- Level: e2e
- Command: `npm --prefix fronted run e2e:playwright -- tests/e2e/copy-verification.spec.ts --grep "T1 sidebar dashboard metadata copy"`
- Expected:
  看板标题、折线图无障碍标签、筛选项文案和相关页面文案均为正式中文，不出现乱码、英文残留或旧柱状图标签

### T4: 前端静态质量门禁

- Covers: P3-AC4
- Level: build
- Command: `npm --prefix fronted run lint` 与 `npm --prefix fronted run build`
- Expected:
  代码风格检查与生产构建均通过，无新增编译或类型问题

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | 后端聚合与对账 | 30 天范围内按产线、按工序每日变化与接口返回一致 | e2e | P1-AC1, P1-AC2, P1-AC3, P1-AC4, P3-AC1 | `test-report.md` Round 1 + Playwright 证据 |
| T2 | 前端看板交互 | 双筛选折线图渲染、旧图移除、物料排行与 KPI 回归 | e2e | P2-AC1, P2-AC2, P2-AC3, P2-AC4, P3-AC2 | `test-report.md` Round 1 + Playwright 证据 |
| T3 | 文案与可访问性 | 标题、图表标签、筛选项中文化校验 | e2e | P2-AC3, P3-AC3 | `test-report.md` Round 1 + Playwright 证据 |
| T4 | 构建质量 | lint 与生产构建通过 | build | P3-AC4 | `test-report.md` Round 1 |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: playwright, npm, next, python
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: 必须在真实仓库、真实后端和真实浏览器中执行；不得使用静态截图替代交互验证
- Escalation rule: 在测试者给出首轮结论前，不查看 `execution-log.md` 与 `task-state.json`

## Pass / Fail Criteria

- Pass when:
  所有测试命令通过，接口对账与 UI 展示满足预期，且每个通过的浏览器用例都在 `test-report.md` 中引用实际证据文件
- Fail when:
  任一验收项未被覆盖、关键命令失败、浏览器证据缺失，或看板仍出现旧计划趋势图、乱码、英文残留、错误聚合结果

## Regression Scope

- 排产看板 KPI 卡片展示
- 物料消耗排行图表与表格
- 排产看板日期范围与 Top N 筛选行为
- 调度员访问 `/dashboard/scheduler` 的权限与路由可用性

## Reporting Notes

测试结果写入 `test-report.md`。每个用例需要记录命令、结果、覆盖的 acceptance id、证据路径和最终结论。
