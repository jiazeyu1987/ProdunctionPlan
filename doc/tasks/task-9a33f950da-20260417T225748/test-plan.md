# Test Plan

- Task ID: `task-9a33f950da-20260417T225748`
- Created: `2026-04-17T22:57:48`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `将现有排程重排逻辑扫描结果整理成一份从上到下的开发计划，先定方案，不零碎改点。`

## Test Scope

本测试计划用于验证后续执行阶段是否真正按该开发计划落地，而不是仅在单点报错上打补丁。验证范围包括：

- 概念和数据职责是否已经拆开
- 新旧两条排程管线是否清晰分离
- 锁定和冻结在新模式下是否拥有明确、可测试的语义
- 订单池和排程页的版本口径、事实口径、人工约束口径是否一致

本测试计划不验证：

- ERP 联机同步正确性
- 无关页面的全面 UI 重构
- 与本计划无关的历史乱码或旧接口清理

## Environment

- 平台：Windows，本地工作区 `D:\ProjectPackage\ProductionPlan`
- 后端：Python 3.12+，SQLite，本地 `pytest`
- 前端：Node.js + Next.js，本地 `eslint`
- UI 验证：真实浏览器 Playwright
- 数据要求：
  - 可创建临时 SQLite 测试库
  - 可构造当前排产、存档、锁定单、冻结单、已报工单、未报工单、计划产能和实际产能
- 运行前置：
  - `backend` 依赖已安装
  - `fronted` 依赖已安装
  - Playwright 浏览器二进制可用

## Accounts and Fixtures

- 角色：
  - 排产员 `SCHEDULER`
  - 必要时可读验证车间主任 `WORKSHOP_MANAGER`
- 核心数据夹具：
  - 一张存在当前排产任务的锁定订单
  - 一张未进入当前排产但被锁定的订单
  - 一张未进入当前排产但被冻结的订单
  - 一张已有末道报工、剩余量已变化的订单
  - 一张只存在中间工序报工的订单，用于验证事实边界
  - 至少一组计划产能和实际产能差异数据
  - 一组人工开工窗口与系统排程事实不一致的数据

如果任一核心夹具无法构造，测试人员必须 fail fast 并记录缺失前提。

## Commands

1. 窄回归：模型与约束测试
   - Command:
     - `python -m pytest backend/tests/test_app_service_schedule_trust.py backend/tests/test_app_service_multi_line_schedule.py backend/tests/test_shift_capacity_schedule.py`
   - Expected success signal:
     - 退出码为 0
     - 现有可信排程、固定订单、班次产能相关回归仍通过

2. 新增后端事实重排测试
   - Command:
     - `python -m pytest backend/tests/test_schedule_fact_replan.py backend/tests/test_schedule_fact_constraints.py`
   - Expected success signal:
     - 退出码为 0
     - 能明确区分 legacy 重排与事实重排
     - 锁定/冻结在新模式下的阻断与非阻断行为符合新规则矩阵

3. 前端静态检查
   - Command:
     - `npx eslint --no-ignore src/legacy/features/schedule-calendar/useScheduleCalendarController.js src/legacy/features/schedule-calendar/components/ScheduleCalendarSettingsPanel.jsx src/legacy/features/orders-pool/page/useOrdersPoolPageController.js src/legacy/features/orders-pool/selectors.js src/legacy/features/order-execution/ordersPoolService.js`
   - Expected success signal:
     - 退出码为 0
     - 入口分流、口径文案、订单池排序相关代码无 lint 错误

4. 真实浏览器主链路验证
   - Command:
     - `npx playwright test tests/e2e/production-plan.e2e.spec.ts tests/e2e/orders-pool-trust.e2e.spec.ts`
   - Expected success signal:
     - 退出码为 0
     - 浏览器证据能证明新入口、新口径和订单池顺位符合计划要求

## Test Cases

### T1: 现状入口分流被正确定义

- Covers: P1-AC1, P1-AC2
- Level: integration
- Command: `python -m pytest backend/tests/test_schedule_fact_replan.py -k entry_mode`
- Expected: 初始排产与 legacy 重排的差异由测试明确表达，且事实重排入口不依赖 `base_version_no`。

### T2: 旧口径漂移点被完整收口

- Covers: P1-AC3, P2-AC3
- Level: integration
- Command: `python -m pytest backend/tests/test_schedule_fact_constraints.py -k terminology`
- Expected: `CURRENT/SAVED` 与旧口径的映射在接口层和页面层都可解释，兼容期策略不依赖 silent downgrade。

### T3: 人工窗口与排程事实字段职责分离

- Covers: P2-AC1, P2-AC2
- Level: integration
- Command: `python -m pytest backend/tests/test_schedule_fact_replan.py -k state_window`
- Expected: 人工窗口字段不再被新排程结果直接污染，排程事实改为从结果表或显式导出字段读取。

### T4: 新增事实重排管线不复制旧任务表

- Covers: P3-AC1, P3-AC2
- Level: integration
- Command: `python -m pytest backend/tests/test_schedule_fact_replan.py -k fact_mode`
- Expected: 新模式不依赖旧排程任务作为固定订单源，未来排程只基于事实输入和人工约束生成。

### T5: 新旧两条管线共存且边界稳定

- Covers: P3-AC3
- Level: integration
- Command: `python -m pytest backend/tests/test_schedule_fact_replan.py -k legacy`
- Expected: legacy 重排入口行为保持可用，且新模式不会无意破坏旧模式。

### T6: 锁定与冻结在新模式下的规则矩阵成立

- Covers: P4-AC1, P4-AC2, P4-AC3
- Level: integration
- Command: `python -m pytest backend/tests/test_schedule_fact_constraints.py -k fixed`
- Expected: 新模式下锁定/冻结不再默认等价于“保持旧排位”，缺失锚点时的阻断原因来自新规则，且冲突旧测试已被替换或重写。

### T7: 订单池与排程页口径在真实浏览器中一致

- Covers: P2-AC1, P2-AC2, P2-AC3, P5-AC1
- Level: e2e
- Command: `npx playwright test tests/e2e/orders-pool-trust.e2e.spec.ts`
- Expected: 订单池能区分人工窗口与排程事实，页面能同时说明当前查看方案、当前排产、最近存档等真实口径，且 passing case 附带截图、trace 或视频证据。

### T8: 新模式可通过真实浏览器从当天重排未来

- Covers: P3-AC1, P3-AC2, P5-AC1, P5-AC2, P5-AC3
- Level: e2e
- Command: `npx playwright test tests/e2e/production-plan.e2e.spec.ts -g "fact replan"`
- Expected: 用户可显式选择“按事实从当天重排”，参数变化后可基于事实重算未来，且若新规则要求阻断，页面错误说明必须可操作且可追溯。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | schedule entry | 定义初始排产、legacy 重排、事实重排三种入口边界 | integration | P1-AC1, P1-AC2 | `pytest` 输出 + `execution-log.md` |
| T2 | terminology | 收口 `CURRENT/SAVED` 与旧口径漂移 | integration | P1-AC3, P2-AC3 | `pytest` 输出 + `execution-log.md` |
| T3 | state model | 拆分人工窗口与排程事实字段职责 | integration | P2-AC1, P2-AC2 | `pytest` 输出 + `execution-log.md` |
| T4 | fact replan | 新模式不复制旧任务表，直接基于事实构造输入 | integration | P3-AC1, P3-AC2 | `pytest` 输出 + `execution-log.md` |
| T5 | dual pipeline | legacy 与新模式共存且不互相破坏 | integration | P3-AC3 | `pytest` 输出 + `execution-log.md` |
| T6 | lock/freeze semantics | 新模式下锁定/冻结阻断规则与测试矩阵成立 | integration | P4-AC1, P4-AC2, P4-AC3 | `pytest` 输出 + `execution-log.md` |
| T7 | orders pool UI | 订单池与排程页口径、资源口径和字段职责一致 | e2e | P2-AC1, P2-AC2, P2-AC3, P5-AC1 | 截图 + trace + `test-report.md` |
| T8 | schedule calendar UI | 用户可按事实从当天重排未来，且发布策略可回滚 | e2e | P3-AC1, P3-AC2, P5-AC1, P5-AC2, P5-AC3 | 截图 + trace + `test-report.md` |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: pytest, eslint, playwright
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: 后续执行阶段必须在真实仓库、真实后端测试运行时和真实浏览器中验证；不得用 stub 结果冒充“按事实重排”已成立。
- Escalation rule: 测试人员在给出首轮 verdict 前不得查看 `execution-log.md` 与 `task-state.json`；若 PRD 与实现不一致，再由主代理决定是否开放 withheld artifacts 做差异分析。

## Pass / Fail Criteria

- Pass when:
  - 所有 acceptance ids 至少有一个通过的测试用例覆盖
  - 后端能稳定区分 legacy 重排与事实重排
  - 前端真实浏览器证据证明新入口和新口径可被用户正确理解
  - 发布前检查和回滚策略已被文档化且可执行
- Fail when:
  - 新模式仍然依赖 `base_version_no` 才能工作
  - 人工窗口与系统排程事实仍然混在同一字段职责中
  - 锁定/冻结语义仍然只能靠旧“基准版本缺失”逻辑解释
  - UI 仍然混淆当前排产、当前查看方案和存档口径
  - 任一真实浏览器关键用例缺少非任务工件证据

## Regression Scope

- `backend/tests/test_app_service_schedule_trust.py`
- `backend/tests/test_app_service_multi_line_schedule.py`
- `backend/tests/test_shift_capacity_schedule.py`
- `fronted/tests/e2e/orders-pool-trust.e2e.spec.ts`
- `fronted/tests/e2e/production-plan.e2e.spec.ts`
- `fronted/src/legacy/features/orders-pool/*`
- `fronted/src/legacy/features/schedule-calendar/*`

## Reporting Notes

测试结果写入 `test-report.md`。

报告中必须额外说明以下内容：

- 首轮 verdict 是否在 blind-first-pass 下完成
- 哪些用例验证 legacy 管线
- 哪些用例验证事实重排管线
- 哪些失败属于前置条件缺失，哪些失败属于实现偏差
