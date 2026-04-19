# PRD

- Task ID: `app-queries-masterdata-reporting-facade-appservi-20260419T020047`
- Created: `2026-04-19T02:00:47`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `继续模块化重构：按业务域拆分 app_queries 的剩余查询依赖，优先抽离 masterdata 与 reporting 相关 facade，降低路由层对 AppService 的直接耦合`

## Goal

继续沿着 `app_queries` 的查询边界做自上向下拆分，把 `masterdata` 与 `reportings` 相关查询从路由对 `AppService` 的直接依赖中抽离出来，形成按业务域划分的 facade，同时保持现有接口路径、参数和主要返回行为稳定。

## Scope

- 抽离 `masterdata` 查询 facade，覆盖：
  - `/masterdata/config`
  - `/masterdata/calendar-rules`
  - `/masterdata/process-routes`
  - `/masterdata/line-capacity/daily`
  - `/masterdata/line-capacity/daily/audits`
- 抽离 `reportings` 查询 facade，覆盖：
  - `/reportings`
  - `/reportings/import-files`
- 为上述 facade 增加 provider。
- 将 `app_queries.py` 中对应接口切换到新 facade。
- 增加 facade / route delegation 定向测试。

## Non-Goals

- 不在本轮中拆 `schedules/current`、`order-summary`、`dashboard` 查询。
- 不改写 `AppService` 的底层业务实现。
- 不调整命令接口、后台 worker、排产生成逻辑。
- 不引入 fallback facade 或兼容双路径。

## Preconditions

- Python 3.12+ 与 pytest 可用。
- 现有后端测试夹具可使用临时 SQLite 数据库。
- 若缺少依赖或测试环境异常，必须 fail fast。

## Impacted Areas

- `backend/app/api/routes/app_queries.py`
- `backend/app/services/app_service.py`
- `backend/app/services/`
- `backend/tests/`

## Phase Plan

### P1: 抽离 masterdata query facade

- Objective: 将 masterdata 相关 5 个查询入口切换为独立 facade 依赖。
- Owned paths:
  - `backend/app/api/routes/app_queries.py`
  - `backend/app/services/`
- Dependencies:
  - 现有 `AppService` 中 masterdata 查询逻辑
  - 现有 provider/runtime
- Deliverables:
  - masterdata query facade
  - masterdata facade provider
  - 路由依赖切换

### P2: 抽离 reporting query facade

- Objective: 将 reporting 相关 2 个查询入口切换为独立 facade 依赖。
- Owned paths:
  - `backend/app/api/routes/app_queries.py`
  - `backend/app/services/`
- Dependencies:
  - 现有 `AppService` 中 reporting 查询逻辑
- Deliverables:
  - reporting query facade
  - reporting facade provider
  - 路由依赖切换

### P3: 定向测试与工件闭环

- Objective: 用 facade/route delegation 测试和独立 tester 复核确认本轮切分可用，并完成任务工件。
- Owned paths:
  - `backend/tests/`
  - `doc/tasks/app-queries-masterdata-reporting-facade-appservi-20260419T020047/`
- Dependencies:
  - P1、P2 已完成
- Deliverables:
  - 定向 pytest 通过
  - `execution-log.md`
  - `test-report.md`

## Phase Acceptance Criteria

### P1

- P1-AC1: `app_queries.py` 中 masterdata 相关 5 个查询入口不再注入 `AppService`，而是注入独立的 masterdata query facade。
- P1-AC2: masterdata facade 只承接 masterdata 域查询，不扩大到其他业务域。
- Evidence expectation: 代码 diff、`execution-log.md#Phase-P1`

### P2

- P2-AC1: `app_queries.py` 中 reporting 相关 2 个查询入口不再注入 `AppService`，而是注入独立的 reporting query facade。
- P2-AC2: reporting facade 只承接 reporting 域查询，不扩大到其他业务域。
- Evidence expectation: 代码 diff、`execution-log.md#Phase-P2`

### P3

- P3-AC1: 定向 pytest 证明 masterdata/reporting 路由层已切换到 facade，并且 facade 调用路径可用。
- P3-AC2: `validate_test_report.py` 与 `check_completion.py --apply` 通过。
- Evidence expectation: pytest 输出、`test-report.md#T1`、`test-report.md#T2`、`test-report.md#T3`

## Done Definition

- `app_queries.py` 中 masterdata 与 reporting 查询全部完成 facade 切换。
- 定向 pytest 通过。
- 工件与状态文件闭环完成。

## Blocking Conditions

- 发现 masterdata / reporting 查询被更大范围共享副作用强耦合，导致本轮无法安全抽出 facade。
- 任一关键定向测试持续失败且根因超出本轮 facade 切分范围。
