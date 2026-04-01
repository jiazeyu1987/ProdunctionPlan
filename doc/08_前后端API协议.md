# 前后端 API 协议（按当前前端实现对齐）

更新时间：2026-04-01  
适用范围：`fronted/src`（Next App + Legacy 页面）

## 1. 协议分层
前端当前有两套并行数据源链路，页面显示数据来自以下分层：

1. Next App 路由层（`/api/*`）
2. Legacy Contract 层（`/queries/*`、`/v1/*`、`/internal/v1/internal/*`）
3. Legacy 非 Contract 层（`/api/reportings`、`/api/schedules/generate`、`/api/test/*`）
4. 本地 Mock 数据文件（开发态）

## 2. 页面与数据源映射

### 2.1 新版页面（`src/components/*`）
- 订单列表页：`GET /api/orders`
- 订单详情页基础信息：`GET /api/orders/{orderNo}`
- 生产用料清单：`GET /api/orders/{orderNo}/materials`
- 清单展开子项：`GET /api/materials/{parentMaterialCode}/children`
- 刷新子物料：`POST /api/orders/{orderNo}/materials/refresh`
- 刷新自制：`POST /api/orders/{orderNo}/self-made-materials/refresh`
- 刷新库存：`POST /api/inventory/refresh`
- 报工：`GET /api/orders/{orderNo}/reports`
- 产能：`GET /api/orders/{orderNo}/capacity`

### 2.2 Legacy 页面（`src/legacy/pages/*`）
- 生产订单池、订单详情：`/queries/order-pool` + `/internal/v1/internal/order-pool/*`
- 月历排期：`/queries/schedules*`、`/queries/masterdata-config`、`/queries/calendar-rules`
- 主数据：`/v1/mes/process-routes`、`/queries/masterdata-config`、`/internal/v1/internal/masterdata/*`
- 集成报表：`/internal/v1/internal/integration/*`、`/v1/reports/*`、`/v1/mes/equipments`
- 调度命令/告警/审计：`/queries/dispatch-commands`、`/queries/alerts`、`/queries/audit-logs`、`/internal/v1/internal/dispatch-commands*`
- 测试工具：`/api/test/*`

## 3. 新版 `/api/*` 契约（当前实现）

### 3.1 订单
- `GET /api/orders?keyword=&status=&page=&page_size=`
- `GET /api/orders/{orderNo}`

### 3.2 清单与展开
- `GET /api/orders/{orderNo}/materials`
- `GET /api/materials/{parentMaterialCode}/children`

### 3.3 刷新命令
- `POST /api/orders/{orderNo}/materials/refresh`
- `POST /api/orders/{orderNo}/self-made-materials/refresh`
- `POST /api/inventory/refresh`

### 3.4 报工与产能
- `GET /api/orders/{orderNo}/reports`
- `GET /api/orders/{orderNo}/capacity`

### 3.5 返回约定
- 列表接口：`{ items: T[], total: number }`
- 单对象接口：`{ item: T }`（部分接口直接返回对象，见路由实现）
- 命令接口：`{ success: boolean, message: string }`（个别 legacy 路由返回 `{ ok: true }`）
- 错误：`{ code, message, details }`，并使用 HTTP 非 2xx 状态码

## 4. Legacy Contract 接口清单（当前实现）

### 4.1 Query
- `GET /queries/order-pool`
- `GET /queries/schedules`
- `GET /queries/schedules/{versionNo}`
- `GET /queries/schedules/{versionNo}/tasks`
- `GET /queries/schedules/{versionNo}/algorithm`
- `GET /queries/schedules/{versionNo}/diff?compare_with={versionNo}`
- `GET /queries/schedules/{versionNo}/process-load/daily`
- `GET /queries/masterdata-config`
- `GET /queries/calendar-rules`
- `GET /queries/dispatch-commands`
- `GET /queries/alerts?status=...`
- `GET /queries/audit-logs?request_id=...`
- `GET /v1/mes/process-routes`
- `GET /v1/mes/reportings`
- `GET /v1/mes/equipments`
- `GET /v1/reports/workshop-weekly-plan?version_no=...`
- `GET /v1/reports/workshop-monthly-plan?version_no=...`
- `GET /internal/v1/internal/order-pool/{orderNo}`
- `GET /internal/v1/internal/order-pool/{orderNo}/materials?refresh=true|false`
- `GET /internal/v1/internal/order-pool/materials/{parentMaterialCode}/children?refresh=true|false`
- `GET /internal/v1/internal/material-availability/orders?refresh=true|false`
- `GET /internal/v1/internal/integration/inbox`
- `GET /internal/v1/internal/integration/outbox`

### 4.2 Command
- `POST /internal/v1/internal/dispatch-commands`
- `POST /internal/v1/internal/dispatch-commands/{commandId}/approvals`
- `POST /internal/v1/internal/order-pool/{orderNo}/patch`
- `POST /internal/v1/internal/order-pool/{orderNo}/delete`
- `POST /internal/v1/internal/alerts/{alertId}/ack`
- `POST /internal/v1/internal/alerts/{alertId}/close`
- `POST /internal/v1/internal/simulation/run`
- `POST /internal/v1/internal/simulation/reset`
- `POST /internal/v1/internal/simulation/manual/add-production-order`
- `POST /internal/v1/internal/simulation/manual/advance-day`
- `POST /internal/v1/internal/simulation/manual/reset`
- `POST /internal/v1/internal/schedule-calendar/rules`
- `POST /internal/v1/internal/schedule-versions/{versionNo}/publish`
- `POST /internal/v1/internal/schedule-versions/{versionNo}/rollback`
- `POST /internal/v1/internal/masterdata/config`
- `POST /internal/v1/internal/masterdata/routes/create`
- `POST /internal/v1/internal/masterdata/routes/update`
- `POST /internal/v1/internal/masterdata/routes/copy`
- `POST /internal/v1/internal/masterdata/routes/delete`
- `POST /internal/v1/internal/integration/outbox/{messageId}/retry`
- `POST /api/schedules/generate`（legacy）
- `POST /api/reportings`（legacy）
- `DELETE /api/reportings/{reportId}`（legacy）
- `POST /api/test/import-production-orders`

### 4.3 导出接口
- `GET /v1/reports/workshop-weekly-plan/export?version_no=...`
- `GET /v1/reports/workshop-monthly-plan/export?version_no=...`

### 4.4 测试工具接口
- `GET /api/test/erp/material-issues/{orderNo}?mode=fast|real`
- `GET /api/test/erp/material-supply/{materialCode}`
- `GET /api/test/erp/material-inventory/{materialCode}`
- `POST /api/test/import-production-orders`

## 5. 数据来源文件（开发态）
- 新版 `/api/*` 路由实际由 `src/lib/mock-service.ts` 提供数据
- Legacy Contract/Legacy API 在开发态由 `src/lib/legacy-mock-backend.ts` 提供数据
- 基础样例数据来自 `src/lib/mock-data.ts` 与 `src/lib/mock-data.extra.ts`

## 6. 文档对齐说明
本文件以“前端真实调用”作为主约束。后端实现如有调整，必须同时更新：

1. 本文档的接口清单
2. `04_接口契约与命令行为.md` 的语义定义
3. 对应前端 client（`src/lib/api.ts` 或 `src/legacy/features/*/queryClient|commandClient.js`）
