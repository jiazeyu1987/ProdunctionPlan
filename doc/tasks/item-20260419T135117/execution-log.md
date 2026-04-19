# Execution Log

- Task ID: `item-20260419T135117`
- Created: `2026-04-19T13:51:17`

## Phase Entries

### Phase P1

- Outcome: completed
- Acceptance ids: `P1-AC1`, `P1-AC2`, `P1-AC3`
- Changed paths:
  - `doc/tasks/item-20260419T135117/prd.md`
  - `doc/tasks/item-20260419T135117/test-plan.md`
- Findings:
  - 当前订单池页面里真正会整表刷新的是 `refreshSnapshot()` 链路，主要由 `useOrdersPoolPageController.js` 调用 `fetchOrdersPoolSnapshot()` 触发。
  - 日常订单池操作里，单张操作、批量操作、保存手工开工时间都会在成功后走整表刷新。
  - 手动 ERP 同步入口 `applyOrdersSyncFromErpAndRefresh()` 也走整表刷新，这条路径应保留。
  - 现有 `/api/order-pool/{order_no}` 已存在，且返回结构与列表 item 足够接近，可支撑前端 item 级替换，无需新增后端接口。
- Validation run:
  - `rg -n "fetchOrdersPoolSnapshot|refreshSnapshot|applyOrdersSyncFromErpAndRefresh|saveExpectedStartAndRefresh|createOrderCommandAndRefresh|batchOrderCommandAndRefresh" fronted/src -S`
  - `Get-Content fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js`
  - `Get-Content fronted/src/legacy/features/order-execution/ordersPoolService.js`
  - `Get-Content backend/app/api/routes/app_queries.py`
- Evidence refs:
  - `doc/tasks/item-20260419T135117/prd.md#P1`
  - `doc/tasks/item-20260419T135117/test-plan.md#T1`
- Remaining risks:
  - 订单池页面存在较多派生状态，局部更新后必须确认列表、详情区、选中态仍保持一致。

### Phase P2

- Outcome: completed
- Acceptance ids: `P2-AC1`, `P2-AC2`, `P2-AC3`, `P2-AC4`
- Changed paths:
  - `fronted/src/legacy/features/order-execution/ordersPoolService.js`
  - `fronted/src/legacy/features/orders-pool/commandActions.js`
  - `fronted/src/legacy/features/orders-pool/index.js`
  - `fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js`
  - `fronted/tests/e2e/orders-pool-item-refresh.e2e.spec.ts`
- Implementation summary:
  - 新增 `fetchOrdersPoolItems(orderNos)`，复用现有单条订单查询接口做局部拉取。
  - 将订单池 command actions 从“命令后立即整表 refresh”改为返回 `affectedOrderNos` / `removedOrderNos` 结果对象。
  - 控制器中新增 `mergeOrderPoolItems`、`removeOrderPoolItems`、`refreshOrderPoolItems`，仅对受影响订单做替换或移除。
  - 手动 ERP 同步仍然沿用 `refreshSnapshot()` 整表刷新，不改语义。
- Validation run:
  - 浏览器脚本验证“锁单 + 保存手工开工约束”后不增加整表 `/api/order-pool` 请求
  - `python -m pytest backend/tests/test_job_dispatcher_command_services.py -q`
- Evidence refs:
  - `fronted/test-results/manual/orders-pool-item-refresh.json`
  - `fronted/test-results/manual/orders-pool-erp-sync-refresh.json`
- Remaining risks:
  - 仓库现有 `backend/tests/test_app_service_order_pool.py` 有与本任务无关的既有失败，集中在版本口径字段，不是本次前端局部刷新改动引入。

### Phase P3

- Outcome: completed
- Acceptance ids: `P3-AC1`, `P3-AC2`, `P3-AC3`
- Validation run:
  - 临时真实浏览器脚本 1：在当前 2798 服务上 stub `/api/order-pool`、`/api/order-pool/{order_no}`、命令接口，验证锁单与保存预计开工后整表请求计数不增加。
  - 临时真实浏览器脚本 2：在当前 2798 服务上 stub ERP 同步预览与执行接口，验证手动 ERP 同步后整表请求计数增加。
- Evidence refs:
  - `fronted/test-results/manual/orders-pool-item-refresh.json`
  - `fronted/test-results/manual/orders-pool-erp-sync-refresh.json`
- Notes:
  - Playwright 正式 config 因本机已有开发服务器运行而无法直接复用 `fronted/playwright.config.ts` 启动独立 webServer，本轮使用当前运行中的真实前端服务完成浏览器验证。

## Outstanding Blockers

- None.
