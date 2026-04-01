# /api 统一接口与异步任务规范
更新时间：2026-04-01

## 1. 目标
系统对外只保留一套正式接口：
- `/api/*`

MVP 约束不变：
- 前端不持有业务真数据
- 页面显示数据来自后端 SQLite
- 访问 ERP 或批量重算的操作不能阻塞前端和后端
- 不做 fallback，不用 mock 覆盖失败

## 2. 当前实现状态
- 当前活跃页面的查询和写命令已经全部收口到 `/api/*`
- 旧的 `/queries/*`、`/internal/v1/internal/*`、`/v1/*` 兼容路由已移除
- 当前正式路由集中在 `backend/app/api/routes/*.py`

## 3. `/api/*` 规范

### 3.1 查询接口
- 方法：`GET`
- 数据源：只读 SQLite
- 要求：快速返回，不在查询请求中直连 ERP 做长耗时操作

### 3.2 命令接口
- 方法：`POST` 或 `DELETE`
- 返回：`202 Accepted`
- 响应体包含：`success`、`job_id`、`status_url`、`message`
- 要求：命令接口只负责入队，不在 HTTP 请求中执行长任务

### 3.3 Job 状态机
- `PENDING`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`

### 3.4 幂等
- 异步命令必须带 `request_id`
- 后端对同一 `request_id` 复用已有 `job_id`

## 4. 前端调用规范

### 4.1 新版页面
- 通用封装：`fronted/src/lib/jobs.ts`
- 统一入口：`submitCommandAndTrackJob()`

### 4.2 legacy 页面
- 通用封装：`fronted/src/legacy/shared/api/jobClient.js`
- 统一命令入口：`requestCommandAndTrackJob()`
- legacy 页面虽然目录仍叫 legacy，但当前实际也只访问 `/api/*`

### 4.3 前端统一流程
1. 提交命令
2. 收到 `202 + job_id`
3. 轮询 `GET /api/jobs/{jobId}`
4. 任务结束后刷新查询接口

前端禁止：
- 命令刚返回就假定业务已成功
- 轮询超时后把任务当作成功
- 用本地业务数据覆盖后端结果

## 5. 当前已异步化的操作
- 刷新根层用料
- 刷新自制子项
- 刷新库存
- 订单池编辑和删除
- 派工命令创建和审批
- 报工新增和删除
- 排产生成和发布
- 月历规则保存
- 模拟推进一天和重置
- 主数据配置保存
- 工艺路线增删改复制
- ERP 测试查询
- 测试订单导入

## 6. 当前剩余问题
当前剩余问题已经不在接口路径层，主要是：
- 后端内部仍保留 `LegacyAppService` 这类历史命名
- 仍有批处理脚本入口，例如 `backend/scripts/sync_orders.py`
- 前端运行态 mock 数据文件已经移除

## 7. 结论
截至 2026-04-01，`/api/*` 正式接口和异步 job 机制已经成立，当前运行态对外接口已不再保留 legacy URL。
