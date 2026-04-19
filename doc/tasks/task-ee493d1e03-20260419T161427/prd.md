# PRD

- Task ID: `task-ee493d1e03-20260419T161427`
- Created: `2026-04-19T16:14:27`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `删除上一轮为订单池局部刷新引入的过度设计，并确保锁单、解锁、升权、降权对排产结果有实际影响`

## Goal

收敛上一轮为了跨页局部刷新而引入的过度设计，只保留必要、直观、可维护的订单池局部更新实现；同时修复当前排产逻辑中“锁单/解锁/升权/降权只改状态但不真正影响排产结果”的问题，让这些操作在普通排产和按事实重排里都能对结果顺序产生实际影响。

## Scope

- 删除上一轮新增的跨页订单池局部刷新信号机制。
- 清理与该机制配套的前端和后端附加结构。
- 保留订单池页面内对单条/批量操作的局部 item 更新能力。
- 修改普通排产 `generate_schedule()` 的候选订单构造，使 `lock_flag`、`frozen_flag`、`priority_level` 真正进入排产决策。
- 修改按事实重排 `generate_schedule_by_fact()` 的候选订单构造，使 `lock_flag`、`frozen_flag`、`priority_level` 真正进入排产决策。
- 为上述行为补充后端测试与必要的前端回归验证。

## Non-Goals

- 不重做订单池页面性能优化，不把列表改成虚拟滚动或行级状态管理。
- 不重新引入基准版本、fallback、兼容分支或“锁单照抄旧排位”语义。
- 不修改 ERP 同步本身的业务语义。
- 不改变排产页现有按钮布局和主要交互文案，除非为删除过度设计必须清理相关副作用代码。

## Preconditions

- 本地仓库 `D:\ProjectPackage\ProductionPlan` 可读写。
- Python/pytest 可运行后端测试。
- 前后端可正常启动，用于必要的真实页面验证。
- 当前工作区允许删除上一轮引入的跨页局部刷新信号相关代码；若这些代码已被其他未完成功能依赖，则必须先识别依赖并停下报告。

## Impacted Areas

- 过度设计清理
  - `fronted/src/legacy/features/order-execution/ordersPoolRefreshSignal.js`
  - `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
  - `fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js`
- 订单池局部刷新保留实现
  - `fronted/src/legacy/features/orders-pool/commandActions.js`
  - `fronted/src/legacy/features/order-execution/ordersPoolService.js`
- 排产核心
  - `backend/app/services/app_service.py`
- 相关测试
  - `backend/tests/test_app_service_generate_schedule_unlocked_only.py`
  - `backend/tests/test_schedule_fact_replan.py`
  - `backend/tests/test_app_service_batch_dispatch.py`
  - 如需要，新增更贴近排序语义的测试文件

## Phase Plan

### P1: 固化删减边界与排产影响语义

- Objective:
  明确上一轮哪些代码属于过度设计且必须删除，哪些局部 item 更新能力需要保留；同时明确锁单、解锁、升权、降权在普通排产和事实重排中的预期影响语义。
- Owned paths:
  `fronted/src/legacy/features/order-execution/ordersPoolRefreshSignal.js`
  `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
  `fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js`
  `backend/app/services/app_service.py`
  `backend/tests/*schedule*.py`
- Dependencies:
  当前订单池与排产页实现、现有排产测试、当前用户交互路径
- Deliverables:
  过度设计删减清单、保留清单、锁单/升权等影响排产的规则定义

### P2: 删除过度设计并恢复最小局部刷新实现

- Objective:
  删除跨页局部刷新信号机制及其附属结构，保证系统回到“订单池页内局部更新、跨页不做隐式同步”的更小设计面。
- Owned paths:
  `fronted/src/legacy/features/order-execution/ordersPoolRefreshSignal.js`
  `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
  `fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js`
  `backend/app/services/app_service.py`
- Dependencies:
  P1 已定义哪些代码必须删除、哪些必须保留
- Deliverables:
  删除后的前端代码、必要的后端返回字段收口、执行日志

### P3: 让锁单/解锁/升权/降权真正影响排产结果

- Objective:
  修改普通排产和事实重排，使锁单/冻结/优先级字段不再被排除在候选构造外，而是真正参与排序与结果生成。
- Owned paths:
  `backend/app/services/app_service.py`
  `backend/tests/test_app_service_generate_schedule_unlocked_only.py`
  `backend/tests/test_schedule_fact_replan.py`
  `backend/tests/test_app_service_batch_dispatch.py`
- Dependencies:
  P1 已定义业务语义；P2 已收掉不必要的跨页信号逻辑
- Deliverables:
  排产核心修复、后端回归测试、执行日志

### P4: 验证删减后行为与排产结果影响

- Objective:
  验证删除过度设计后没有留下死路径或残余耦合，并验证锁单/解锁/升权/降权确实能改变排产结果，而不是只改状态字段。
- Owned paths:
  `backend/tests/*schedule*.py`
  `doc/tasks/task-ee493d1e03-20260419T161427/*`
- Dependencies:
  P2、P3 完成
- Deliverables:
  测试报告、证据引用、最终结论

## Phase Acceptance Criteria

### P1

- P1-AC1: 计划必须明确列出上一轮引入的哪些代码属于过度设计，并说明删除它们不会破坏订单池页内已有的局部 item 更新能力。
- P1-AC2: 计划必须明确锁单/解锁/升权/降权在普通排产和事实重排中的预期影响语义，不允许再使用“只是状态变化但不参与候选排序”的模糊定义。
- Evidence expectation:
  `prd.md` 有清晰删减边界与排产语义说明；`test-plan.md` 覆盖删除与结果影响两类验证。

### P2

- P2-AC1: 跨页订单池局部刷新信号机制及其附属代码被删除，不再通过 `localStorage`、自定义事件或挂载时读取信号来隐式刷新订单池。
- P2-AC2: 订单池页内对锁单、解锁、升权、降权、删除、保存预计开始时间的局部 item 更新能力仍然保留，不得因删减过度设计而退化回整表刷新。
- Evidence expectation:
  `execution-log.md` 明确记录删除路径、保留路径与验证命令；代码中不存在残余未使用的跨页信号接口。

### P3

- P3-AC1: 普通排产 `generate_schedule()` 中，锁单/冻结订单不再被简单跳过，而是参与排产并对结果排序产生实际影响。
- P3-AC2: 按事实重排 `generate_schedule_by_fact()` 中，锁单/冻结/优先级不再被抹平或跳过，而是对未来排产结果产生实际影响。
- P3-AC3: 升权/降权修改 `priority_level` 后，至少有一组测试能够证明排产结果顺序随之变化。
- Evidence expectation:
  后端测试能明确证明锁单/升权对结果有影响，而不是仅断言字段值变化。

### P4

- P4-AC1: 删除过度设计后，系统没有遗留跨页刷新相关死路径或残余依赖。
- P4-AC2: 测试报告必须区分“删除了什么设计”与“恢复了什么排产影响”，并给出可复核证据。
- Evidence expectation:
  `test-report.md` 记录过度设计删除验证与排产结果影响验证，两类都要有清晰结果。

## Done Definition

- 上一轮新增的跨页订单池局部刷新信号设计被删除。
- 订单池页内局部 item 更新仍能正常工作。
- 锁单、解锁、升权、降权在普通排产与事实重排中都会实际影响结果，而不只是修改状态。
- 至少有针对锁单和优先级的回归测试证明结果变化。
- 所有 acceptance ids 都有执行或测试证据。

## Blocking Conditions

- 若删除跨页信号后发现当前 UI 仍有必须依赖该机制的真实交互，且无法在本任务内以更小设计替换，则必须停下并报告。
- 若业务无法接受“锁单/冻结不再是隐藏订单，而是作为高优先级约束参与排产”，则必须先确认语义后再继续。
- 不允许通过新增 fallback 或重新引入基准版本来制造“锁单有影响”的假象。
