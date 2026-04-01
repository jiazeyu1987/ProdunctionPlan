# ERP 集成与缓存链路

## 1. 当前 ERP 集成能力
系统当前需要从 ERP 获取以下数据：
- 生产订单
- 生产用料清单根层子物料
- BOM 子项明细
- 物料属性/供应类型
- 即时库存
- 报工相关数据

## 2. 当前关键业务链路
### 2.1 根层生产用料清单
- 输入：`production_order_no`
- 来源：生产订单相关 ERP 子物料查询
- 输出：根层 `MaterialIssueItem`

### 2.2 自制子物料展开
- 输入：`parent_material_code = 当前清单行的 child_material_code`
- 来源：ERP 物料清单列表 `ENG_BOM` 的已审核 BOM
- 匹配规则：`父项物料编码 = 当前自制物料编码`
- 输出：子项编码、名称、规格、用量分子、用量分母、子项单位等

### 2.3 即时库存
- 输入：`material_code[]`
- 来源：ERP 库存查询
- 输出：按物料编码聚合后的当前库存数量

### 2.4 物料属性
- 输入：`material_code`
- 来源：ERP 供应或物料属性查询
- 输出：自制、外购等属性

## 3. 当前缓存问题总结
### 已识别问题
- 原始 ERP 行 JSON 长期落 H2，导致库文件暴涨
- 某些链路过去按历史批次追加，不按唯一键覆盖
- 重启后冷热缓存切换复杂，影响首开性能
- 冷启动阶段不应因缺库存而全量打 ERP

## 4. 重写后的缓存策略建议
### 4.1 原则
- 缓存服务于查询，不参与业务真相竞争
- 只存当前版本，不存历史批次
- 每类缓存使用明确唯一键
- 页面聚合结果可缓存，但可随时重建

### 4.2 建议缓存表
#### `material_issue_cache`
- 唯一键：`production_order_no + child_material_code`
- 保存根层生产用料清单当前版本

#### `bom_children_cache`
- 唯一键：`parent_material_code + child_material_code`
- 保存自制物料展开结果当前版本

#### `inventory_cache`
- 唯一键：`material_code`
- 保存物料当前库存快照

#### `material_supply_cache`
- 唯一键：`material_code`
- 保存物料属性当前快照

## 5. 推荐的数据存储分层
### 原始层 Raw
- 只在确有调试/审计需求时保留
- 默认不存全量 ERP 原始 JSON

### 规范层 Canonical
- 将 ERP 数据映射为标准业务对象
- 这是后端领域服务的正式输入

### 聚合层 Projection
- 面向页面查询
- 可重建、可覆盖、不保留历史批次

## 6. 重写时必须明确的规则
- `issue_qty` 是正式字段
- `inventory_qty` 是正式字段
- `supply_type_name` 是正式字段
- `未知` 是页面语义，不是数据库默认成功值
- 缓存缺失时允许返回“未知”，但不能伪造库存数值
