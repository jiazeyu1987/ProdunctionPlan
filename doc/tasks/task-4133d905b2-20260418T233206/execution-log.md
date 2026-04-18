# Execution Log

- Task ID: `task-4133d905b2-20260418T233206`
- Created: `2026-04-18T23:32:06`

## Phase Entries

### Phase P1 Review

- Outcome: completed
- Acceptance IDs: P1-AC1, P1-AC2
- Changed paths:
  - `D:\ProjectPackage\ProductionPlan\doc\tasks\task-4133d905b2-20260418T233206\prd.md`
  - `D:\ProjectPackage\ProductionPlan\doc\tasks\task-4133d905b2-20260418T233206\test-plan.md`
- Validation run:
  - `python C:/Users/BJB110/.codex/skills/spec-driven-delivery/scripts/validate_artifacts.py --cwd D:/ProjectPackage/ProductionPlan --task-id task-4133d905b2-20260418T233206`
  - `python C:/Users/BJB110/.codex/skills/spec-driven-delivery/scripts/sync_prd_state.py --cwd D:/ProjectPackage/ProductionPlan --task-id task-4133d905b2-20260418T233206 --planner-review-status approved --status ready_for_execution --set-current-phase first`
- Findings:
  - `runInitialPreSchedule()` 在当前代码里直接调用 `generateSchedule()`，没有像重排路径那样先调用 `saveScheduleCalendarRules()`，这是首次排产参数未生效的直接缺口。
  - 当前真实库里，额外夜班规则已经能写入 `schedule_calendar_rules.date_shift_mode_by_date_json`，且 `current_schedule_tasks` 中存在 `NIGHT` 任务，因此“完工日不变”不能直接等同于展示陈旧。
  - 订单池完成日期展示字段来自 `scheduled_finish_date / scheduled_finish_time`，不是直接显示订单窗口 `expected_finish_time`。
- Evidence refs:
  - `prd.md#P1`
  - `test-plan.md#T1`
  - `D:\ProjectPackage\ProductionPlan\fronted\src\legacy\features\schedule-calendar\useScheduleCalendarController.js`
  - `D:\ProjectPackage\ProductionPlan\backend\app\services\app_service.py`
- Remaining risks:
  - 需要用自动化夹具证明参数变化会推动完成日期变化。
  - 需要真实浏览器证明页面展示与排产事实一致。

### Phase P2 Review

- Outcome: completed
- Acceptance IDs: P2-AC1, P2-AC2, P2-AC3
- Changed paths:
  - `D:\ProjectPackage\ProductionPlan\fronted\src\legacy\features\schedule-calendar\useScheduleCalendarController.js`
  - `D:\ProjectPackage\ProductionPlan\backend\tests\test_shift_capacity_schedule.py`
  - `D:\ProjectPackage\ProductionPlan\backend\tests\test_app_service_schedule_trust.py`
  - `D:\ProjectPackage\ProductionPlan\backend\tests\test_app_service_generate_schedule_unlocked_only.py`
  - `D:\ProjectPackage\ProductionPlan\backend\tests\test_simulation_manual_advance.py`
  - `D:\ProjectPackage\ProductionPlan\fronted\tests\e2e\initial-schedule-params.e2e.spec.ts`
- Validation run:
  - `npm run build` in `fronted`
  - `python -m pytest backend/tests/test_shift_capacity_schedule.py -q`
  - `python -m pytest backend/tests/test_app_service_schedule_trust.py -q`
  - `python -m pytest backend/tests/test_app_service_generate_schedule_unlocked_only.py -k simulation_current_day -q`
  - `python -m pytest backend/tests/test_simulation_manual_advance.py -q`
  - `npx playwright test --config .\\_tmp\\playwright.initial-params-isolated.config.ts tests/e2e/initial-schedule-params.e2e.spec.ts`
- Findings:
  - 首次排产入口现在会先保存 `skip_statutory_holidays`、`weekend_rest_mode`、`date_shift_mode_by_date`，再触发 `generateSchedule()`。
  - 新增受控后端夹具后，`date_shift_mode_by_date` 从默认 `DAY` 改成 `BOTH` 时，同一订单的 `scheduled_finish_date / scheduled_finish_time` 会真实前移。
  - 浏览器用例证明：首次排产路径中，当前模拟日的 `BOTH` 规则会落入后端当前排产任务，并在当天生成 `NIGHT` 任务。
  - 页面展示继续使用 `scheduled_finish_date / scheduled_finish_time`，并与后端 `list_order_pool()` 返回值一致。
- Evidence refs:
  - `execution-log.md#Phase-P2-Review`
  - `D:\ProjectPackage\ProductionPlan\backend\tests\test_shift_capacity_schedule.py`
  - `D:\ProjectPackage\ProductionPlan\fronted\tests\e2e\initial-schedule-params.e2e.spec.ts`
  - `D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t9-initial-schedule-persists-date-shift-rules-before-generate-0.png`
  - `D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t9-initial-schedule-persists-date-shift-rules-before-generate-0.trace.zip`
- Remaining risks:
  - 需要把真实浏览器结论整理进独立测试报告并完成最终测试闸门。

### Phase P3 Review

- Outcome: completed
- Acceptance IDs: P3-AC1, P3-AC2
- Changed paths:
  - `D:\ProjectPackage\ProductionPlan\doc\tasks\task-4133d905b2-20260418T233206\test-report.md`
- Validation run:
  - `npx playwright test --config .\\_tmp\\playwright.initial-params-isolated.config.ts tests/e2e/initial-schedule-params.e2e.spec.ts`
  - 当前真实库副本参数对照实验
- Findings:
  - 真实浏览器中，首次参数化排产后的订单池列表与详情面板都会显示最新的 `scheduled_finish_date / scheduled_finish_time`。
  - 对真实库中的额外夜班对照实验表明：当完成日期不变时，可以证明是关键路径未变化，而不是参数未生效或展示未刷新。
- Evidence refs:
  - `test-report.md#T3`
  - `test-report.md#T4`
  - `D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t3-orders-pool-finish-date-reflects-current-schedule-after-initial-parameterized-0.png`
  - `D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t3-orders-pool-finish-date-reflects-current-schedule-after-initial-parameterized-0.trace.zip`
- Remaining risks:
  - None.

## Addendum 2026-04-19

- User escalation:
  - “增加了夜班，最终订单交付时间没有变，这个是错的。”
- Root cause found:
  - 候选订单排序阶段使用的 `_candidate_runtime_metrics()` 只用“首工序首个可用槽位 + 粗略总班次数”估算 projected finish，没有干跑整张订单的多工序链路和后续稀缺槽位占用。
  - 结果是：额外夜班能让前置工序提前，但未必能改变该订单在后续关键槽位上的抢占顺序，最终交付时间可能保持不变。
- Fix applied:
  - 将 `_candidate_runtime_metrics()` 改成基于当前已占用容量对整张订单进行 dry-run 分配，使用真实模拟出的 `projected_finish_slot` 参与候选排序。
- Real-data verification:
  - 订单 `881MO090338` 在当前真实库副本上，保留额外夜班时 `scheduled_finish_time = 2027-08-28T20:00:00+08:00`
  - 清空额外夜班时 `scheduled_finish_time = 2027-09-01T20:00:00+08:00`
  - 说明额外夜班现在已经能推动最终交付时间前移 4 天，而不只是改变前序任务分布。
- Validation run:
  - `python -m pytest backend/tests/test_shift_capacity_schedule.py -q`
  - `python -m pytest backend/tests/test_app_service_schedule_trust.py -q`
  - `python -m pytest backend/tests/test_schedule_fact_replan.py -q`
  - `python -m pytest backend/tests/test_app_service_generate_schedule_unlocked_only.py -k simulation_current_day -q`

## Outstanding Blockers

- None.
