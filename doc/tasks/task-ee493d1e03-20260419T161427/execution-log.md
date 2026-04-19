# Execution Log

- Task ID: `task-ee493d1e03-20260419T161427`
- Created: `2026-04-19T16:14:27`

## Phase Entries

### Phase P1

- Outcome: completed
- Acceptance ids: `P1-AC1`, `P1-AC2`
- Changed paths:
  - `doc/tasks/task-ee493d1e03-20260419T161427/prd.md`
  - `doc/tasks/task-ee493d1e03-20260419T161427/test-plan.md`
- Findings:
  - 上一轮真正属于过度设计的是跨页订单池局部刷新信号链：`ordersPoolRefreshSignal.js`、排产页发信号、订单池页监听 `localStorage`/事件/焦点后自动刷新。
  - 订单池页内局部更新本身不是过度设计，应保留。
  - 当前普通排产与事实重排都会在候选构造阶段直接跳过 `lock_flag/frozen_flag`，导致锁单不可能对结果产生实际影响。
  - 优先级字段虽然已进入排序 key，但事实重排里被直接写成 `0`，同样无法影响结果。
- Validation run:
  - `rg -n "ordersPoolRefreshSignal|affected_order_nos|partial-refresh-signal|publishOrdersPoolPartialRefreshSignal" fronted backend -S`
  - `Get-Content backend/app/services/app_service.py | Select-Object -Skip 2828 -First 120`
  - `Get-Content backend/tests/test_schedule_fact_replan.py | Select-Object -First 220`
- Evidence refs:
  - `doc/tasks/task-ee493d1e03-20260419T161427/prd.md#P1`
  - `doc/tasks/task-ee493d1e03-20260419T161427/test-plan.md#T1`

### Phase P2

- Outcome: completed
- Acceptance ids: `P2-AC1`, `P2-AC2`
- Changed paths:
  - `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
  - `fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js`
  - `fronted/src/legacy/features/order-execution/ordersPoolRefreshSignal.js`
  - `backend/app/services/app_service.py`
- Implementation summary:
  - 删除了跨页刷新信号文件与所有发布/消费逻辑。
  - 删除了排产返回中仅供跨页局部刷新增量使用的 `affected_order_nos`。
  - 保留了订单池页内本地局部刷新实现，不退化回整表刷新。
- Validation run:
  - `rg -n --glob '!backend/tests/_tmp/**' "ordersPoolRefreshSignal|affected_order_nos|partial-refresh-signal|publishOrdersPoolPartialRefreshSignal" fronted backend -S`
- Evidence refs:
  - `D:/ProjectPackage/ProductionPlan/backend/test-results/task-ee493d1e03/overdesign-grep.txt`

### Phase P3

- Outcome: completed
- Acceptance ids: `P3-AC1`, `P3-AC2`, `P3-AC3`
- Changed paths:
  - `backend/app/services/app_service.py`
  - `backend/tests/test_app_service_generate_schedule_unlocked_only.py`
  - `backend/tests/test_schedule_fact_replan.py`
- Implementation summary:
  - 普通排产不再在候选构造阶段跳过锁单/冻结订单。
  - 事实重排不再跳过锁单/冻结订单，也不再把 `lock_flag/frozen_flag` 直接抹成 `0`。
  - 现有排序 key 已包含 `frozen_flag`、`lock_flag`、`priority_level`，在候选真正进入列表后，这些字段会实际影响结果顺序。
  - 新增/调整测试以验证：锁单优先于普通订单、解锁后恢复普通顺序、升权后排在前面、事实重排中锁单/冻结/优先级会影响未来任务顺序。
- Validation run:
  - `python -m pytest backend/tests/test_app_service_generate_schedule_unlocked_only.py -q`
  - `python -m pytest backend/tests/test_schedule_fact_replan.py -q`
  - `python -m pytest backend/tests/test_app_service_batch_dispatch.py -q`
- Evidence refs:
  - `D:/ProjectPackage/ProductionPlan/backend/test-results/task-ee493d1e03/generate-schedule-lock-priority.txt`
  - `D:/ProjectPackage/ProductionPlan/backend/test-results/task-ee493d1e03/fact-replan-lock-priority.txt`
  - `D:/ProjectPackage/ProductionPlan/backend/test-results/task-ee493d1e03/batch-dispatch-state.txt`

### Phase P4

- Outcome: completed
- Acceptance ids: `P4-AC1`, `P4-AC2`
- Notes:
  - 本轮验证结果清晰分成两类：一类是过度设计删除的代码级证据；另一类是锁单/优先级影响排产结果的后端测试证据。
  - 没有再保留“为了跨页局部刷新而引入的复杂设计”来掩盖锁单无效问题。

## Outstanding Blockers

- None.
