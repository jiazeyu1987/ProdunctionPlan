# Test Plan

- Task ID: `e2e-5-20260412T165342`
- Created: `2026-04-12T16:53:42+08:00`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `使用 e2e 测试点击推进一天 5 次并验证结果，再点击重置模拟并验证是否符合预期`

## Test Scope

必须验证：

- 排产员可以在月历页真实点击“推进一天”按钮 5 次。
- 每次点击后，页面当前日高亮与成功消息都反映了正确的推进结果。
- 推进操作带来的至少一种后端副作用真实发生且可观测。
- 点击“重置模拟”后，页面当前日高亮回到推进前基线，且上述后端副作用恢复到基线。
- 最终给出“当前实现是否符合预期”的明确结论，并附上具体日期。

本次不覆盖：

- 完整重排、发布、报工主流程回归。
- 车间主任角色权限验证。
- 与模拟功能无直接关系的页面文案或样式问题。

## Environment

- 操作系统：Windows PowerShell
- 前端真实浏览器运行器：
  - `fronted/scripts/run-e2e-browser.mjs`
- 浏览器验证面：
  - Playwright Chromium
- 隔离数据库：
  - `fronted/test-results/e2e/runtime/production_plan.e2e.db`
- 隔离备份/运行目录：
  - `fronted/test-results/e2e/runtime/*`
- 前后端启动方式：
  - 由 `fronted/playwright.config.ts` 的 `webServer` 自动启动真实 backend 与 frontend

成功信号：

- 目标命令退出码为 0。
- `fronted/test-results/e2e/evidence-manifest.json` 中存在本任务对应 case。
- 对应截图与 trace 文件真实存在。

## Accounts and Fixtures

- 排产员账号：
  - `scheduler_e2e / Passw0rd!`
- E2E 种子库应将模拟当前日期初始化为固定基线：
  - `2026-04-10`
- 若运行时实际页面初始高亮日期与种子基线不一致，测试必须记录实际观测值并用该观测值推导后续预期；不能静默忽略。

如果任一账号、种子库或浏览器运行时缺失，tester 必须 fail fast 并记录阻塞项。

## Commands

静态与构建检查：

```powershell
npm --prefix fronted run lint
npm --prefix fronted run build
```

预期：命令退出码为 0。

真实浏览器目标验证：

```powershell
npm --prefix fronted run e2e:browser -- --grep "simulation advance"
```

预期：

- 目标用例通过。
- 浏览器 evidence manifest、截图、trace 产物生成。

如目标用例新增到现有 spec 中，也允许使用更精确的 grep：

```powershell
npm --prefix fronted run e2e:browser -- --grep "advance one day 5 times and reset simulation"
```

## Test Cases

### T1: Advance One Day Five Times From The Calendar UI

- Covers: P1-AC1, P2-AC1, P2-AC2
- Level: e2e
- Command: `npm --prefix fronted run e2e:browser -- --grep "simulation advance"`
- Expected: 浏览器登录排产员后进入 `/schedule/calendar`，从当前日高亮单元格读取基线日期；连续点击“推进一天”5次后，每一步都显示成功消息，且当前日高亮依次推进到基线+1、+2、+3、+4、+5 天。

### T2: Reset Simulation Restores Baseline Date And Side Effects

- Covers: P1-AC2, P1-AC3, P2-AC1, P2-AC2
- Level: e2e
- Command: `npm --prefix fronted run e2e:browser -- --grep "simulation advance"`
- Expected: 在 T1 完成后点击“重置模拟”，页面显示重置成功；当前日高亮回到推进前基线日期；推进过程中增长的副作用数据（如 work reports 数量）回到推进前基线。

### T3: No Silent Downgrade If The Flow Deviates From Expected Dates

- Covers: P2-AC3
- Level: e2e
- Command: `npm --prefix fronted run e2e:browser -- --grep "simulation advance"`
- Expected: 如果任一步推进日期不连续、重置未回到基线、或副作用未恢复，则测试直接失败并输出具体日期差异，不允许以模糊提示或跳过断言的方式“通过”。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | 月历页模拟推进 | 连续点击推进一天 5 次并校验日期推进 | e2e | P1-AC1, P2-AC1, P2-AC2 | `fronted/test-results/e2e/evidence-manifest.json` + screenshot + trace |
| T2 | 月历页模拟重置 | 重置后日期与副作用恢复到基线 | e2e | P1-AC2, P1-AC3, P2-AC1, P2-AC2 | `fronted/test-results/e2e/evidence-manifest.json` + screenshot + trace |
| T3 | 失败可见性 | 日期或副作用不符时直接失败并给出具体差异 | e2e | P2-AC3 | Playwright failure output / trace |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: playwright, python, npm
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: 必须运行真实前后端与真实浏览器，不允许以 API 单测或假数据替代页面点击验证；通过页面高亮、成功消息和浏览器证据文件回答“是否符合预期”。
- Escalation rule: Do not inspect withheld artifacts until the tester has written an initial verdict or the main agent explicitly asks for discrepancy analysis.

## Pass / Fail Criteria

- Pass when:
  - 目标浏览器用例通过。
  - 连续 5 次推进的日期全部符合预期。
  - 重置后日期恢复到基线。
  - 副作用数据在推进后变化、重置后恢复。
  - 证据文件存在且可复核。
- Fail when:
  - 任一步推进日期不符合预期。
  - 重置后仍停留在推进后的日期，或未回到基线。
  - 副作用数据无法证明“推进后变化、重置后恢复”。
  - 目标命令失败，或没有产生真实浏览器证据。

## Regression Scope

- 月历页既有重排/发布入口不能被本次模拟用例破坏。
- 既有 browser evidence manifest 结构不能被破坏。
- `fronted/tests/e2e/support/evidence.ts` 的证据收集逻辑仍需兼容已有用例。

## Reporting Notes

结果写入 `test-report.md` 时必须包含：

- 实际运行命令
- 实际基线日期
- 连续 5 次推进后的最终日期
- 重置后的恢复日期
- 推进前/推进后/重置后的副作用观测值
- 截图、trace、manifest 路径

tester 必须保持独立，不得修改产品代码或 `task-state.json`。
