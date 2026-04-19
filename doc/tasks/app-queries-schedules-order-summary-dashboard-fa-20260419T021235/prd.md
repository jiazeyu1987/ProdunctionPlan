# PRD

- Task ID: `app-queries-schedules-order-summary-dashboard-fa-20260419T021235`
- Created: `2026-04-19T02:12:35`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `继续模块化重构：拆分 app_queries 中剩余的 schedules、order-summary、dashboard 查询依赖，为每个业务域建立独立 facade，进一步降低路由层对 AppService 的直接耦合`

## Goal

完成 `app_queries` 中最后一批仍直接依赖 `AppService` 的查询入口拆分，为 `schedules`、`order-summary`、`dashboard` 分别建立独立 facade，使路由层按业务域完成查询分层。

## Scope

- 抽离 schedules query facade，覆盖：
  - `/schedules/current`
  - `/schedules/current/tasks`
  - `/schedules/snapshots`
- 抽离 order-summary query facade，覆盖：
  - `/order-summary`
  - `/order-summary/workshop-managers`
- 抽离 dashboard query facade，覆盖：
  - `/dashboard/scheduler`
- 增加对应 provider。
- 切换 `app_queries.py` 中对应接口到新 facade。
- 补充 facade/provider 与 route delegation 定向测试。

## Non-Goals

- 不改写 `AppService` 底层业务实现。
- 不调整命令接口、worker 或排产生成逻辑。
- 不引入 fallback facade、双路径兼容或默认成功值。

## Preconditions

- Python 3.12+ 与 pytest 可用。
- 后端测试夹具可运行。
- 若依赖缺失或 pytest 不可用，必须 fail fast。

## Impacted Areas

- `backend/app/api/routes/app_queries.py`
- `backend/app/services/`
- `backend/tests/`

## Phase Plan

### P1: 抽离 schedules query facade

- Objective: 将 schedules 当前查询相关 3 个入口切到独立 facade。
- Owned paths:
  - `backend/app/api/routes/app_queries.py`
  - `backend/app/services/`
- Dependencies:
  - 现有 `AppService` 中 schedules 查询逻辑
- Deliverables:
  - schedules query facade
  - schedules provider
  - 路由依赖切换

### P2: 抽离 order-summary 与 dashboard facade

- Objective: 将 order-summary 和 dashboard 查询入口切到独立 facade。
- Owned paths:
  - `backend/app/api/routes/app_queries.py`
  - `backend/app/services/`
- Dependencies:
  - 现有 `AppService` 中 order-summary 与 dashboard 查询逻辑
- Deliverables:
  - order-summary facade/provider
  - dashboard facade/provider
  - 路由依赖切换

### P3: 定向测试与工件闭环

- Objective: 用 facade/provider 与 route delegation 测试确认本轮切分可用，并完成工件闭环。
- Owned paths:
  - `backend/tests/`
  - `doc/tasks/app-queries-schedules-order-summary-dashboard-fa-20260419T021235/`
- Dependencies:
  - P1、P2 已完成
- Deliverables:
  - 定向 pytest 通过
  - `execution-log.md`
  - `test-report.md`

## Phase Acceptance Criteria

### P1

- P1-AC1: schedules 相关 3 个查询入口不再注入 `AppService`，而是注入独立 schedules facade。
- P1-AC2: schedules facade 只承接 schedules 域查询。
- Evidence expectation: 代码 diff、`execution-log.md#Phase-P1`

### P2

- P2-AC1: order-summary 与 dashboard 查询入口不再注入 `AppService`，而是注入独立 facade。
- P2-AC2: order-summary facade 与 dashboard facade 保持单一业务域职责，不交叉扩张。
- Evidence expectation: 代码 diff、`execution-log.md#Phase-P2`

### P3

- P3-AC1: 定向 pytest 证明三类 facade/provider 与路由委托可用。
- P3-AC2: `validate_test_report.py` 与 `check_completion.py --apply` 通过。
- Evidence expectation: pytest 输出、`test-report.md#T1`、`test-report.md#T2`、`test-report.md#T3`

## Done Definition

- `app_queries.py` 中剩余 schedules、order-summary、dashboard 查询全部完成 facade 切换。
- 定向 pytest 通过。
- 本轮工件和状态文件闭环完成。

## Blocking Conditions

- 发现这三域查询被更大范围共享副作用强耦合，无法在本轮安全抽出 facade。
- 任一关键定向测试持续失败且根因超出本轮 facade 切分范围。
