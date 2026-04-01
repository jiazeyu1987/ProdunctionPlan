# 后端 SQLite 访问协议
更新时间：2026-04-01

## 1. 目标
本文描述当前 FastAPI 与 SQLite 之间真实已经落地的访问方式，不写目标态假设。

## 2. 基本约束
- 数据库驱动：Python `sqlite3`
- 数据库路径：`PRODUCTION_PLAN_DB_PATH`
- 初始化脚本：`backend/scripts/init_db.py`
- DDL 文件：`backend/sqlite/001_init.sql`
- 前端不得直接访问 SQLite，所有读写都经由 FastAPI

## 3. 连接模型

### 3.1 HTTP 请求线程
- 路由通过 `get_db()` 获取连接
- 查询接口直接读 SQLite
- legacy 同步写接口直接写 SQLite
- `/api/*` 异步命令只写 `jobs` 表

### 3.2 后台 worker
- `JobWorker` 周期性轮询 `jobs`
- worker 使用 `managed_connection()` 独立连接
- worker 负责调用 ERP、写回 SQLite、更新 job 状态

## 4. 当前真实表结构

### 4.1 订单与物料主表
- `production_orders`
- `material_issue_items`
- `bom_children`
- `inventory_cache`
- `material_supply_cache`
- `work_reports`
- `capacity_bindings`

### 4.2 订单池与排产状态表
- `order_pool_state`
- `schedule_versions`
- `schedule_tasks`
- `schedule_calendar_rules`
- `simulation_state`
- `masterdata_process_routes`
- `masterdata_line_topology`
- `dispatch_commands`

### 4.3 异步任务表
- `jobs`

## 5. 表与代码映射

### 5.1 repository 映射
- `ProductionOrderRepository` -> `production_orders`
- `MaterialIssueRepository` -> `material_issue_items`
- `BomChildrenRepository` -> `bom_children`
- `InventoryRepository` -> `inventory_cache`
- `MaterialSupplyRepository` -> `material_supply_cache`
- `WorkReportRepository` -> `work_reports`
- `CapacityRepository` -> `capacity_bindings`
- `JobRepository` -> `jobs`

### 5.2 legacy service 直接访问的表
`LegacyAppService` 还直接访问以下表：
- `order_pool_state`
- `schedule_versions`
- `schedule_tasks`
- `schedule_calendar_rules`
- `simulation_state`
- `masterdata_process_routes`
- `masterdata_line_topology`
- `dispatch_commands`

## 6. 当前接口与读写表关系

### 6.1 `/api/*` 查询
- `GET /api/orders*` -> `production_orders`
- `GET /api/orders/{orderNo}/materials` -> `material_issue_items` + `inventory_cache` + `material_supply_cache`
- `GET /api/materials/{parentMaterialCode}/children` -> `bom_children` + `inventory_cache` + `material_supply_cache`
- `GET /api/orders/{orderNo}/reports` -> `work_reports`
- `GET /api/orders/{orderNo}/capacity` -> `capacity_bindings`
- `GET /api/jobs*` -> `jobs`

### 6.2 `/api/*` 异步命令
- `POST /api/orders/{orderNo}/materials/refresh`
  - 立即写：`jobs`
  - worker 成功后写：`material_issue_items`、`material_supply_cache`
- `POST /api/orders/{orderNo}/self-made-materials/refresh`
  - 立即写：`jobs`
  - worker 成功后写：`bom_children`、`material_supply_cache`
- `POST /api/inventory/refresh`
  - 立即写：`jobs`
  - worker 成功后写：`inventory_cache`

### 6.3 legacy 查询
- `/queries/order-pool` -> `production_orders` + `order_pool_state` + `capacity_bindings` + `masterdata_process_routes` + `masterdata_line_topology`
- `/queries/schedules*` -> `schedule_versions` + `schedule_tasks`
- `/queries/masterdata-config` -> `schedule_calendar_rules` + `masterdata_process_routes` + `masterdata_line_topology`
- `/queries/calendar-rules` -> `schedule_calendar_rules`
- `/v1/mes/process-routes` -> `masterdata_process_routes`
- `/v1/mes/reportings` -> `work_reports`

### 6.4 legacy 写接口
- 订单编辑/删除 -> `order_pool_state` / `production_orders`
- 报工增删 -> `work_reports`
- 派工命令 -> `dispatch_commands`，并回写 `order_pool_state`
- 主数据保存 -> `masterdata_line_topology`、`masterdata_process_routes`、`schedule_calendar_rules`
- 排产生成/发布 -> `schedule_versions`、`schedule_tasks`
- 模拟推进/重置 -> `simulation_state`
- 测试工具导入 -> `production_orders`

## 7. 事务规则
- 需要“删旧写新”的刷新逻辑必须放在同一事务中
- job 成功与失败状态更新各自独立提交
- 不允许部分成功后静默忽略剩余写入失败

当前真实事务点包括：
- `replace_for_order`
- `replace_for_parent`
- `inventory_cache` 批量 upsert
- `production_orders` 全量同步
- legacy 主数据、排产、派工、报工等写操作

## 8. 正确性结论

### 8.1 当前正确的部分
- 后端到 SQLite 的访问边界清晰，前端没有绕过后端直连数据库
- 当前已落库表足以支撑现在可见页面
- `/api/*` 异步任务的入队、worker 领取、结果回写链路已经成立

### 8.2 当前需要注意的部分
- legacy 功能较多，仍有一部分业务逻辑直接放在 `LegacyAppService`，还未全部沉淀到 `/api/*` 正式层
- 这不是运行错误，但说明数据库访问层目前仍是“正式接口 + 兼容层并存”

## 9. 结论
截至 2026-04-01，后端与 SQLite 的数据通信接口是正确的，且与当前实现一致；主要剩余问题不是“读写错误”，而是接口与服务层尚未完全收口。
