# PRD

- Task ID: `facade-app-queries-appservice-20260419T014536`
- Created: `2026-04-19T01:45:36`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `继续模块化重构：抽离订单池查询 facade，使 app_queries 不再直接依赖 AppService，并保持订单池/工序时间线查询行为稳定`

## Goal

在上一轮 provider/runtime 收口的基础上，继续按自上向下方式降低耦合：把订单池相关查询从 `AppService` 的直接暴露层中切成独立 facade，让 `app_queries.py` 通过专门的查询服务承接订单池接口，同时保持现有接口路径和返回行为稳定。

## Scope

- 抽离订单池相关 query facade。
- 将 `app_queries.py` 中订单池相关 5 个接口切换到新 facade：
  - `/order-pool`
  - `/order-pool/{order_no}`
  - `/order-pool/{order_no}/process-timeline`
  - `/order-pool/{order_no}/materials`
  - `/order-pool/materials/{parent_material_code}/children`
- 为 facade 增加对应 provider / 依赖获取函数。
- 补充针对 API 路由依赖切换的定向测试。

## Non-Goals

- 不在本轮中拆分 `AppService` 的排产、报工、主数据、dashboard 或 order-summary 逻辑。
- 不改变任何 HTTP 路径、鉴权规则或主要返回字段。
- 不引入 fallback facade、兼容双写或默认成功值。

## Preconditions

- Python 环境可执行后端 pytest。
- 当前仓库中的订单池测试夹具可正常创建临时 SQLite 数据库。
- 如缺失依赖或测试环境不可用，必须立即停止并记录阻塞项。

## Impacted Areas

- `backend/app/api/routes/app_queries.py`
- `backend/app/services/app_service.py`
- `backend/app/services/`
- `backend/tests/test_app_service_order_pool.py`
- `backend/tests/test_app_service_process_timeline.py`

## Phase Plan

### P1: 抽离订单池查询 facade

- Objective: 新增专门面向订单池查询的 facade，使路由层不再依赖 `AppService` 处理订单池查询。
- Owned paths:
  - `backend/app/api/routes/app_queries.py`
  - `backend/app/services/`
  - `backend/app/services/app_service.py`
- Dependencies:
  - 现有 provider/runtime
  - 现有 `AppService` 中订单池相关查询逻辑
- Deliverables:
  - 订单池 query facade
  - 订单池 facade provider
  - 更新后的路由依赖

### P2: 保持行为稳定并补齐测试

- Objective: 用已有订单池测试与新增路由依赖测试兜住重构后的行为边界。
- Owned paths:
  - `backend/tests/test_app_service_order_pool.py`
  - `backend/tests/test_app_service_process_timeline.py`
  - `backend/tests/`
- Dependencies:
  - P1 已完成
  - 可运行 pytest
- Deliverables:
  - 路由依赖切换测试
  - 通过的定向 pytest 结果

### P3: 工件闭环

- Objective: 将这轮 facade 重构的执行证据和测试证据写入任务工件并通过 completion gate。
- Owned paths:
  - `doc/tasks/facade-app-queries-appservice-20260419T014536/`
- Dependencies:
  - P1、P2 已完成
- Deliverables:
  - `execution-log.md`
  - `test-report.md`
  - 已完成的 `task-state.json`

## Phase Acceptance Criteria

### P1

- P1-AC1: `app_queries.py` 中订单池相关 5 个接口不再注入 `AppService`，而是注入独立的订单池 query facade。
- P1-AC2: 新 facade 仅承接订单池相关查询，不扩大到无关业务域。
- P1-AC3: `AppService` 保留原有订单池查询逻辑作为过渡实现，facade 通过显式组合调用这些逻辑，不引入 fallback 分支。
- Evidence expectation: 代码 diff、`execution-log.md#Phase-P1`

### P2

- P2-AC1: 订单池相关定向 pytest 通过，确认订单池列表、详情、工序时间线和物料查询行为未被重构打断。
- P2-AC2: 新增或更新的测试能证明路由层已切换到 facade 依赖。
- Evidence expectation: pytest 输出、`test-report.md#T1`、`test-report.md#T2`

### P3

- P3-AC1: `execution-log.md` 与 `test-report.md` 记录了本轮 facade 重构的执行与验证证据。
- P3-AC2: `validate_test_report.py` 与 `check_completion.py --apply` 通过。
- Evidence expectation: 工件内容、completion check

## Done Definition

- 订单池 5 个查询接口完成 facade 切换。
- 定向订单池 pytest 通过。
- 本轮工件和状态文件闭环完成。

## Blocking Conditions

- 发现订单池查询逻辑被更广泛的共享副作用强依赖，导致本轮无法安全抽离独立 facade。
- 任一关键定向测试持续失败且根因超出本轮 facade 切分范围。
