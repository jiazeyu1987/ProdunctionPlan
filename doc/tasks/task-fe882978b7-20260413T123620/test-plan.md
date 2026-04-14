# Test Plan

- Task ID: `task-fe882978b7-20260413T123620`
- Created: `2026-04-13T12:36:20`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `修改当前前端里的乱码问题、描述不正式问题，以及英文未转换为中文的问题`

## Test Scope

验证当前前端在真实浏览器中的关键文案是否保持正式中文，重点覆盖排产日历模拟提示、当日产能报工校验提示，以及已经存在的页面级中文文案回归。

不在本计划中覆盖：

- 后端提示语生成逻辑变更
- 非本次范围的页面重构
- 与文案无关的复杂业务算法正确性

## Environment

- 工作目录：`D:\ProjectPackage\ProductionPlan`
- 前端：`npm run dev`，目录 `fronted`
- 后端：`python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`，目录 `backend`
- Playwright 基础地址：`http://127.0.0.1:2798`
- 后端基础地址：`http://127.0.0.1:8000`
- 数据库：`backend/data/e2e/production_plan.e2e.db`
- 备份目录：`backend/data/e2e/backups`

## Accounts and Fixtures

- 使用 `tests/e2e/support/constants` 中的 `ACCOUNTS.scheduler` 账号登录。
- 使用 Playwright 配置中预置的 e2e 数据库与备份目录。
- 若账号、数据库或备份目录缺失，测试必须立即失败并在 `test-report.md` 记录缺失前置条件。

## Commands

- `npm --prefix fronted run lint`
  预期：命令退出码为 0。
- `npm --prefix fronted run build`
  预期：命令退出码为 0，Next.js 构建成功。
- `npm --prefix fronted exec playwright test tests/e2e/copy-verification.spec.ts --reporter=list`
  预期：文案回归相关用例全部通过，并生成 trace/video/html 报告证据。
- `npm --prefix fronted exec playwright test tests/e2e/simulation-calendar.e2e.spec.ts --reporter=list`
  预期：连续推进 5 次并重置模拟的用例通过，且提示语为中文。

## Test Cases

### T1: 页面级中文文案回归

- Covers: P1-AC3, P2-AC1
- Level: e2e
- Command:
  `npm --prefix fronted exec playwright test tests/e2e/copy-verification.spec.ts --reporter=list`
- Expected:
  登录后，侧边栏、排产看板、当日产能、业务接口验证页和排产日历页均展示中文且正式的关键文案，不出现英文标签或乱码。

### T2: 当日产能报工校验提示中文化

- Covers: P1-AC2, P2-AC1
- Level: e2e
- Command:
  `npm --prefix fronted exec playwright test tests/e2e/copy-verification.spec.ts --reporter=list`
- Expected:
  在当日产能页打开任一报工输入框并提交无效数量时，错误提示为正式中文，不出现 `report_qty` 或英文句式。

### T3: 排产日历模拟推进与重置中文提示

- Covers: P1-AC1, P2-AC2
- Level: e2e
- Command:
  `npm --prefix fronted exec playwright test tests/e2e/simulation-calendar.e2e.spec.ts --reporter=list`
- Expected:
  在排产日历页连续点击“推进一天”5 次后，模拟日期推进 5 天，提示语为中文；点击“重置模拟”后，日期恢复到基线日期，提示语仍为中文，相关报工副作用计数恢复。

### T4: 静态检查与生产构建回归

- Covers: P2-AC3
- Level: build
- Command:
  `npm --prefix fronted run lint`
  `npm --prefix fronted run build`
- Expected:
  lint 与构建均成功，无新增语法、类型或打包错误。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | 页面级文案 | 侧边栏、看板、当日产能、业务接口验证、排产日历关键中文文案回归 | e2e | P1-AC3, P2-AC1 | Playwright trace/video/html + `test-report.md` |
| T2 | 当日产能 | 无效报工数量提示使用正式中文且不暴露内部字段名 | e2e | P1-AC2, P2-AC1 | Playwright trace/video/html + `test-report.md` |
| T3 | 排产日历 | 推进 5 次并重置模拟，验证日期、副作用与中文提示 | e2e | P1-AC1, P2-AC2 | Playwright trace/video/html + `test-report.md` |
| T4 | 构建回归 | lint 与 build 通过 | build | P2-AC3 | 命令输出摘要 + `test-report.md` |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: playwright, npm, node, python, uvicorn
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: 使用真实前后端进程、真实浏览器与现有 e2e 数据库运行，不允许使用 mock 页面或伪造提示结果。
- Escalation rule: 在初次结论完成前，不查看 `execution-log.md` 和 `task-state.json`。

## Pass / Fail Criteria

- Pass when:
  所有命令成功；T1-T4 全部通过；关键提示文案在浏览器中为中文且正式。
- Fail when:
  任一命令失败；浏览器中仍出现英文提示、乱码、内部字段名；推进/重置模拟后的日期或副作用不符合预期。

## Regression Scope

- 排产日历页面的版本刷新与提示条展示。
- 当日产能页面的报工提交流程与错误提示展示。
- 现有文案回归用例已经覆盖的排产看板、业务接口验证和排产日历标题文案。

## Reporting Notes

结果写入 `test-report.md`。

测试人员必须保持独立，不修改产品代码；每个通过的浏览器用例都需要在 `test-report.md` 中引用至少一个 Playwright 证据文件。
