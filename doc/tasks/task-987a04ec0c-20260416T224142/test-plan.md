# Test Plan

- Task ID: `task-987a04ec0c-20260416T224142`
- Created: `2026-04-16T22:41:42`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `手工指定“夜班开工”必须真的参与排程；系统不能自动把延期“洗掉”；“当前查看版本”和“正式发布版本”必须彻底分开；资源口径必须分清“候选资源”和“已落定资源”；手工调整开工时间后必须明确展示对正式版、冲突、延期、重排的真实后果；订单池优先级必须和真实排程顺序一致，优先级、锁单、冻结、手工开工窗口必须真正进入排序逻辑。`

## Test Scope

验证本次排程可信度收口是否同时满足后端行为和前端呈现两条链路：

- 后端必须真实使用手工夜班开工约束，保留原承诺交期，并暴露必然延期与保存影响。
- 订单池接口和 UI 必须一致区分当前查看版、正式执行版、草稿版，以及候选资源和已落定资源。
- 订单池排序必须反映排程算法真正尊重的人工决策。

以下内容不在本次测试范围：

- 全量 ERP 同步、部署、报工闭环回归。
- 与本次可信度收口无关的历史乱码清理。

## Environment

- OS: Windows
- Python: 使用当前仓库已有 Python 运行环境
- Frontend: `fronted` 目录依赖已安装
- Validation surface: real-browser
- Required tools: pytest, playwright, npm
- Startup assumptions:
  - 后端测试通过临时 SQLite 数据库独立运行，不依赖外部服务。
  - 前端 Playwright 用例可采用仓库现有的接口 stub 方式，或在真实本地运行态下执行；无论采用哪种方式，都必须保留可追溯浏览器证据。

## Accounts and Fixtures

- 后端测试使用仓库中的 SQLite 初始化与测试夹具。
- 前端浏览器验证使用仓库现有 `SCHEDULER` 角色 stub 登录方式。
- 若需要新增前端验证用例，应使用最小 stub 数据同时覆盖：
  - 手工夜班开工影响提示
  - 当前查看版 / 正式执行版 / 草稿版摘要
  - 候选资源 / 已落定资源分离展示
  - 订单池顺位变化

若上述任一夹具或工具缺失，测试必须 fail fast 并记录缺失项。

## Commands

1. `python -m pytest backend/tests/test_app_service_schedule_trust.py -q`
   Expected success signal: 排程可信度相关后端测试全部通过，覆盖夜班开工、必然延期、保存影响。
2. `python -m pytest backend/tests/test_app_service_order_pool.py -q`
   Expected success signal: 订单池状态、版本口径、资源口径相关后端测试全部通过。
3. `npm --prefix fronted run e2e:playwright -- --grep "orders pool trust|orders pool process columns|schedule calendar"`
   Expected success signal: 相关浏览器用例通过，并产出 trace/video/screenshot 等证据。
4. 如第 3 步没有现成覆盖且本次实现新增了用例：
   `npm --prefix fronted run e2e:playwright -- fronted/tests/e2e/<new-spec>.spec.ts`
   Expected success signal: 新增可信度校验用例通过，并产出证据文件。

## Test Cases

### T1: 夜班开工真正进入排程

- Covers: P1-AC1
- Level: integration
- Command: `python -m pytest backend/tests/test_app_service_schedule_trust.py -q`
- Expected: 订单存在手工夜班开工窗口时，生成排程的首个任务日期与班次与手工约束一致，不退回白班。

### T2: 必然延期不被洗掉

- Covers: P1-AC2, P1-AC3
- Level: integration
- Command: `python -m pytest backend/tests/test_app_service_schedule_trust.py -q`
- Expected: 手工开工已晚于承诺交期时，系统保留原承诺交期，标记必然延期，并在保存影响中给出延期/冲突/重排提示。

### T3: 订单池接口区分版本与资源口径

- Covers: P2-AC1, P2-AC3
- Level: integration
- Command: `python -m pytest backend/tests/test_app_service_order_pool.py -q`
- Expected: 订单池接口返回当前查看版、正式执行版、草稿版相关字段，并区分候选资源与已落定资源。

### T4: 页面统一展示版本摘要

- Covers: P2-AC1, P2-AC2
- Level: e2e
- Command: `npm --prefix fronted run e2e:playwright -- --grep "orders pool trust|schedule calendar"`
- Expected: 订单池与排产日历页面均能同时显示当前查看版、正式执行版和草稿版，并且术语一致、不混口径。

### T5: 页面明确区分候选资源与已落定资源

- Covers: P2-AC3
- Level: e2e
- Command: `npm --prefix fronted run e2e:playwright -- --grep "orders pool trust|orders pool process columns"`
- Expected: 订单详情资源区域明确区分候选资源与已落定资源，提示语说明“可排到”不代表“已排到”。

### T6: 订单池顺位与排程人工决策一致

- Covers: P3-AC1, P3-AC2, P3-AC3
- Level: e2e
- Command: `npm --prefix fronted run e2e:playwright -- --grep "orders pool trust"`
- Expected: 当测试数据调整优先级、锁单、冻结或手工开工窗口时，订单池顺位按同样的人工决策变化，且与当前查看版的排程先后不冲突。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | Scheduling engine | 手工夜班开工真正进入排程首任务 | integration | P1-AC1 | `pytest` 输出 + `execution-log.md` |
| T2 | Order patch + risk surfacing | 必然延期保留原交期并在保存影响中暴露 | integration | P1-AC2, P1-AC3 | `pytest` 输出 + `execution-log.md` |
| T3 | Order pool API | 接口同时返回版本与资源分离字段 | integration | P2-AC1, P2-AC3 | `pytest` 输出 + `execution-log.md` |
| T4 | Orders pool + schedule calendar UI | 两个页面统一展示当前查看版/正式执行版/草稿版 | e2e | P2-AC1, P2-AC2 | Playwright trace/video/screenshot + `test-report.md` |
| T5 | Orders pool detail UI | 候选资源与已落定资源明确分离 | e2e | P2-AC3 | Playwright trace/video/screenshot + `test-report.md` |
| T6 | Orders pool ordering | 顺位受优先级、锁单、冻结、手工开工窗口驱动 | e2e | P3-AC1, P3-AC2, P3-AC3 | Playwright trace/video/screenshot + `test-report.md` |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: pytest, playwright, npm
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: 使用当前真实仓库；后端通过真实测试运行时验证，前端通过真实浏览器会话或仓库既有 Playwright stub 会话验证，并保留具体证据文件。
- Escalation rule: 在 tester 产出首轮结论前，不读取 `execution-log.md` 与 `task-state.json`。

## Pass / Fail Criteria

- Pass when:
  - `T1-T3` 全部通过。
  - `T4-T6` 中与实际改动范围相关的浏览器用例全部通过，并能提供证据文件。
  - 版本口径、资源口径、保存影响和顺位逻辑不再出现与用户诉求相反的表现。
- Fail when:
  - 任何一条 acceptance id 没有被测试覆盖。
  - 系统仍然会把夜班开工排回白班、洗掉延期、混淆版本/资源口径，或订单池顺位继续与排程逻辑冲突。
  - 浏览器验证缺少可追溯证据文件。

## Regression Scope

- 订单池筛选、详情切换、批量锁单/解锁/提优先级操作。
- 排产日历版本切换、发布草稿和版本对比入口。
- 已存在的订单详情工序时序与资源展示流程。
- 任何依赖 `schedule_versions` / `schedule_tasks` / `order_pool_state` 的前端映射。

## Reporting Notes

- 将后端测试结果、浏览器证据路径、失败项与最终结论写入 `test-report.md`。
- 若浏览器验证因环境缺失无法执行，必须在 `test-report.md` 中写明缺失的工具或运行前提，不能用口头推断代替结果。
