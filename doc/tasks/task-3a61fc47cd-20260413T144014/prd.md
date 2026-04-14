# PRD

- Task ID: `task-3a61fc47cd-20260413T144014`
- Created: `2026-04-13T14:40:14`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `排产看板里的每日产能变化增加成两组，一个是产线，一个是工序；可以选择产线，可以选择工序，展示一段时间之内的工序与产线变化；图表改成折线图；去掉每日产能趋势（计划）的统计。`

## Goal

将排产看板中的“每日产能变化”改造成两个独立的时间序列分析区域，分别按产线和工序展示指定时间范围内的每日产能变化，并支持用户筛选单个产线或单个工序查看折线趋势；同时移除“每日产能趋势（计划）”统计卡片，保持其余看板指标和物料消耗排行行为稳定。

## Scope

- 后端排产看板接口聚合逻辑与返回结构
- 排产看板页面的数据获取、状态管理、筛选交互与中文文案
- 排产看板折线图组件与相关样式
- 看板 E2E、文案校验与看板数据对账辅助代码

## Non-Goals

- 不修改订单完成率、设备损坏率、总产能、实际总产能的统计口径
- 不修改物料消耗排行的排序规则、字段结构或展示方式
- 不新增兼容旧图表的兜底分支、临时 mock 数据或静态占位数据
- 不改动车间主任的权限模型或侧边栏路由权限
- 不重写看板之外的其他页面布局或图表实现

## Preconditions

- `backend` 与 `fronted` 依赖已安装，可执行 Python、`npm --prefix fronted run lint`、`npm --prefix fronted run build` 与 Playwright
- E2E 所依赖的真实测试数据库和 Playwright 启动配置可正常运行
- `/api/dashboard/scheduler` 访问所依赖的 `masterdata_line_topology`、订单汇总、物料消耗相关数据在目标时间范围内存在真实记录
- 若前置条件缺失，必须停止执行并记录到 `task-state.json.blocking_prereqs`

## Impacted Areas

- `backend/app/services/app_service.py` 中排产看板数据聚合逻辑
- `backend/app/api/routes/app_queries.py` 中排产看板查询入口
- `fronted/src/legacy/features/dashboard/useSchedulerDashboardController.js`
- `fronted/src/legacy/features/dashboard/schedulerDashboardQueryClient.js`
- `fronted/src/legacy/pages/SchedulerDashboardPage.jsx`
- `fronted/src/legacy/features/dashboard/components/`
- `fronted/src/legacy/styles/pages/scheduler-dashboard.css`
- `fronted/tests/e2e/production-plan.e2e.spec.ts`
- `fronted/tests/e2e/copy-verification.spec.ts`
- `fronted/tests/e2e/support/backendClient.ts`
- `fronted/tests/e2e/support/dashboardReconciliation.ts`

## Phase Plan

### P1: 扩展排产看板后端聚合结构

- Objective:
  基于真实的每日产能明细，按日期聚合出“按产线”和“按工序”两组每日产能变化时间序列，并为前端提供稳定的筛选项数据。
- Owned paths:
  `backend/app/services/app_service.py`
  `backend/app/api/routes/app_queries.py`
- Dependencies:
  `list_line_daily_capacity(calendar_date)` 返回的明细中已包含 `line_code`、`line_name`、`process_code`
- Deliverables:
  排产看板接口新增 `capacity_change_by_line` 与 `capacity_change_by_process` 两个数据段，包含筛选项和覆盖完整日期范围的每日变化折线数据

### P2: 重构排产看板前端展示与交互

- Objective:
  移除原“每日产能趋势（计划）”图表，将“每日产能变化”拆分为产线和工序两张折线图，并提供筛选控件与正式中文文案。
- Owned paths:
  `fronted/src/legacy/features/dashboard/useSchedulerDashboardController.js`
  `fronted/src/legacy/features/dashboard/schedulerDashboardQueryClient.js`
  `fronted/src/legacy/pages/SchedulerDashboardPage.jsx`
  `fronted/src/legacy/features/dashboard/components/SchedulerDashboardLineChart.jsx`
  `fronted/src/legacy/styles/pages/scheduler-dashboard.css`
- Dependencies:
  P1 已提供前端所需的分组时间序列与筛选项数据
- Deliverables:
  新的折线图组件、两个筛选区域、正式中文标签与空态文案，以及删除旧的计划趋势图表展示

### P3: 更新自动化验证与数据对账

- Objective:
  让自动化测试能独立验证新接口结构、新 UI 行为和 30 天范围内的折线数据正确性，并回归中文展示。
- Owned paths:
  `fronted/tests/e2e/production-plan.e2e.spec.ts`
  `fronted/tests/e2e/copy-verification.spec.ts`
  `fronted/tests/e2e/support/backendClient.ts`
  `fronted/tests/e2e/support/dashboardReconciliation.ts`
- Dependencies:
  P1、P2 完成且 Playwright 可使用真实浏览器启动应用
- Deliverables:
  更新后的 Playwright 用例、对账辅助逻辑、命令验证结果与可追溯证据

## Phase Acceptance Criteria

### P1

- P1-AC1:
  `/api/dashboard/scheduler` 返回结果中新增 `capacity_change_by_line` 与 `capacity_change_by_process`，每个数据段都必须包含 `options` 与 `items`，且数据来自真实每日产能明细聚合结果。
- P1-AC2:
  `capacity_change_by_line.items` 必须按所请求的日期范围覆盖每天数据；每条产线序列都要包含日期、产线编码、产线名称和当天产能变化值，变化值按同一产线相邻日期的计划产能差值计算。
- P1-AC3:
  `capacity_change_by_process.items` 必须按所请求的日期范围覆盖每天数据；每条工序序列都要包含日期、工序编码、工序名称和当天产能变化值，变化值按同一工序相邻日期的计划产能差值计算。
- P1-AC4:
  现有 `summary`、`material_consumption` 结构和统计口径保持可用，不因本次改造被移除或静默降级。
- Evidence expectation:
  `execution-log.md` 需记录新增接口字段、聚合规则、受影响路径与至少一组基于真实数据的校验结果

### P2

- P2-AC1:
  排产看板页面不再展示“每日产能趋势（计划）”，改为“产线每日产能变化”和“工序每日产能变化”两张折线图卡片。
- P2-AC2:
  页面必须提供产线筛选下拉框和工序筛选下拉框；切换日期范围或筛选项后，折线图展示的数据与当前选择一致。
- P2-AC3:
  折线图组件必须使用折线形式展示时间范围内的每日变化，且在空数据时显示正式中文空态文案，不得出现乱码、英文残留或内部字段名。
- P2-AC4:
  现有 KPI 卡片与物料消耗排行仍能正常渲染，页面整体布局在桌面与窄屏宽度下可用。
- Evidence expectation:
  `execution-log.md` 需记录页面改动、交互结果、折线图渲染方式与样式调整说明

### P3

- P3-AC1:
  自动化对账逻辑必须独立计算并验证 30 天范围内按产线和按工序的每日产能变化结果，与看板接口返回值逐项一致。
- P3-AC2:
  Playwright 真实浏览器用例必须验证排产看板中新的两个筛选控件、两个折线图容器以及旧计划趋势图已移除。
- P3-AC3:
  文案验证用例必须覆盖排产看板相关标题、图表无障碍标签和筛选项中文文案，确保当前页面不再出现乱码或未翻译英文。
- P3-AC4:
  `npm --prefix fronted run lint`、`npm --prefix fronted run build` 以及目标 Playwright 用例必须通过。
- Evidence expectation:
  `test-report.md` 需引用 Playwright 证据文件和命令结果，并对应列出覆盖的验收项

## Done Definition

- P1、P2、P3 全部标记为 `completed`
- P1-AC1 至 P3-AC4 全部具有可追溯证据
- 排产看板页面中的产能变化分析改为双筛选折线图，且旧“每日产能趋势（计划）”已移除
- 接口、页面和 E2E 验证均未引入 fallback、mock 或静默降级逻辑
- `test_status` 为 `passed`，且 `check_completion.py --apply` 校验通过

## Blocking Conditions

- 排产看板真实数据源在目标日期范围内缺失，导致无法生成按产线或按工序的真实时间序列
- Playwright 无法启动真实浏览器或应用运行环境，导致无法完成 UI 验证
- 当前工作区存在直接冲突的未提交改动并覆盖本次任务目标文件，导致无法安全合并本次实现
- `lint`、`build` 或目标 E2E 持续失败且失败原因不是本次改动可修复范围内的问题
