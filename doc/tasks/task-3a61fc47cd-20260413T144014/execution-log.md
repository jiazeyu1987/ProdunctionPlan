# Execution Log

- Task ID: `task-3a61fc47cd-20260413T144014`
- Created: `2026-04-13T14:40:14`

## Phase Entries

## Phase-P1

- Outcome: completed
- Acceptance ids: `P1-AC1`, `P1-AC2`, `P1-AC3`, `P1-AC4`
- Changed paths:
  - `backend/app/services/app_service.py`
- Summary:
  - 保留现有 `summary`、`daily_capacity` 与 `material_consumption` 返回结构。
  - 在排产看板接口中新增 `capacity_change_by_line` 与 `capacity_change_by_process` 两个分组数据段。
  - 新增按日期全覆盖的产线/工序计划产能与产能变化聚合逻辑，变化值按同一实体相邻日期的计划产能差值计算。
- Validation run:
  - `python -m py_compile backend/app/services/app_service.py`
  - `cd fronted; npm run e2e:playwright -- --grep "T8 scheduler dashboard 30-day correctness reconciliation"`
- Evidence refs:
  - `backend/app/services/app_service.py`
  - `fronted/tests/e2e/support/dashboardReconciliation.ts`
  - `fronted/tests/e2e/production-plan.e2e.spec.ts`
- Remaining risks:
  - 接口排序依赖产线名称与工序编码的稳定性；当前 E2E 已按键值映射对账，未发现不稳定行为。

## Phase-P2

- Outcome: completed
- Acceptance ids: `P2-AC1`, `P2-AC2`, `P2-AC3`, `P2-AC4`
- Changed paths:
  - `fronted/src/legacy/features/dashboard/useSchedulerDashboardController.js`
  - `fronted/src/legacy/pages/SchedulerDashboardPage.jsx`
  - `fronted/src/legacy/features/dashboard/components/SchedulerDashboardLineChart.jsx`
  - `fronted/src/legacy/features/dashboard/components/SchedulerDashboardPieChart.jsx`
  - `fronted/src/legacy/styles/pages/scheduler-dashboard.css`
- Summary:
  - 移除页面中的“每日产能趋势（计划）”卡片与旧“每日产能变化”柱状图。
  - 新增“产线每日产能变化”与“工序每日产能变化”两张折线图，并提供对应筛选下拉框。
  - 修正当前看板页面与饼图组件中的乱码、英文残留和不正式描述，统一为正式中文文案。
- Validation run:
  - `npm --prefix D:\ProjectPackage\ProductionPlan\fronted run lint`
  - `cd fronted; npm run build`
  - `cd fronted; npm run e2e:playwright -- --grep "T6 scheduler dashboard metrics and charts"`
- Evidence refs:
  - `fronted/src/legacy/pages/SchedulerDashboardPage.jsx`
  - `fronted/src/legacy/features/dashboard/components/SchedulerDashboardLineChart.jsx`
  - `fronted/src/legacy/features/dashboard/components/SchedulerDashboardPieChart.jsx`
  - `fronted/src/legacy/styles/pages/scheduler-dashboard.css`
- Remaining risks:
  - 折线图为自绘 SVG 组件，当前已验证桌面宽度与 30 天范围；更长日期范围会继续使用横向滚动承载。

## Phase-P3

- Outcome: completed
- Acceptance ids: `P3-AC1`, `P3-AC2`, `P3-AC3`, `P3-AC4`
- Changed paths:
  - `fronted/tests/e2e/production-plan.e2e.spec.ts`
  - `fronted/tests/e2e/copy-verification.spec.ts`
  - `fronted/tests/e2e/support/backendClient.ts`
  - `fronted/tests/e2e/support/dashboardReconciliation.ts`
- Summary:
  - 将 30 天看板对账逻辑扩展为按产线和按工序两组分项校验。
  - 更新看板 E2E，用真实浏览器验证新筛选控件、新折线图和旧图表移除。
  - 收敛看板文案校验用例，验证页面标题、Top N 选项与图表无障碍标签为正式中文。
- Validation run:
  - `cd fronted; npm run e2e:playwright -- --grep "T6 scheduler dashboard metrics and charts|T8 scheduler dashboard 30-day correctness reconciliation"`
  - `cd fronted; npm run e2e:playwright -- tests/e2e/copy-verification.spec.ts --grep "T1 sidebar dashboard metadata copy"`
  - `npm --prefix D:\ProjectPackage\ProductionPlan\fronted run lint`
  - `cd fronted; npm run build`
- Evidence refs:
  - `fronted/test-results/e2e/t6-scheduler-dashboard-metrics-and-charts-0.png`
  - `fronted/test-results/e2e/t6-scheduler-dashboard-metrics-and-charts-0.trace.zip`
  - `fronted/test-results/e2e/t8-scheduler-dashboard-30-day-correctness-reconciliation-0.png`
  - `fronted/test-results/e2e/t8-scheduler-dashboard-30-day-correctness-reconciliation-0.trace.zip`
  - `fronted/test-results/e2e/t1-sidebar-dashboard-metadata-copy-0.png`
  - `fronted/test-results/e2e/t1-sidebar-dashboard-metadata-copy-0.trace.zip`
- Remaining risks:
  - Playwright 运行过程中仍会出现 React Router v7 future flag 警告，但不影响当前用例结果。

## Outstanding Blockers

- None.
