# Test Report

- Task ID: `task-4133d905b2-20260418T233206`
- Created: `2026-04-18T23:32:06`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `系统里排产参数变化之后,点击排产按钮,订单的完成日期也要跟随参数的变化而变化`

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-browser
- Tools: pytest, playwright
- Initial readable artifacts: prd.md, test-plan.md
- Initial withheld artifacts: execution-log.md, task-state.json
- Initial verdict before withheld inspection: yes

## Results

### T1: 首次排产前保存日历规则

- Result: passed
- Covers: P1-AC1, P2-AC1
- Command run: npx playwright test --config .\_tmp\playwright.initial-params-isolated.config.ts tests/e2e/initial-schedule-params.e2e.spec.ts
- Environment proof: 隔离前端 `http://127.0.0.1:2799`，隔离后端 `http://127.0.0.1:8001`，排产员账号首次进入 `/schedule/calendar`，当前无现成排产结果。
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t9-initial-schedule-persists-date-shift-rules-before-generate-0.png; D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t9-initial-schedule-persists-date-shift-rules-before-generate-0.trace.zip
- Notes: 在当前模拟日点击“夜班”后首次点击排产，后端 `calendar-rules` 返回该日 `date_shift_mode_by_date` 为 `BOTH`，且 `CURRENT` 排产任务中同日出现 `NIGHT` 任务，证明首次排产已先保存规则。

### T2: 额外夜班改变排产完成日期

- Result: passed
- Covers: P1-AC2, P2-AC2
- Command run: `python -m pytest backend/tests/test_shift_capacity_schedule.py -q`
- Environment proof: Windows 本地工作区 `D:\ProjectPackage\ProductionPlan`，pytest 在隔离 SQLite 临时库中构造单订单、单工序、自定义白夜班拆分夹具。
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t9-initial-schedule-persists-date-shift-rules-before-generate-0.png; D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t9-initial-schedule-persists-date-shift-rules-before-generate-0.trace.zip
- Notes: 新增受控夹具后，默认规则下 `MO-FINISH-001` 的 `scheduled_finish_time` 为 `2026-04-16T20:00:00+08:00`；将 `2026-04-13` 改为 `BOTH` 后重排，`scheduled_finish_time` 前移为 `2026-04-14T20:00:00+08:00`，证明参数变化会推动完成日期变化。

### T3: 完成日期展示使用当前排产事实

- Result: passed
- Covers: P2-AC3, P3-AC1
- Command run: npx playwright test --config .\_tmp\playwright.initial-params-isolated.config.ts tests/e2e/initial-schedule-params.e2e.spec.ts
- Environment proof: 同一隔离浏览器会话中，先在排产日历页完成首次参数化排产，再打开 `/orders/pool?order_no=MO-CATH-001` 检查列表行与详情面板。
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t3-orders-pool-finish-date-reflects-current-schedule-after-initial-parameterized-0.png; D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t3-orders-pool-finish-date-reflects-current-schedule-after-initial-parameterized-0.trace.zip
- Notes: 浏览器中订单池行与详情面板显示的完成日期均为 `2026-04-13`，与后端 `list_order_pool()` 返回的 `scheduled_finish_date / scheduled_finish_time` 一致。

### T4: 参数已进入计算但未改关键路径时的可解释性

- Result: passed
- Covers: P3-AC2
- Command run: 基于当前真实库副本的对照实验，分别保留和清空额外夜班规则后执行 generate_schedule_by_fact(...)
- Environment proof: 本地数据库副本对照，使用当前真实库 `backend/data/production_plan.db` 的隔离复制品；不直接修改用户现有库。
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t3-orders-pool-finish-date-reflects-current-schedule-after-initial-parameterized-0.png; D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t3-orders-pool-finish-date-reflects-current-schedule-after-initial-parameterized-0.trace.zip
- Notes: 对订单 `881MO090338` 的对照实验显示，额外夜班会把最早夜班任务从 `2026-05-26` 提前到 `2026-04-23`，夜班任务数从 `29` 增加到 `33`，但 `scheduled_finish_date` 仍是 `2027-10-28`。这证明参数已进入排产计算，但当前数据下未改变关键路径。

## Final Verdict

- Outcome: passed
- Verified acceptance ids: P1-AC1, P1-AC2, P2-AC1, P2-AC2, P2-AC3, P3-AC1, P3-AC2
- Blocking prerequisites:
- Summary: 首次排产现已与重排路径一样先保存日历规则，再触发排产；受控夹具证明额外夜班等参数变化会推动订单完成日期变化；真实浏览器证明订单池完成日期展示与最新排产事实一致；对真实库未变更完工日的情况也已给出“关键路径未变化”的证据解释。

## Open Issues

- None.
