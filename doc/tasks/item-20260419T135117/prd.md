# PRD

- Task ID: `item-20260419T135117`
- Created: `2026-04-19T13:51:17`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `把当前会整表刷新订单池/生产订单列表的操作改成只更新对应 item；只有手动点击刷新生产订单时才允许刷新整个订单列表`

## Goal

把订单池页面里当前会触发整表重新拉取 `/api/order-pool` 的日常操作改成“只更新受影响的订单 item”，降低大订单量场景下的刷新成本与等待时间；保留“手动点击 ERP 刷新生产订单”作为唯一允许整表同步生产订单列表的入口。

## Scope

- 订单池页面 `useOrdersPoolPageController` 的刷新策略。
- 订单池操作封装 `commandActions.js` 与 `ordersPoolService.js`。
- 订单池单条查询接口 `/api/order-pool/{order_no}` 的使用与必要补强。
- 订单池页面中以下操作后的前端数据更新行为：
  - 单张锁单/解锁/优先级调整/删除
  - 批量锁单/解锁/提优先级
  - 保存手工预计开始日期/班次
- “ERP 增量同步生产订单”操作后的整表刷新保留逻辑。
- 与上述行为直接相关的前端自动化或单元测试。

## Non-Goals

- 不修改 ERP 增量同步本身的后端业务语义，不把整表同步改成 item 级同步。
- 不改动排产算法、报工逻辑、物料刷新逻辑或库存刷新逻辑。
- 不重做订单池筛选、排序、表格结构或详情面板 UI。
- 不引入 fallback、静默降级、mock 返回或“失败后自动全表刷新”的兜底分支。

## Preconditions

- 本地仓库 `D:\ProjectPackage\ProductionPlan` 可读写。
- 前后端可正常启动，订单池页面可访问。
- 现有 `/api/order-pool/{order_no}` 接口可返回单条订单详情，或允许在本任务内补足其返回字段以支撑 item 级更新。
- Node / Python / pytest 可用；若需要前端浏览器验证，Playwright 可用。

## Impacted Areas

- 前端订单池页面控制器
  - `fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js`
- 前端订单池操作封装
  - `fronted/src/legacy/features/orders-pool/commandActions.js`
  - `fronted/src/legacy/features/order-execution/ordersPoolService.js`
  - `fronted/src/legacy/features/order-execution/ordersPoolQueryClient.js`
- 后端订单池查询接口
  - `backend/app/api/routes/app_queries.py`
  - `backend/app/services/order_pool_query_facade.py`
  - `backend/app/services/app_service.py`
- 可能需要新增或调整的测试
  - 订单池相关前端测试文件
  - `backend/tests/test_app_service_order_pool.py`
  - 订单池页面或 e2e 相关测试

## Phase Plan

### P1: 固化刷新边界与 item 更新契约

- Objective:
  明确哪些操作当前会整表刷新，哪些操作必须改成 item 级更新，哪些操作必须保留整表刷新；同时确认单条订单查询接口是否具备替换前端全量快照所需的数据。
- Owned paths:
  `fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js`
  `fronted/src/legacy/features/orders-pool/commandActions.js`
  `fronted/src/legacy/features/order-execution/ordersPoolService.js`
  `fronted/src/legacy/features/order-execution/ordersPoolQueryClient.js`
  `backend/app/api/routes/app_queries.py`
  `backend/app/services/app_service.py`
- Dependencies:
  当前订单池页面实现、单条订单查询接口、现有同步入口 `/api/orders/sync-from-erp/apply`
- Deliverables:
  item 级更新目标清单、保留整表刷新的白名单、单条订单查询契约结论

### P2: 实现订单池页面 item 级更新

- Objective:
  将非 ERP 手动同步操作从 `refreshSnapshot()` 整表刷新改成只更新当前或受影响订单 item，并同步维护选中态、详情区、排产标记等前端派生状态。
- Owned paths:
  `fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js`
  `fronted/src/legacy/features/orders-pool/commandActions.js`
  `fronted/src/legacy/features/order-execution/ordersPoolService.js`
  `fronted/src/legacy/features/order-execution/ordersPoolQueryClient.js`
  `backend/app/api/routes/app_queries.py`
  `backend/app/services/app_service.py`
- Dependencies:
  P1 已明确 item 更新所需字段与保留整表刷新入口
- Deliverables:
  前端 item 更新实现、必要的单条订单查询接口补强、执行日志

### P3: 验证“仅手动刷新整表”的回归

- Objective:
  通过自动化与真实页面验证证明：锁单/预计开工保存等操作不再整表刷新；只有手动点击 ERP 刷新生产订单时才整表同步生产订单列表。
- Owned paths:
  `fronted/tests/e2e/*`
  `backend/tests/test_app_service_order_pool.py`
  `doc/tasks/item-20260419T135117/*`
- Dependencies:
  P2 完成且前后端运行环境可用
- Deliverables:
  自动化验证结果、浏览器证据、测试报告

## Phase Acceptance Criteria

### P1

- P1-AC1: 计划必须明确列出当前哪些订单池操作会调用整表快照刷新，以及这些操作在目标行为下应改为 item 级更新还是保留整表刷新。
- P1-AC2: 计划必须明确“手动点击 ERP 刷新生产订单”是唯一允许整表同步生产订单列表的入口，其他日常订单池操作不得再隐式触发整表刷新。
- P1-AC3: 计划必须说明单条订单查询接口是否足够支撑前端 item 替换；若不够，需把接口补强纳入实现范围。
- Evidence expectation:
  `prd.md` 中有明确的刷新边界矩阵；`test-plan.md` 对每类操作都有覆盖。

### P2

- P2-AC1: 单张锁单、解锁、优先级调整、删除完成后，前端不得再重新拉取整张 `/api/order-pool`，只能更新受影响订单 item 或本地移除该 item。
- P2-AC2: 批量锁单、解锁、提优先级完成后，前端不得整表刷新，只能对受影响订单集合做局部更新。
- P2-AC3: 保存手工预计开始日期/班次后，前端不得整表刷新，只能刷新当前订单 item，并保持详情区与列表展示一致。
- P2-AC4: 手动点击“ERP 刷新生产订单”后，系统仍允许整表同步与刷新，不得误改成 item 级局部更新。
- Evidence expectation:
  `execution-log.md` 记录受影响路径、局部更新策略与验证命令；代码中不存在通过失败兜底再强制整表刷新来掩盖问题。

### P3

- P3-AC1: 自动化或浏览器验证能证明非 ERP 手动同步操作不会触发整表 `/api/order-pool` 重新加载。
- P3-AC2: 自动化或浏览器验证能证明手动 ERP 同步仍会触发整表刷新，并使订单池列表与 ERP 同步结果一致。
- P3-AC3: 测试报告必须记录至少一个真实页面或真实请求级证据，区分“item 级更新”与“整表刷新”两类行为。
- Evidence expectation:
  `test-report.md` 包含逐条测试结果与证据引用；若使用浏览器验证，需附带截图、trace 或网络证据。

## Done Definition

- 非 ERP 手动同步的订单池日常操作不再整表刷新 `/api/order-pool`。
- 订单池列表、详情区、选中态和派生状态在 item 级更新后保持一致。
- 手动 ERP 同步仍然是唯一允许整表刷新生产订单列表的入口。
- 所有 phase 与 acceptance ids 都有执行或测试证据。
- `check_completion.py` 可在最终收口时通过。

## Blocking Conditions

- 若单条订单查询接口无法返回支撑 item 级更新所需的字段，且本任务范围内又不能补强该接口，则必须停下并报告这一前置缺口。
- 若订单池页面存在隐藏耦合，导致某些操作必须依赖整表快照才能保持一致，而又无法明确收敛为受影响 item 集合，则必须先定义边界后再继续。
- 若前端或浏览器验证环境不可用，不能假装“局部更新已验证”；必须记录为阻塞。
- 不允许通过“失败后再自动整表刷新”的 fallback 掩盖 item 级更新设计缺陷。
