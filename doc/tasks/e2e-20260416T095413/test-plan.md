# Test Plan

- Task ID: `e2e-20260416T095413`
- Created: `2026-04-16T09:54:13`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `补全缺失的E2E测试用例`

## Test Scope

验证新增的 Playwright 用例是否真实覆盖当前缺失的两个页面：

- `/schedule/lite` 的页面可达性、关键工具栏操作、快照持久化与读取链路。
- `/test` 的页面可达性、tab 切换与无需外部系统即可触发的本地校验。

以下内容明确不在本次测试计划范围内：

- 真实 ERP、K3、库存服务的外部集成成功链路。
- 所有历史未覆盖路由的全面回归。
- 对旧有 stub 型用例进行架构性重写。

## Environment

- 平台：Windows，本机仓库根目录 `D:\ProjectPackage\ProductionPlan`
- 前端：`fronted`，Next.js + React Router 承载遗留页面
- 后端：`backend`，FastAPI / Uvicorn
- 浏览器：Playwright 默认 Chromium
- 基础地址：
- 前端 `http://127.0.0.1:2798`
- 后端 `http://127.0.0.1:8000`
- 启动方式：使用仓库已有 `fronted/playwright.config.ts` 的 `webServer` 自动启动前后端。
- 本次任务的 UI 验证必须在真实浏览器中执行。
- `/schedule/lite` 测试前应清理 `liteScheduler.scenario.v1` 与 `liteScheduler.scenario.snapshots.v1` 对应 `localStorage`，避免历史脏数据污染。

## Accounts and Fixtures

- 调度员账号：`scheduler_e2e / Passw0rd!`
- 车间主任账号：本任务预计无需使用
- 轻量排产页使用浏览器本地状态，无需后端种子数据即可完成主要页面级交互验证。
- `/test` 页本次仅验证页面与本地校验分支，不依赖外部 ERP 凭据。

如果上述账号、浏览器、前后端启动链路或 Playwright 不可用，测试必须 fail fast 并在 `test-report.md` 中记录缺失前提。

## Commands

- `npm --prefix fronted run e2e:playwright -- tests/e2e/lite-scheduler.e2e.spec.ts`
- 期望：退出码 0，生成对应 HTML report、trace、screenshot。
- `npm --prefix fronted run e2e:playwright -- tests/e2e/test-tools.e2e.spec.ts`
- 期望：退出码 0，生成对应 HTML report、trace、screenshot。
- `npm --prefix fronted run e2e:playwright -- tests/e2e/lite-scheduler.e2e.spec.ts tests/e2e/test-tools.e2e.spec.ts`
- 期望：退出码 0，两个新增 spec 可在同一命令下稳定通过。
- `npm --prefix fronted run e2e:playwright -- tests/e2e/simulation-calendar.e2e.spec.ts`
- 期望：退出码 0，证明邻近 `/schedule/*` 关键回归未被新增改动破坏。

## Test Cases

### T1: Lite scheduler route and toolbar smoke

- Covers: P1-AC1
- Level: e2e
- Command: `npm --prefix fronted run e2e:playwright -- tests/e2e/lite-scheduler.e2e.spec.ts -g "T1"`
- Expected: 登录后进入 `/schedule/lite`，页面展示工具栏、排产模式区域、四个主 tab，并可见核心操作按钮。

### T2: Lite scheduler snapshot persistence flow

- Covers: P1-AC2, P1-AC3
- Level: e2e
- Command: `npm --prefix fronted run e2e:playwright -- tests/e2e/lite-scheduler.e2e.spec.ts -g "T2"`
- Expected: 真实浏览器中完成关键操作链并验证 `localStorage` 与 UI 状态一致，至少覆盖保存场景和读取场景。

### T3: Test tools route and tab switching

- Covers: P2-AC1, P2-AC2
- Level: e2e
- Command: `npm --prefix fronted run e2e:playwright -- tests/e2e/test-tools.e2e.spec.ts -g "T1"`
- Expected: 登录后进入 `/test`，四个 tab 可见且切换后对应面板内容发生变化。

### T4: Test tools local validation without external ERP

- Covers: P2-AC3
- Level: e2e
- Command: `npm --prefix fronted run e2e:playwright -- tests/e2e/test-tools.e2e.spec.ts -g "T2"`
- Expected: 至少两个输入分支在不请求真实外部系统的前提下展示明确错误提示或空态，且页面不崩溃、不静默成功。

### T5: Added specs pass under repo Playwright runner

- Covers: P3-AC1
- Level: e2e
- Command: `npm --prefix fronted run e2e:playwright -- tests/e2e/lite-scheduler.e2e.spec.ts tests/e2e/test-tools.e2e.spec.ts`
- Expected: 新增两个 spec 在仓库标准 runner 下同时通过，并生成 Playwright 报告产物。

### T6: Schedule regression remains passing

- Covers: P3-AC2
- Level: e2e
- Command: `npm --prefix fronted run e2e:playwright -- tests/e2e/simulation-calendar.e2e.spec.ts`
- Expected: 既有 `/schedule/calendar` 回归用例保持通过，证明新增覆盖未破坏相邻排程页面。

### T7: Task artifacts capture execution evidence

- Covers: P3-AC3
- Level: manual
- Command: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id e2e-20260416T095413`
- Expected: `test-report.md` 结构合法，且记录了新增用例、执行命令、结果与真实证据文件引用；`execution-log.md` 中存在对应 phase 记录。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | lite scheduler | 页面可达与工具栏/主 tab 渲染 | e2e | P1-AC1 | Playwright trace + screenshot |
| T2 | lite scheduler | 关键操作链与 `localStorage` 持久化/读取 | e2e | P1-AC2, P1-AC3 | Playwright trace + screenshot |
| T3 | test tools | `/test` 页面可达与四个 tab 切换 | e2e | P2-AC1, P2-AC2 | Playwright trace + screenshot |
| T4 | test tools | 无外部系统依赖的本地校验分支 | e2e | P2-AC3 | Playwright trace + screenshot |
| T5 | Playwright runner | 新增 spec 接入仓库标准运行方式 | e2e | P3-AC1 | HTML report + trace |
| T6 | schedule regression | 相邻排程回归保持通过 | e2e | P3-AC2 | HTML report + trace |
| T7 | task artifacts | 任务工件记录执行结果与证据 | manual | P3-AC3 | validate_test_report output + artifact refs |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: playwright
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: 在真实浏览器与真实本地运行时中执行；对 UI 路径必须提供至少一个截图或 trace 作为外部证据。
- Escalation rule: 初次判定前不得查看 `execution-log.md` 与 `task-state.json`；如出现 PRD 与实测不一致，再由主代理决定是否开放 withheld artifacts 做差异分析。

## Pass / Fail Criteria

- Pass when:
- `T1` 到 `T6` 全部通过，或仅因计划中明确允许跳过的外部前提缺失而 fail fast 记录。
- 新增 spec 在标准 Playwright runner 下稳定通过并留下证据。
- 每个 acceptance id 至少被一个测试用例覆盖并在 `test-report.md` 中有结果记录。

- Fail when:
- `/schedule/lite` 或 `/test` 仍无新增真实浏览器 E2E。
- 新增用例仅做元素存在性检查，没有验证副作用或状态变化。
- 测试依赖 mock/fallback 才能宣称通过。
- 关键命令失败且无明确阻断前提记录。

## Regression Scope

- `/schedule/calendar` 相关回归：`simulation-calendar.e2e.spec.ts`
- Playwright 登录流程与证据采集：`fronted/tests/e2e/support/ui.ts`、`fronted/tests/e2e/support/evidence.ts`
- 若为新增定位点调整了页面组件，还需关注 `/dashboard/scheduler` 与 `/masterdata` 现有用例不应受影响

## Reporting Notes

结果写入 `doc/tasks/e2e-20260416T095413/test-report.md`。

测试人员必须保持独立，不得在测试阶段修改 product code；通过用例必须引用 `fronted/test-results/` 下真实存在的 screenshot、trace 或 report 产物。
