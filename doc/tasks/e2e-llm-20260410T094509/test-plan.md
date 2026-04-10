# Test Plan

- Task ID: `e2e-llm-20260410T094509`
- Created: `2026-04-10T09:45:09`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `针对当前生产排期系统实现一套尽量全面的 E2E 测试，覆盖从重排到报工的完整流程，并加入 LLM 评测判断系统行为是否符合要求。`

## Test Scope

- 验证隔离 E2E 数据库、真实后端 API、真实前端壳与真实浏览器交互的闭环。
- 覆盖排产员与车间主任两个角色的关键业务路径。
- 重点验证以下系统能力：
  - 排产版本生成与发布
  - 当日产能维护与审计记录
  - 报工写入与当日实际产能回写
  - 订单汇总统计
  - 生产订单页的基础可见性与排产结果联动
  - LLM 对浏览器证据和系统要求的独立评测
- 不在本测试计划内：ERP 联机刷新能力、文件导入外部系统联调、与当前任务无关的历史页面重构。

## Environment

- OS: Windows + PowerShell
- Backend runtime: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Frontend runtime: `next dev --hostname 127.0.0.1 --port 2798`
- Database: 仅允许使用 `backend/data/e2e/production_plan.e2e.db` 或同等隔离路径
- Required local auth/runtime for full run:
  - `codex` CLI 已安装，并可在本机默认全局 npm 位置调用
  - `codex login status` 返回可用的本机登录态
  - 当前本机 Codex provider 可完成结构化评测请求，而不是仅能执行极小探针
- Not used by this task: `OPENAI_API_KEY`, `OPENAI_MODEL`
- Browser: Playwright Chromium
- Validation surface: real-browser
- 平台假设：本地允许启动前后端进程，并可写入 `fronted/test-results/` 与 `backend/data/e2e/`

## Accounts and Fixtures

- 排产员账号：`scheduler_e2e / Passw0rd!`
- 车间主任账号：`manager_e2e / Passw0rd!`
- 固定业务数据要求：
  - 至少 2 张待排生产订单，覆盖同一产品的多道工序
  - 至少 1 条车间产线和对应工序拓扑
  - 车间主任具备单条产线范围权限
  - 存在可用于生成版本、发布、修改当日产能、查看审计、执行报工、查看汇总的完整数据链
- 若账号、权限、种子库、Codex 登录态 / provider 或浏览器缺失或失效，测试必须 fail fast 并记录阻塞项。

## Commands

1. 初始化隔离测试库
   - Command: `python backend/scripts/seed_e2e_db.py --output backend/data/e2e/production_plan.e2e.db --force`
   - Expected success signal: 命令退出码为 `0`，输出包含生成的数据库路径、账号信息和关键数据摘要。

2. 安装浏览器依赖
   - Command: `cd fronted; npx playwright install chromium`
   - Expected success signal: Chromium 安装成功，无报错退出。

3. 执行仅浏览器 E2E
   - Command: `cd fronted; npm run e2e:browser`
   - Expected success signal: Playwright 全部用例通过，并在 `fronted/test-results/` 下生成截图、trace 和结构化 evidence manifest。

4. 执行完整浏览器 + LLM 评测
   - Command: `cd fronted; npm run e2e`
   - Expected success signal: 浏览器用例全部通过，随后生成 `codex-eval-prompt.txt`、`codex-eval-schema.json`、`codex-eval-output.json`、`llm-verdict.json` 且 verdict 为 pass；若本机 Codex provider 连续返回 `503 Service Unavailable` / `No available providers`，命令必须明确失败。

5. 校验测试报告结构
   - Command: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id e2e-llm-20260410T094509`
   - Expected success signal: 结构校验通过，无缺失 case/result/evidence 错误。

6. 任务完成校验
   - Command: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\check_completion.py --cwd D:\ProjectPackage\ProductionPlan --task-id e2e-llm-20260410T094509 --apply`
   - Expected success signal: 所有 acceptance ids 与测试状态满足完成门禁。

## Test Cases

### T1: 隔离数据库和固定账号可启动

- Covers: P1-AC1, P1-AC2
- Level: integration
- Command: `python backend/scripts/seed_e2e_db.py --output backend/data/e2e/production_plan.e2e.db --force`
- Expected: 成功创建独立测试库；固定账号、产线、工艺、订单和权限写入完成；不会触碰用户当前数据库。

### T2: 排产员完整跑通重排到报工

- Covers: P1-AC3, P2-AC1
- Level: e2e
- Command: `cd fronted; npm run e2e:browser -- --grep "scheduler full flow"`
- Expected: 排产员登录后可生成草稿版本并发布；修改当日产能后产生审计记录；提交报工后当日实际产能和订单汇总发生符合预期的更新。

### T3: 排产员覆盖生产订单和汇总相邻页面

- Covers: P2-AC2
- Level: e2e
- Command: `cd fronted; npm run e2e:browser -- --grep "scheduler adjacent coverage"`
- Expected: 生产订单页能看到种子订单与排产联动结果；订单汇总页能看到报工聚合结果；关键页面无权限或数据错乱问题。

### T4: 车间主任权限范围和报工约束

- Covers: P2-AC2
- Level: e2e
- Command: `cd fronted; npm run e2e:browser -- --grep "workshop manager scope"`
- Expected: 车间主任只能看到被授权的产线能力与报工范围，且能在授权范围内提交报工并看到对应记录。

### T5: 浏览器证据产出完整

- Covers: P2-AC3
- Level: e2e
- Command: `cd fronted; npm run e2e:browser`
- Expected: 每个通过的浏览器 case 至少生成一个真实证据文件，并写入结构化 evidence manifest，供 LLM 评测与测试报告引用。

### T6: LLM 评测严格校验完整 E2E 结果

- Covers: P3-AC1, P3-AC2
- Level: e2e
- Command: `cd fronted; npm run e2e`
- Expected: 主入口先执行浏览器用例，再执行 Codex LLM 评测；当本机 Codex provider 不可用并连续返回 `503 Service Unavailable` 时命令立即失败；当证据满足要求时输出机器可读 pass verdict，否则输出 fail verdict。

### T7: Workflow 证据和完成门禁闭环

- Covers: P4-AC1, P4-AC2
- Level: review
- Command: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id e2e-llm-20260410T094509`，随后执行 `check_completion.py --apply`
- Expected: 所有 acceptance ids 在 `execution-log.md` 与 `test-report.md` 有证据引用，且只有浏览器 E2E 与 LLM 评测通过时才能进入完成态。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | Seed / Runtime | 生成隔离 SQLite 测试库和固定账号 | integration | P1-AC1, P1-AC2 | seed stdout, DB assertions |
| T2 | Schedule + Capacity + Audit + Reporting | 排产员完整跑通重排到报工闭环 | e2e | P1-AC3, P2-AC1 | screenshot, trace, evidence manifest |
| T3 | Orders Pool + Order Summary | 排产员验证相邻高价值页面结果一致性 | e2e | P2-AC2 | screenshot, trace, evidence manifest |
| T4 | Role Scope | 车间主任权限范围与报工约束 | e2e | P2-AC2 | screenshot, trace, evidence manifest |
| T5 | Evidence | 浏览器证据与结构化清单生成 | e2e | P2-AC3 | manifest JSON, screenshot paths |
| T6 | LLM Evaluation | 浏览器证据驱动的 LLM 独立评测 | e2e | P3-AC1, P3-AC2 | verdict JSON, run log |
| T7 | Workflow Gate | 测试报告与 completion gate 校验 | review | P4-AC1, P4-AC2 | validate_test_report output, completion output |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: playwright, python, node, npm, codex
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: tester 必须在真实前后端运行时与真实浏览器中执行，不允许以 API mock、DOM 注入或伪造结果代替。
- Escalation rule: tester 首轮给出初始结论前不得查看 `execution-log.md` 和 `task-state.json`；只有在需要做差异分析时才允许解锁。

## Pass / Fail Criteria

- Pass when:
  - 隔离种子库创建成功。
  - 真实浏览器用例全部通过。
  - 每个通过的浏览器 case 都有真实证据文件。
  - Codex LLM 评测返回机器可读 pass verdict。
  - `validate_test_report.py` 和 `check_completion.py --apply` 通过。
- Fail when:
  - 任意前置条件缺失。
  - 浏览器或后端任一路径无法真实执行。
  - 关键业务断言与系统要求不一致。
  - Codex 登录态不可用、provider 不可用、评测缺失、被跳过、或 verdict 非 pass。
  - 测试报告结构无效或 completion gate 失败。

## Regression Scope

- 登录/鉴权与 Bearer token 透传。
- 异步 job 创建、轮询与最终状态处理。
- 排产版本列表、任务查询、发布状态切换。
- 当日产能计划/实际值/审计记录。
- 报工记录增删、订单汇总聚合、车间主任产线权限过滤。
- 生产订单页与已排任务窗口联动。

## Reporting Notes

- 所有测试结果写入 `doc/tasks/e2e-llm-20260410T094509/test-report.md`。
- 浏览器原始证据写入 `fronted/test-results/` 下的非任务工件目录。
- Codex prompt、schema、log、output 与最终 LLM verdict 都输出到 `fronted/test-results/e2e/`，并在测试报告中引用绝对或可解析路径。
- tester 保持独立，不修复产品代码，只报告结果。

