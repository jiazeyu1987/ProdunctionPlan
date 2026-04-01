# 前后端 API 协议
更新时间：2026-04-01

## 1. 范围
本文只描述当前运行代码中仍然有效的接口。

当前前端到后端存在两条调用链，但两条链最终都只访问 FastAPI 的 `/api/*`：
- legacy 页面直连 FastAPI：浏览器 -> `fronted/src/legacy/shared/api/requestCore.js` -> FastAPI
- 新版页面代理链路：浏览器 -> Next Route Handler -> FastAPI `/api/*`

运行态显示数据已经不再来自前端 mock。

## 2. 当前有效接口

### 2.1 查询接口
- `GET /api/health`
- `GET /api/orders`
- `GET /api/orders/{orderNo}`
- `GET /api/orders/{orderNo}/materials`
- `GET /api/materials/{parentMaterialCode}/children`
- `GET /api/orders/{orderNo}/reports`
- `GET /api/orders/{orderNo}/capacity`
- `GET /api/order-pool`
- `GET /api/order-pool/{order_no}`
- `GET /api/order-pool/{order_no}/materials`
- `GET /api/order-pool/materials/{parent_material_code}/children`
- `GET /api/schedules`
- `GET /api/schedules/{version_no}`
- `GET /api/schedules/{version_no}/tasks`
- `GET /api/schedules/{version_no}/algorithm`
- `GET /api/schedules/{version_no}/diff`
- `GET /api/schedules/{version_no}/process-load/daily`
- `GET /api/masterdata/config`
- `GET /api/masterdata/calendar-rules`
- `GET /api/masterdata/process-routes`
- `GET /api/reportings`
- `GET /api/jobs`
- `GET /api/jobs/{jobId}`

### 2.2 异步命令接口
以下接口统一返回 `202 Accepted + job_id`，前端随后轮询 `/api/jobs/{jobId}`：

- `POST /api/orders/{orderNo}/materials/refresh`
- `POST /api/orders/{orderNo}/self-made-materials/refresh`
- `POST /api/inventory/refresh`
- `POST /api/order-pool/{order_no}/patch`
- `POST /api/order-pool/{order_no}/delete`
- `POST /api/dispatch-commands`
- `POST /api/dispatch-commands/{command_id}/approvals`
- `POST /api/masterdata/config`
- `POST /api/masterdata/calendar-rules`
- `POST /api/masterdata/process-routes/create`
- `POST /api/masterdata/process-routes/update`
- `POST /api/masterdata/process-routes/copy`
- `POST /api/masterdata/process-routes/delete`
- `POST /api/schedules/generate`
- `POST /api/schedules/{version_no}/publish`
- `POST /api/simulation/manual/advance-day`
- `POST /api/simulation/manual/reset`
- `POST /api/reportings`
- `DELETE /api/reportings/{report_id}`
- `POST /api/test/erp/material-issues/query`
- `POST /api/test/erp/material-supply/query`
- `POST /api/test/erp/material-inventory/query`
- `POST /api/test/import-production-orders`

### 2.3 命令返回格式
```json
{
  "success": true,
  "job_id": "8d970c2d4c864b44a7e90e642d7d8d18",
  "status_url": "/api/jobs/8d970c2d4c864b44a7e90e642d7d8d18",
  "message": "Task accepted."
}
```

## 3. 历史路径状态
以下路径不再属于当前有效运行接口：
- `/queries/*`
- `/internal/v1/internal/*`
- `/v1/*`

这些路径现在不应写入联调说明、页面实现或新文档中的“有效接口”清单。

## 4. 请求约束

### 4.1 `request_id`
- 所有 `/api/*` 异步命令必须携带 `request_id`
- 前端当前会自动补齐 `request_id`
- 后端按 `request_id` 复用已存在 `job_id`

### 4.2 认证头
- legacy 页面直连后端时会默认带 `Authorization: Bearer mvp-dev-token`
- 当前后端未强制校验该 token
- 这属于开发态兼容事实，不影响当前接口路径正确性

### 4.3 CORS
当前后端允许以下开发源访问：
- `http://127.0.0.1:2798`
- `http://localhost:2798`
- `http://127.0.0.1:3000`
- `http://localhost:3000`

## 5. 正确性结论
- 当前运行态对外接口已经统一到 `/api/*`
- 当前活跃页面的查询和写命令都已走 `/api/*`
- 当前未发现已上线链路中的接口路径、字段名或目标数据源错误
