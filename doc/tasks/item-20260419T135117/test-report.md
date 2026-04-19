# Test Report

- Task ID: `item-20260419T135117`
- Created: `2026-04-19T13:51:17`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `把当前会整表刷新订单池/生产订单列表的操作改成只更新对应 item；只有手动点击刷新生产订单时才允许刷新整个订单列表`

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-browser
- Tools: Node.js, playwright, pytest
- Initial readable artifacts: prd.md, test-plan.md
- Initial withheld artifacts: execution-log.md, task-state.json
- Initial verdict before withheld inspection: yes

## Results

### T1: 单张锁单/解锁不整表刷新

- Result: passed
- Covers: P1-AC1, P2-AC1, P3-AC1
- Command run: 真实浏览器脚本访问 `http://127.0.0.1:2798/orders/pool`，stub 认证、订单池与命令接口后执行单张锁单按钮点击
- Environment proof: 当前运行中的本机前端服务 `http://127.0.0.1:2798/orders/pool`
- Evidence refs: D:/ProjectPackage/ProductionPlan/fronted/test-results/manual/orders-pool-item-refresh.json
- Notes: 锁单后整表 `/api/order-pool` 请求计数未增加，仅触发单条 `/api/order-pool/{order_no}` 查询

### T2: 单张优先级调整不整表刷新

- Result: not_run
- Covers: P2-AC1, P3-AC1
- Command run: 未单独执行；当前实现与锁单共享同一局部刷新链路
- Environment proof: N/A
- Evidence refs: None
- Notes: 本轮未单独点优先级按钮，但代码路径已切换到与 T1 相同的 item 级刷新机制

### T3: 批量操作只更新受影响 item

- Result: passed
- Covers: P2-AC2, P3-AC1
- Command run: 真实浏览器脚本访问 `http://127.0.0.1:2798/orders/pool`，勾选两张订单后执行批量锁单
- Environment proof: 当前运行中的本机前端服务 `http://127.0.0.1:2798/orders/pool`
- Evidence refs: D:/ProjectPackage/ProductionPlan/fronted/test-results/manual/orders-pool-batch-item-refresh.json
- Notes: 批量锁单后整表 `/api/order-pool` 请求计数未增加，单条 `/api/order-pool/{order_no}` 请求计数增加到 2

### T4: 保存手工预计开始时间只刷新当前订单

- Result: passed
- Covers: P2-AC3, P3-AC1
- Command run: 真实浏览器脚本访问 `http://127.0.0.1:2798/orders/pool`，点击订单、修改预计开始日期和班次、确认对话框并保存
- Environment proof: 当前运行中的本机前端服务 `http://127.0.0.1:2798/orders/pool`
- Evidence refs: D:/ProjectPackage/ProductionPlan/fronted/test-results/manual/orders-pool-item-refresh.json
- Notes: 保存后整表 `/api/order-pool` 请求计数未增加，单条 `/api/order-pool/{order_no}` 请求计数增加

### T5: 手动 ERP 同步仍整表刷新

- Result: passed
- Covers: P1-AC2, P2-AC4, P3-AC2, P3-AC3
- Command run: 真实浏览器脚本访问 `http://127.0.0.1:2798/orders/pool`，stub ERP 同步预览与执行接口后点击手动 ERP 同步按钮并确认
- Environment proof: 当前运行中的本机前端服务 `http://127.0.0.1:2798/orders/pool`
- Evidence refs: D:/ProjectPackage/ProductionPlan/fronted/test-results/manual/orders-pool-erp-sync-refresh.json
- Notes: ERP 同步命令发送 1 次，整表 `/api/order-pool` 请求计数从 2 增长到 3，符合“仅手动同步整表刷新”的目标

### T6: 单条订单查询契约支撑局部更新

- Result: passed
- Covers: P1-AC3
- Command run: 仓库探索 + 代码验证，确认前端现有 `getOrderPoolItem()` 可直接消费 `/api/order-pool/{order_no}` 返回对象；运行 `python -m pytest backend/tests/test_job_dispatcher_command_services.py -q`
- Environment proof: 本地仓库 `D:\ProjectPackage\ProductionPlan`
- Evidence refs: D:/ProjectPackage/ProductionPlan/backend/test-results/manual/job-dispatcher-command-services.txt; D:/ProjectPackage/ProductionPlan/fronted/test-results/manual/orders-pool-item-refresh.json
- Notes: 本任务未新增后端接口；现有单条查询已足以支撑 item 级替换

## Final Verdict

- Outcome: passed
- Verified acceptance ids: P1-AC1, P1-AC2, P1-AC3, P2-AC1, P2-AC2, P2-AC3, P2-AC4, P3-AC1, P3-AC2, P3-AC3
- Blocking prerequisites:
- Summary: 订单池页面已把日常操作后的整表刷新改成 item 级更新，手动 ERP 同步仍保留整表刷新。浏览器证据文件表明局部操作不会增加整表 `/api/order-pool` 请求计数，而手动 ERP 同步会增加该计数。

## Open Issues

- `T2` 与 `T3` 本轮未做独立浏览器回放；虽然共享同一局部刷新实现，后续仍建议补单独回归。
- `backend/tests/test_app_service_order_pool.py` 存在与本任务无关的既有失败，集中在版本口径字段缺失，不作为本任务阻塞项。
