# 后端 ERP 集成协议
更新时间：2026-04-01

## 1. 目标
本文描述当前后端与 ERP 之间已经落地的通信协议、配置项、请求体和失败语义。

## 2. 当前配置项
后端通过环境变量决定 ERP 连接参数：

- `PRODUCTION_PLAN_ERP_BASE_URL`
- `PRODUCTION_PLAN_ERP_TIMEOUT_SECONDS`
- `PRODUCTION_PLAN_ERP_AUTHORIZATION`
- `PRODUCTION_PLAN_ERP_ORDERS_PATH`
- `PRODUCTION_PLAN_ERP_ORDER_MATERIALS_PATH`
- `PRODUCTION_PLAN_ERP_BOM_CHILDREN_PATH`
- `PRODUCTION_PLAN_ERP_INVENTORY_PATH`
- `PRODUCTION_PLAN_ERP_SUPPLY_PATH`

示例见：`backend/.env.example`

## 3. 调用模型
- 后端统一使用 `ERPClient.post_items()`
- 请求方法固定为 `POST`
- 请求头固定包含：
  - `Content-Type: application/json`
  - `Accept: application/json`
- 当 `PRODUCTION_PLAN_ERP_AUTHORIZATION` 有值时，附带 `Authorization`

ERP 返回必须是：
```json
{
  "items": []
}
```

若不是对象，或者没有 `items` 数组，后端直接报错，不做降级。

## 4. 当前网关与 ERP 路径

### 4.1 订单同步
- 网关：`ERPOrderGateway`
- 路径配置：`PRODUCTION_PLAN_ERP_ORDERS_PATH`
- 当前入口：`backend/scripts/sync_orders.py`
- 请求体：
```json
{}
```

### 4.2 根层用料刷新
- 网关：`ERPMaterialGateway.fetch_order_materials`
- 路径配置：`PRODUCTION_PLAN_ERP_ORDER_MATERIALS_PATH`
- 当前调用方：
  - `/api/orders/{orderNo}/materials/refresh` 对应 worker
  - `/api/test/erp/material-issues/query`
- 请求体：
```json
{
  "production_order_no": "881MO091041"
}
```

### 4.3 自制子项刷新
- 网关：`ERPMaterialGateway.fetch_bom_children`
- 路径配置：`PRODUCTION_PLAN_ERP_BOM_CHILDREN_PATH`
- 当前调用方：
  - `/api/orders/{orderNo}/self-made-materials/refresh` 对应 worker
- 请求体：
```json
{
  "parent_material_code": "A003.017.11.003.2002"
}
```

### 4.4 库存刷新
- 网关：`ERPInventoryGateway.fetch_inventory`
- 路径配置：`PRODUCTION_PLAN_ERP_INVENTORY_PATH`
- 当前调用方：
  - `/api/inventory/refresh` 对应 worker
  - `/api/test/erp/material-inventory/query`
- 请求体：
```json
{
  "material_codes": ["A001.01.004.002", "A002.01.003.000"]
}
```

### 4.5 供给属性刷新
- 网关：`ERPSupplyGateway.fetch_material_supply`
- 路径配置：`PRODUCTION_PLAN_ERP_SUPPLY_PATH`
- 当前调用方：
  - 根层用料刷新流程
  - 自制子项刷新流程
  - `/api/test/erp/material-supply/query`
- 请求体：
```json
{
  "material_codes": ["A001.01.004.002", "A002.01.003.000"]
}
```

## 5. ERP 响应字段约束

### 5.1 订单
ERP 响应字段需满足：
- `production_order_no`
- `material_code`
- `material_name`
- `material_specification`
- `production_qty`
- `status`
- `planned_start_date`
- `planned_end_date`
- `source_bill_no`
- `material_list_no`

### 5.2 根层用料
ERP 响应字段需满足：
- `production_order_no`
- `child_material_code`
- `child_material_name`
- `spec_model`
- `issue_qty`
- `supply_type_code`
- `supply_type_name`

### 5.3 BOM 子项
ERP 响应字段需满足：
- `parent_material_code`
- `child_material_code`
- `child_material_name`
- `child_specification`
- `usage_numerator`
- `usage_denominator`
- `child_unit`
- `supply_type_code`
- `supply_type_name`

### 5.4 库存
ERP 响应字段需满足：
- `material_code`
- `inventory_qty`
- `inventory_status`

其中 `inventory_status` 当前只接受：
- `KNOWN`
- `UNKNOWN`

### 5.5 供给属性
ERP 响应字段需满足：
- `material_code`
- `supply_type_code`
- `supply_type_name`

## 6. ERP 数据写回 SQLite 的位置
- 订单同步 -> `production_orders`
- 根层用料刷新 -> `material_issue_items` + `material_supply_cache`
- 自制子项刷新 -> `bom_children` + `material_supply_cache`
- 库存刷新 -> `inventory_cache`

## 7. 失败语义
当前后端对 ERP 调用采用 fail-fast，不允许 mock、默认成功或静默降级。

### 7.1 当前实际错误码
- `ERP_BASE_URL_MISSING`
- `ERP_ENDPOINT_MISSING`
- `ERP_HTTP_ERROR`
- `ERP_CONNECTION_ERROR`
- `ERP_INVALID_JSON`
- `ERP_INVALID_PAYLOAD`
- `SUPPLY_TYPE_MISSING`

### 7.2 规则
- ERP 基础地址缺失：立即失败
- ERP 路径缺失：立即失败
- ERP 返回非 JSON：立即失败
- ERP 返回结构不符合 `{ items: [...] }`：立即失败
- ERP 未返回物料供给属性而刷新流程又需要它：立即失败
- 库存接口未返回某物料时：写 `inventory_status = UNKNOWN`

## 8. 当前正确性结论

### 8.1 当前正确的部分
- 后端与 ERP 的接口配置项、网关分层、请求体和响应校验都已落地
- ERP 刷新结果会写回 SQLite，再由页面查询 SQLite，不会让页面直接打 ERP
- 配置缺失时后端会明确失败，不会回退 mock

### 8.2 当前需要说明的部分
- 截至 2026-04-01，真实 ERP 是否可达取决于部署环境变量
- 未配置 `PRODUCTION_PLAN_ERP_BASE_URL` 时，相关调用会返回 `ERP_BASE_URL_MISSING`
- 订单同步脚本 `backend/scripts/sync_orders.py` 是后端批处理入口，不属于 HTTP job 接口

## 9. 结论
截至 2026-04-01，后端与 ERP 的通信接口定义是正确的，代码实现与文档一致；当前唯一未必成立的是“真实 ERP 环境是否已配置”，这属于部署前提，不属于接口定义错误。
