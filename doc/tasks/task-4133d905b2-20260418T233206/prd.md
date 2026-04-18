# PRD

- Task ID: `task-4133d905b2-20260418T233206`
- Created: `2026-04-18T23:32:06`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `系统里排产参数变化之后,点击排产按钮,订单的完成日期也要跟随参数的变化而变化`

## Goal

让排产日历页中会影响排产结果的参数，在用户点击“排产”或“重排”后都真实进入后端排产计算，并使订单完成日期展示反映最新排产结果。至少要修复“额外夜班”等日历规则在首次排产时未生效的问题，避免用户修改参数后点击排产却得到与未修改参数一致的完成日期。

## Scope

- 排产日历页触发排产和重排的前端控制器逻辑。
- 日历规则保存与排产命令调用之间的衔接。
- 后端基于 `schedule_calendar_rules` 计算可用班次并生成当前排产任务的链路。
- 与订单完成日期展示直接相关的排产事实字段构建与验证。
- 覆盖首次排产与后续重排的自动化验证。

## Non-Goals

- 不修改 Lite Scheduler 独立页面的手工完工逻辑。
- 不重做排产算法的整体优先级模型。
- 不承诺“任意参数变化都必须数学上改变每一张订单的完成日期”；本任务只要求参数变化必须真实进入排产计算，且在受影响场景下完成日期应随结果变化。
- 不引入 fallback、mock 排产、或静默兜底展示。

## Preconditions

- 本地仓库 `D:\ProjectPackage\ProductionPlan` 可读写。
- Python 与 pytest 可运行后端测试。
- 前端依赖已安装，仓库可运行 Playwright 或现有 e2e 脚本。
- 当前排产页面仍使用 `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js` 作为入口。

## Impacted Areas

- 前端首次排产入口 [useScheduleCalendarController.js](D:/ProjectPackage/ProductionPlan/fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js)
- 前端排产规则命令客户端与完成日期展示：
  [OrdersPoolOrdersTable.jsx](D:/ProjectPackage/ProductionPlan/fronted/src/legacy/features/orders-pool/page/OrdersPoolOrdersTable.jsx)
  [OrdersPoolOrderDetailPanel.jsx](D:/ProjectPackage/ProductionPlan/fronted/src/legacy/features/orders-pool/page/OrdersPoolOrderDetailPanel.jsx)
- 后端排产主流程与日历规则解析：
  [app_service.py](D:/ProjectPackage/ProductionPlan/backend/app/services/app_service.py)
- 现有后端测试：
  [test_shift_capacity_schedule.py](D:/ProjectPackage/ProductionPlan/backend/tests/test_shift_capacity_schedule.py)
  [test_app_service_schedule_trust.py](D:/ProjectPackage/ProductionPlan/backend/tests/test_app_service_schedule_trust.py)
  [test_app_service_generate_schedule_unlocked_only.py](D:/ProjectPackage/ProductionPlan/backend/tests/test_app_service_generate_schedule_unlocked_only.py)
- 需要新增或扩展的参数敏感性测试与真实浏览器验证。

## Phase Plan

### P1: 固化参数接线缺口与验收基线

- Objective:
  明确哪些排产参数真正进入“排产/重排”按钮调用，锁定首次排产未保存日历规则的缺口，并把关键场景写入测试契约。
- Owned paths:
  `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
  `backend/tests/*schedule*.py`
  `doc/tasks/task-4133d905b2-20260418T233206/*`
- Dependencies:
  当前前后端代码、现有参数敏感性实验结果、现有排产测试。
- Deliverables:
  可审阅 PRD/Test Plan；明确首次排产与重排的参数接线矩阵；锁定缺口说明。

### P2: 修复首次排产参数未生效并补自动化验证

- Objective:
  修复首次排产前未保存日历规则的问题，确保额外夜班、周末模式、法定假日开关等参数在点击“排产”后进入后端排产；补充自动化测试验证完成日期或排产事实随参数变化更新。
- Owned paths:
  `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
  `backend/tests/test_shift_capacity_schedule.py`
  `backend/tests/test_app_service_schedule_trust.py`
  `backend/tests/test_app_service_generate_schedule_unlocked_only.py`
  `backend/tests/test_simulation_manual_advance.py`
- Dependencies:
  P1 文档与审阅完成；现有后端测试基线可通过。
- Deliverables:
  产品代码修复、参数敏感性测试、执行记录。

### P3: 验证完成日期展示与真实交互结果一致

- Objective:
  用真实浏览器或现有 e2e 证明：修改额外夜班等日历参数后点击“排产”，订单完成日期展示使用最新排产事实；若当前数据下完工日期不变，也必须能证明参数已进入计算且展示不是陈旧值。
- Owned paths:
  `fronted/tests/e2e/*`
  `fronted/test-results/e2e/*`
  `doc/tasks/task-4133d905b2-20260418T233206/test-report.md`
- Dependencies:
  P2 修复完成；可运行浏览器验证环境。
- Deliverables:
  浏览器证据、测试报告、最终验收结论。

## Phase Acceptance Criteria

### P1

- P1-AC1: 明确列出排产按钮与重排按钮各自传入后端的排产参数，以及当前哪些参数在首次排产路径未生效。
- P1-AC2: PRD 与测试计划必须包含“额外夜班变更后点击首次排产”的显式验证场景。
- Evidence expectation:
  `prd.md`、`test-plan.md`、规划审阅记录。

### P2

- P2-AC1: 首次点击“排产”前，前端必须先保存当前日历规则，再触发后端排产命令；不得只在重排路径保存规则。
- P2-AC2: 在可控测试夹具下，修改 `date_shift_mode_by_date`、`weekend_rest_mode` 或 `skip_statutory_holidays` 后重新排产，至少一张订单的 `scheduled_finish_date` 或 `scheduled_finish_time` 发生变化。
- P2-AC3: 订单完成日期展示继续读取当前排产事实字段，而不是停留在旧的订单窗口字段或陈旧快照。
- Evidence expectation:
  代码 diff、后端测试输出、执行日志中带 acceptance id 的证据。

### P3

- P3-AC1: 真实浏览器验证中，先修改额外夜班再点击首次排产，页面展示的订单完成日期与最新排产事实一致。
- P3-AC2: 如果某组参数在当前真实数据下没有改变某张订单的完成日期，测试报告必须明确记录“参数已进入排产计算但未改变关键路径”的证据，不能把这种情况误判为前端未更新。
- Evidence expectation:
  Playwright 证据文件、`test-report.md`、浏览器截图或 trace。

## Done Definition

- P1-P3 全部完成并通过审阅。
- 首次排产与重排都使用同一份最新日历规则参数。
- 至少一个受控场景能证明参数变化会改变订单完成日期。
- 真实浏览器验证覆盖“额外夜班 + 点击排产”路径。
- `execution-log.md` 与 `test-report.md` 中能为每个 acceptance id 找到对应证据。

## Blocking Conditions

- 无法运行后端测试或真实浏览器验证。
- 排产按钮实际入口不在当前已定位的控制器中。
- 缺少能稳定复现“参数变化影响完成日期”的可控测试夹具且无法构建。
- 任意修复方案需要引入 fallback、mock 排产、或静默改写展示口径。
