# Test Report

- Task ID: `task-16baa18d28-20260419T222910`
- Created: `2026-04-19T22:29:10`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `删除解锁,锁单按钮增加冻结,解冻按钮`

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-browser
- Tools: playwright, pytest
- Initial readable artifacts: prd.md, test-plan.md
- Initial withheld artifacts: execution-log.md, task-state.json
- Initial verdict before withheld inspection: yes

## Results

### T0: 任务文档覆盖冻结命令与真实浏览器验证

- Result: passed
- Covers: P1-AC1, P1-AC2
- Command run: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_artifacts.py --cwd D:\ProjectPackage\ProductionPlan --task-id task-16baa18d28-20260419T222910`
- Environment proof: 本地仓库任务目录 `D:\ProjectPackage\ProductionPlan\doc\tasks\task-16baa18d28-20260419T222910`
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\evidence-manifest.json, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\local-order-actions-refresh-only-the-affected-item-instead-of-reloading-the-full-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\local-order-actions-refresh-only-the-affected-item-instead-of-reloading-the-full-0.trace.zip
- Notes: 文档已明确本次改动覆盖前端入口、前端状态更新与后端 `FREEZE` / `UNFREEZE`，并声明 `Validation surface: real-browser` 与 `Required tools: playwright`。

### T1: 单条订单按钮切换为冻结语义

- Result: passed
- Covers: P2-AC1, P2-AC3, P3-AC3
- Command run: `npm run e2e:playwright -- tests/e2e/orders-pool-item-refresh.e2e.spec.ts`
- Environment proof: Playwright 启动本地前端 `http://127.0.0.1:2799/orders/pool`，使用 scheduler stub 会话与测试内订单池路由桩
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\evidence-manifest.json, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\local-order-actions-refresh-only-the-affected-item-instead-of-reloading-the-full-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\local-order-actions-refresh-only-the-affected-item-instead-of-reloading-the-full-0.trace.zip
- Notes: 单条订单不再出现“解锁”，可见“锁单”和“冻结”；点击冻结后按钮切为“解冻”，再次点击恢复“冻结”。

### T2: 单条冻结/解冻仍走局部刷新

- Result: passed
- Covers: P2-AC1, P2-AC3, P3-AC2
- Command run: `npm run e2e:playwright -- tests/e2e/orders-pool-item-refresh.e2e.spec.ts`
- Environment proof: 与 T1 相同；测试内统计 `/api/order-pool`、`/api/reportings` 与批量命令请求计数
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\evidence-manifest.json, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\local-order-actions-refresh-only-the-affected-item-instead-of-reloading-the-full-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\local-order-actions-refresh-only-the-affected-item-instead-of-reloading-the-full-0.trace.zip
- Notes: 冻结/解冻后整表 `/api/order-pool` 请求计数保持初始值，页面只更新当前订单行；同一次用例也验证了保存手工开工约束后详情区更新为 `2026-04-21 夜班`。

### T3: 批量冻结/解冻命令服务更新状态

- Result: passed
- Covers: P2-AC2, P2-AC4, P3-AC1
- Command run: `python -m pytest backend/tests/test_app_service_batch_dispatch.py -q`
- Environment proof: 仓库内 Python 环境 + 临时 SQLite 数据库 `batch-dispatch.db`
- Evidence refs: D:\ProjectPackage\ProductionPlan\backend\test-results\task-16baa18d28\app-service-batch-dispatch.txt, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\local-order-actions-refresh-only-the-affected-item-instead-of-reloading-the-full-0.trace.zip
- Notes: 新增测试证明 `FREEZE` / `UNFREEZE` 会正确更新 `frozen_flag`，并保持审计记录写入。

### T4: 非法冻结状态 fail fast

- Result: passed
- Covers: P2-AC4, P3-AC1
- Command run: `python -m pytest backend/tests/test_app_service_batch_dispatch.py -q`
- Environment proof: 与 T3 相同
- Evidence refs: D:\ProjectPackage\ProductionPlan\backend\test-results\task-16baa18d28\app-service-batch-dispatch.txt, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\local-order-actions-refresh-only-the-affected-item-instead-of-reloading-the-full-0.trace.zip
- Notes: 混合冻结状态执行 `FREEZE`、未冻结集合执行 `UNFREEZE` 时会返回 `ORDER_BATCH_DISPATCH_FROZEN_STATE_INVALID`，且不会产生部分更新。

### T5: 调度命令批准链路支持冻结/解冻

- Result: passed
- Covers: P2-AC4, P3-AC1
- Command run: `python -m pytest backend/tests/test_dispatch_command_service.py -q`
- Environment proof: 仓库内 Python 环境 + 临时 SQLite 数据库 `dispatch-command-service.db`
- Evidence refs: D:\ProjectPackage\ProductionPlan\backend\test-results\task-16baa18d28\dispatch-command-service.txt, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\local-order-actions-refresh-only-the-affected-item-instead-of-reloading-the-full-0.trace.zip
- Notes: 创建并批准 `FREEZE` / `UNFREEZE` 命令后，`order_pool_state.frozen_flag` 按预期在 1 和 0 之间切换。

## Final Verdict

- Outcome: passed
- Verified acceptance ids: P1-AC1, P1-AC2, P2-AC1, P2-AC2, P2-AC3, P2-AC4, P3-AC1, P3-AC2, P3-AC3
- Blocking prerequisites:
- Summary: 订单池页面已删除“解锁”入口，单条与批量操作新增冻结/解冻；前端 optimistic 更新、后端批量命令与批准链路均已支持 `FREEZE` / `UNFREEZE`，定向 pytest 与真实浏览器 Playwright 验证全部通过。

## Open Issues

- None.
