# React + FastAPI + SQLite MVP 重写架构建议

## 1. 目标
本次重写目标不是完整替代现有系统，而是先做一个能稳定跑通核心业务链路的 MVP。

技术栈确定为：
- 前端：`React`
- 后端：`FastAPI`
- 数据库：`SQLite`
- ORM：`SQLAlchemy`
- 迁移：`Alembic`
- 前端数据层：`React Query`

## 2. MVP 范围
### 2.1 本期必须做
- 生产订单列表
- 生产订单详情
- `详情 / 清单 / 报工 / 产能` 四个 tab
- 根层生产用料清单
- 自制子物料展开
- `刷新子物料`
- `刷新自制`
- `刷新库存`
- SQLite 持久化缓存恢复

### 2.2 本期可以只做只读
- 报工列表
- 工序/车间/产线对应

### 2.3 本期不做
- 排程
- 仿真
- 复杂任务调度中心
- Redis
- 多实例部署
- 历史批次缓存
- ERP 原始 JSON 全量持久化

## 3. 总体架构
### 3.1 前端
- React 页面负责展示和交互
- React Query 负责查询缓存和 mutation
- 树表负责渲染用料清单与自制展开层级

### 3.2 后端
- FastAPI 提供 query 和 command 接口
- Service 层负责业务聚合
- Repository 层负责 SQLite 读写
- ERP Gateway 层负责和 ERP 通信

### 3.3 数据层
- SQLite 只保存当前业务数据与当前缓存
- 不保存历史批次
- 不长期保存大块 ERP 原始明细 JSON

## 4. 后端目录建议
```text
backend/
  app/
    main.py
    api/
      orders.py
      materials.py
      inventory.py
      reports.py
      capacity.py
    schemas/
      order.py
      material.py
      inventory.py
      report.py
      capacity.py
    services/
      order_query_service.py
      material_query_service.py
      material_refresh_service.py
      bom_expand_service.py
      inventory_service.py
      report_query_service.py
      capacity_query_service.py
    repositories/
      order_repository.py
      material_issue_repository.py
      bom_children_repository.py
      inventory_repository.py
      supply_repository.py
      report_repository.py
      capacity_repository.py
    gateway/
      erp_client.py
      erp_order_gateway.py
      erp_material_gateway.py
      erp_inventory_gateway.py
    db/
      base.py
      session.py
      models.py
```

## 5. 前端目录建议
```text
frontend/
  src/
    pages/
      OrdersPage.tsx
      OrderDetailPage.tsx
    features/
      orders/
      order-detail/
      materials/
      reports/
      capacity/
    components/
      MaterialTreeTable.tsx
      InventoryCell.tsx
      SupplyTypeCell.tsx
    api/
      client.ts
      orders.ts
      materials.ts
      inventory.ts
```

## 6. API 设计
### 6.1 Query
- `GET /api/orders`
- `GET /api/orders/{order_no}`
- `GET /api/orders/{order_no}/materials`
- `GET /api/materials/{parent_material_code}/children`
- `GET /api/orders/{order_no}/reports`
- `GET /api/orders/{order_no}/capacity`

### 6.2 Command
- `POST /api/orders/{order_no}/materials/refresh`
- `POST /api/orders/{order_no}/self-made-materials/refresh`
- `POST /api/inventory/refresh`

## 7. SQLite 使用原则
### 7.1 为什么 MVP 选 SQLite
- 部署简单
- 本地开发快
- 不依赖外部数据库服务
- 适合单机 MVP 验证

### 7.2 约束
- 只支持单实例
- 不适合长期堆积原始缓存
- 不适合复杂并发写入
- 不做历史批次留存

### 7.3 明确禁止
- 不将 ERP 原始大 JSON 持续落库
- 不对同一订单按刷新轮次无限追加
- 不把页面临时状态持久化为业务真相

## 8. 缓存设计
### 8.1 只保留当前版本
对以下数据只保留一个当前版本：
- 订单根层子物料清单
- 自制物料展开子项
- 即时库存
- 物料属性

### 8.2 页面语义
- 库存没有缓存时显示 `未知`
- 不因为页面首次打开就全量刷新 ERP
- 只有用户显式点击刷新按钮时才强制回 ERP

## 9. 推荐开发顺序
### 第一阶段
- 建 SQLite 表
- 打通订单列表
- 打通订单详情
- 打通清单 tab

### 第二阶段
- 打通自制子物料展开
- 打通刷新子物料
- 打通刷新自制
- 打通刷新库存

### 第三阶段
- 补报工 tab
- 补产能 tab
- 做页面交互和错误态

## 10. 开发原则
- 严格区分 ERP 查询层和业务聚合层
- 严格区分 query 和 command
- 默认覆盖当前版本，不保留历史批次
- 数据缺失时明确失败或显示 `未知`
- 不做静默降级
- 不返回假数据
