# SQLite 表设计草案

## 1. 设计目标
本表设计仅服务 `React + FastAPI + SQLite` 的 MVP 版本。

原则：
- 只保留当前业务数据和当前缓存
- 不保留历史批次
- 不存大块 ERP 原始 JSON
- 每张缓存表有明确唯一键

## 2. 表总览
建议最少建立以下表：
- `production_orders`
- `material_issue_items`
- `bom_children`
- `inventory_cache`
- `material_supply_cache`
- `work_reports`
- `capacity_bindings`
- `jobs`

## 3. production_orders
### 用途
保存订单池和订单详情基础数据。

### 建议字段
```sql
CREATE TABLE production_orders (
  production_order_no TEXT PRIMARY KEY,
  material_code TEXT,
  material_name TEXT,
  material_specification TEXT,
  production_qty REAL,
  status TEXT,
  planned_start_date TEXT,
  planned_end_date TEXT,
  source_bill_no TEXT,
  material_list_no TEXT,
  updated_at TEXT NOT NULL
);
```

## 4. material_issue_items
### 用途
保存生产订单根层生产用料清单。

### 唯一规则
- 一个订单下同一个子物料只保留一条当前记录

### 建议字段
```sql
CREATE TABLE material_issue_items (
  production_order_no TEXT NOT NULL,
  child_material_code TEXT NOT NULL,
  child_material_name TEXT,
  spec_model TEXT,
  issue_qty REAL,
  supply_type_code TEXT,
  supply_type_name TEXT,
  inventory_qty REAL,
  inventory_status TEXT,
  usage_numerator REAL,
  usage_denominator REAL,
  child_unit TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (production_order_no, child_material_code)
);
```

## 5. bom_children
### 用途
保存自制物料展开后的下一层 BOM 子项。

### 唯一规则
- 一个父项物料下同一个子项只保留一条当前记录

### 建议字段
```sql
CREATE TABLE bom_children (
  parent_material_code TEXT NOT NULL,
  child_material_code TEXT NOT NULL,
  child_material_name TEXT,
  child_specification TEXT,
  usage_numerator REAL,
  usage_denominator REAL,
  child_unit TEXT,
  supply_type_code TEXT,
  supply_type_name TEXT,
  inventory_qty REAL,
  inventory_status TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (parent_material_code, child_material_code)
);
```

## 6. inventory_cache
### 用途
保存按物料编码聚合后的当前库存快照。

### 唯一规则
- 每个物料编码只有一条当前库存记录

### 建议字段
```sql
CREATE TABLE inventory_cache (
  material_code TEXT PRIMARY KEY,
  inventory_qty REAL,
  inventory_status TEXT NOT NULL,
  snapshot_time TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 说明
- `inventory_status` 可取：`KNOWN`、`UNKNOWN`
- 未查到库存时可以没有数量，但状态必须明确

## 7. material_supply_cache
### 用途
保存物料属性，如自制、外购。

### 建议字段
```sql
CREATE TABLE material_supply_cache (
  material_code TEXT PRIMARY KEY,
  supply_type_code TEXT,
  supply_type_name TEXT,
  snapshot_time TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

## 8. work_reports
### 用途
保存历史报工数据。

### 建议字段
```sql
CREATE TABLE work_reports (
  report_id TEXT PRIMARY KEY,
  production_order_no TEXT NOT NULL,
  process_code TEXT,
  process_name TEXT,
  workshop_code TEXT,
  workshop_name TEXT,
  line_code TEXT,
  line_name TEXT,
  report_qty REAL,
  report_time TEXT,
  operator_name TEXT,
  updated_at TEXT NOT NULL
);
```

## 9. capacity_bindings
### 用途
保存工序、车间、产线对应关系和基础产能信息。

### 建议字段
```sql
CREATE TABLE capacity_bindings (
  production_order_no TEXT NOT NULL,
  process_code TEXT NOT NULL,
  workshop_code TEXT NOT NULL,
  line_code TEXT NOT NULL,
  process_name TEXT,
  workshop_name TEXT,
  line_name TEXT,
  capacity_qty REAL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (production_order_no, process_code, workshop_code, line_code)
);
```

### 说明
- 当前前端接口是 `GET /api/orders/{order_no}/capacity`，MVP 实现直接按订单维度存当前绑定结果

## 9.1 jobs
### 用途
保存异步命令任务状态，支撑 `/api/jobs/*` 轮询。

### 建议字段
```sql
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_key TEXT NOT NULL,
  request_id TEXT UNIQUE,
  status TEXT NOT NULL,
  progress INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  result_json TEXT,
  error_code TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
```

## 10. 推荐索引
```sql
CREATE INDEX idx_material_issue_items_order_no
  ON material_issue_items (production_order_no);

CREATE INDEX idx_bom_children_parent_material
  ON bom_children (parent_material_code);

CREATE INDEX idx_work_reports_order_no
  ON work_reports (production_order_no);

CREATE INDEX idx_jobs_status_created
  ON jobs (status, created_at);
```

## 11. 刷新写入规则
### 刷新子物料
- 先删除 `material_issue_items` 中该订单旧记录
- 再写入当前新记录

### 刷新自制
- 先删除 `bom_children` 中该父项物料旧记录
- 再写入当前新记录

### 刷新库存
- 按 `material_code` 批量 upsert 到 `inventory_cache`

### 刷新物料属性
- 按 `material_code` 批量 upsert 到 `material_supply_cache`

## 12. 明确不做的表设计
MVP 阶段不建议建立：
- ERP 原始大 JSON 行表
- 按刷新批次存历史快照表
- 页面临时状态表
- 复杂任务编排表

## 13. 后续升级空间
如果 MVP 成功，后续可平滑升级到 PostgreSQL，保留同样的领域表结构：
- `production_orders`
- `material_issue_items`
- `bom_children`
- `inventory_cache`
- `material_supply_cache`
- `work_reports`
- `capacity_bindings`
