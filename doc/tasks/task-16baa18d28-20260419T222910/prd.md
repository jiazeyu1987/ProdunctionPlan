# PRD

- Task ID: `task-16baa18d28-20260419T222910`
- Created: `2026-04-19T22:29:10`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `删除解锁,锁单按钮增加冻结,解冻按钮`

## Goal

让订单池页面不再提供“解锁”操作，而是改为围绕“锁单/冻结”两类控制提供明确按钮；同时确保前端点击后的命令链路、后端批量命令处理、订单池局部刷新和测试都与新行为保持一致。

## Scope

- 订单池单行操作按钮文案、按钮显隐与禁用规则。
- 订单池批量操作按钮与批量预览文案。
- 前端订单池命令封装、本地 optimistic 更新和批量校验逻辑。
- 后端批量调度命令服务对 `FREEZE` / `UNFREEZE` 的支持。
- 覆盖上述行为的前后端自动化测试与任务交付物。

## Non-Goals

- 不改动订单池排序规则、筛选规则或排程算法。
- 不新增兼容旧 UI 的 fallback 按钮或双入口。
- 不修改 ERP 同步、删除订单、预计开工保存等非本次请求直接涉及的流程。

## Preconditions

- 本地 Python 测试环境可运行 `pytest`。
- 前端依赖已安装，可运行 Playwright 用例。
- 仓库中的订单池页面仍以 `fronted/src/legacy/features/orders-pool` 为有效实现入口。
- 若前后端任一测试依赖缺失，必须停止并记录到 `task-state.json.blocking_prereqs`。

## Impacted Areas

- `fronted/src/legacy/features/orders-pool/page/OrdersPoolOrdersTable.jsx`
- `fronted/src/legacy/features/orders-pool/page/OrdersPoolToolbar.jsx`
- `fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js`
- `fronted/src/legacy/features/orders-pool/commandActions.js`
- `fronted/src/legacy/features/orders-pool/formatters.js`
- `fronted/tests/e2e/orders-pool-item-refresh.e2e.spec.ts`
- `backend/app/services/dispatch_command_service.py`
- `backend/tests/test_app_service_batch_dispatch.py`
- `backend/tests/test_dispatch_command_service.py`

## Phase Plan

### P1: 固化冻结/解冻产品语义与验收口径

- Objective: 明确前后端当前实现中“锁单/解锁/冻结”的现状，定义本次 UI 与命令链路的目标行为，并把测试口径固化到任务产物。
- Owned paths: `doc/tasks/task-16baa18d28-20260419T222910/prd.md` `doc/tasks/task-16baa18d28-20260419T222910/test-plan.md` `doc/tasks/task-16baa18d28-20260419T222910/task-state.json`
- Dependencies: 仓库可读；订单池前后端相关源码存在。
- Deliverables: 审核通过的 PRD、测试计划与同步后的任务状态。

### P2: 实现订单池冻结/解冻命令链路

- Objective: 让订单池前端单行与批量操作移除“解锁”，改为提供“冻结/解冻”，并补齐前后端对 `FREEZE` / `UNFREEZE` 的状态变更能力。
- Owned paths: `fronted/src/legacy/features/orders-pool/page/OrdersPoolOrdersTable.jsx` `fronted/src/legacy/features/orders-pool/page/OrdersPoolToolbar.jsx` `fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js` `fronted/src/legacy/features/orders-pool/commandActions.js` `fronted/src/legacy/features/orders-pool/formatters.js` `backend/app/services/dispatch_command_service.py`
- Dependencies: P1 完成；订单池前后端命令接口保持可编辑。
- Deliverables: 可运行的前后端实现与执行日志证据。

### P3: 验证冻结/解冻交互与回归

- Objective: 用后端测试与真实浏览器测试验证新按钮行为、命令处理和局部刷新链路，确保没有残留“解锁”入口。
- Owned paths: `backend/tests/test_app_service_batch_dispatch.py` `backend/tests/test_dispatch_command_service.py` `fronted/tests/e2e/orders-pool-item-refresh.e2e.spec.ts` `doc/tasks/task-16baa18d28-20260419T222910/execution-log.md` `doc/tasks/task-16baa18d28-20260419T222910/test-report.md`
- Dependencies: P2 完成；测试工具可运行。
- Deliverables: 通过的测试结果、独立测试报告与完成态任务状态。

## Phase Acceptance Criteria

### P1

- P1-AC1: PRD 与测试计划必须明确本次改动不是纯文案替换，而是需要同时覆盖前端入口、前端状态更新和后端 `FREEZE` / `UNFREEZE` 命令支持。
- P1-AC2: 测试计划必须覆盖真实浏览器下的订单池按钮行为，并声明 `Validation surface: real-browser` 与 `Required tools: playwright`。
- Evidence expectation: `prd.md`、`test-plan.md` 通过 `validate_artifacts.py` 且状态已同步到 `task-state.json`。

### P2

- P2-AC1: 单条订单操作中不再显示“解锁”按钮；锁单按钮旁新增冻结或解冻按钮，且按钮文案与点击行为与订单当前 `frozen_flag` 一致。
- P2-AC2: 批量工具栏不再提供“全部解锁”；必须提供“全部冻结”和“全部解冻”，并且前端批量预览、禁用与错误提示与冻结状态一致。
- P2-AC3: 前端本地 optimistic 更新、命令文案和命令提交逻辑必须支持 `FREEZE` / `UNFREEZE`，且不引入 fallback 或双写逻辑。
- P2-AC4: 后端批量调度服务必须支持 `FREEZE` / `UNFREEZE`，并正确更新 `frozen_flag` 与审计记录；非法状态要 fail fast 返回明确错误。
- Evidence expectation: `execution-log.md` 记录变更路径、命令类型、验证命令和覆盖的验收项。

### P3

- P3-AC1: 后端自动化测试必须证明 `FREEZE` / `UNFREEZE` 能正确更新状态，并对空选中、已冻结、未冻结等非法状态给出明确错误。
- P3-AC2: 真实浏览器测试必须证明订单池页面可执行冻结或解冻动作，且只更新受影响订单，不会整表重拉 `/api/order-pool`。
- P3-AC3: 真实浏览器测试或实现检查必须证明页面不再暴露“解锁”入口，批量入口与单条入口都切换为冻结语义。
- Evidence expectation: `test-report.md` + Playwright trace/video/screenshot + pytest 输出。

## Done Definition

- P1、P2、P3 全部完成并有证据。
- 前端订单池页面没有残留“解锁”按钮入口。
- `FREEZE` / `UNFREEZE` 已贯通前端命令调用、后端服务和测试。
- `execution-log.md` 与 `test-report.md` 覆盖全部 acceptance ids。
- `check_completion.py --apply` 能将任务安全收口为完成态。

## Blocking Conditions

- 前端依赖或 Playwright 无法运行，导致 UI 任务无法做真实浏览器验证。
- Python / pytest 环境缺失，导致后端命令服务无法执行自动化验证。
- 订单池命令接口或相关源码不存在，无法继续实现 `FREEZE` / `UNFREEZE`。
- 发现用户已有未说明但直接冲突的在制修改时，必须暂停并说明冲突点，不得静默覆盖。
