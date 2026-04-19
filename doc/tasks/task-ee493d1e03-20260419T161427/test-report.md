# Test Report

- Task ID: `task-ee493d1e03-20260419T161427`
- Created: `2026-04-19T16:14:27`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `删除上一轮为订单池局部刷新引入的过度设计，并确保锁单、解锁、升权、降权对排产结果有实际影响`

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-runtime
- Tools: pytest, rg
- Initial readable artifacts: prd.md, test-plan.md
- Initial withheld artifacts: execution-log.md, task-state.json
- Initial verdict before withheld inspection: yes

## Results

### T1: 删除跨页订单池刷新信号设计

- Result: passed
- Covers: P1-AC1, P2-AC1, P4-AC1
- Command run: `rg -n --glob '!backend/tests/_tmp/**' "ordersPoolRefreshSignal|affected_order_nos|partial-refresh-signal|publishOrdersPoolPartialRefreshSignal" fronted backend -S`
- Environment proof: 本地仓库 `D:\ProjectPackage\ProductionPlan`
- Evidence refs: D:/ProjectPackage/ProductionPlan/backend/test-results/task-ee493d1e03/overdesign-grep.txt
- Notes: 检索结果为空，说明跨页信号文件、排产返回增量字段与消费逻辑都已删除

### T2: 订单池页内局部刷新能力保留

- Result: passed
- Covers: P2-AC2
- Command run: 代码复核订单池页内命令结果处理链路
- Environment proof: 本地代码路径 `fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js`
- Evidence refs: D:/ProjectPackage/ProductionPlan/doc/tasks/task-ee493d1e03-20260419T161427/execution-log.md
- Notes: 页内单条/批量操作后的 `refreshOrderPoolItems()` 仍保留，未退化回整表刷新

### T3: 普通排产中锁单会影响结果

- Result: passed
- Covers: P1-AC2, P3-AC1
- Command run: `python -m pytest backend/tests/test_app_service_generate_schedule_unlocked_only.py -q`
- Environment proof: 本地 pytest 运行时
- Evidence refs: D:/ProjectPackage/ProductionPlan/backend/test-results/task-ee493d1e03/generate-schedule-lock-priority.txt
- Notes: 普通排产已验证锁单优先于普通订单，且解锁后普通优先级重新生效

### T4: 升权/降权会影响普通排产结果

- Result: passed
- Covers: P1-AC2, P3-AC3
- Command run: `python -m pytest backend/tests/test_app_service_generate_schedule_unlocked_only.py -q`
- Environment proof: 本地 pytest 运行时
- Evidence refs: D:/ProjectPackage/ProductionPlan/backend/test-results/task-ee493d1e03/generate-schedule-lock-priority.txt
- Notes: 提升 `priority_level` 后，竞争订单的排产顺序会变化

### T5: 事实重排中锁单/优先级会影响未来结果

- Result: passed
- Covers: P1-AC2, P3-AC2
- Command run: `python -m pytest backend/tests/test_schedule_fact_replan.py -q`
- Environment proof: 本地 pytest 运行时
- Evidence refs: D:/ProjectPackage/ProductionPlan/backend/test-results/task-ee493d1e03/fact-replan-lock-priority.txt
- Notes: 事实重排已验证锁单/冻结订单进入未来候选并排在普通订单前面，优先级也会影响顺序

### T6: 解锁后排产恢复普通约束

- Result: passed
- Covers: P3-AC1, P3-AC2
- Command run: `python -m pytest backend/tests/test_app_service_generate_schedule_unlocked_only.py -q`
- Environment proof: 本地 pytest 运行时
- Evidence refs: D:/ProjectPackage/ProductionPlan/backend/test-results/task-ee493d1e03/generate-schedule-lock-priority.txt
- Notes: 解锁后，原先被锁单强行提前的订单会恢复到由普通优先级决定的顺序

### T7: 测试报告区分设计删减与排产影响

- Result: passed
- Covers: P4-AC2
- Command run: 审查 `test-report.md`
- Environment proof: 当前任务工件目录
- Evidence refs: D:/ProjectPackage/ProductionPlan/doc/tasks/task-ee493d1e03-20260419T161427/test-report.md
- Notes: 报告已分别记录“删除了什么过度设计”和“锁单/优先级如何影响排产”的独立结论与证据

## Final Verdict

- Outcome: passed
- Verified acceptance ids: P1-AC1, P1-AC2, P2-AC1, P2-AC2, P3-AC1, P3-AC2, P3-AC3, P4-AC1, P4-AC2
- Blocking prerequisites:
- Summary: 上一轮为跨页局部刷新引入的过度设计已删除，订单池页内局部刷新能力仍保留；锁单、解锁、升权、降权不再只是改状态，而是在普通排产与事实重排中都能实际改变结果。

## Open Issues

- None.
