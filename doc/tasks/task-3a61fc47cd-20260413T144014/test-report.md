# Test Report

- Task ID: `task-3a61fc47cd-20260413T144014`
- Created: `2026-04-13T14:40:14`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `排产看板里的每日产能变化增加成两组，一个是产线，一个是工序；可以选择产线，可以选择工序，展示一段时间之内的工序与产线变化；图表改成折线图；去掉每日产能趋势（计划）的统计。`

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-browser
- Tools: playwright, npm, next, python
- Initial readable artifacts: prd.md, test-plan.md
- Initial withheld artifacts: execution-log.md, task-state.json
- Initial verdict before withheld inspection: yes

## Results

### T1: 看板接口按产线与工序聚合对账

- Result: passed
- Covers: P1-AC1, P1-AC2, P1-AC3, P1-AC4, P3-AC1
- Command run: `cd fronted; npm run e2e:playwright -- --grep "T8 scheduler dashboard 30-day correctness reconciliation"`
- Environment proof: Playwright 启动真实 Chromium，并通过仓库内 webServer 启动 Next.js 与 FastAPI；运行时数据库位于 `fronted/test-results/e2e/runtime/production_plan.e2e.db`
- Evidence refs: fronted/test-results/e2e/t8-scheduler-dashboard-30-day-correctness-reconciliation-0.png, fronted/test-results/e2e/t8-scheduler-dashboard-30-day-correctness-reconciliation-0.trace.zip
- Notes: 30 天范围内的汇总指标、每日聚合、按产线变化、按工序变化与物料排行均与独立对账结果一致。

### T2: 看板页面双筛选折线图交互

- Result: passed
- Covers: P2-AC1, P2-AC2, P2-AC3, P2-AC4, P3-AC2
- Command run: `cd fronted; npm run e2e:playwright -- --grep "T6 scheduler dashboard metrics and charts"`
- Environment proof: 调度员真实登录后访问 `/dashboard/scheduler`，在浏览器中切换日期范围、产线筛选与工序筛选
- Evidence refs: fronted/test-results/e2e/t6-scheduler-dashboard-metrics-and-charts-0.png, fronted/test-results/e2e/t6-scheduler-dashboard-metrics-and-charts-0.trace.zip
- Notes: 页面显示新的产线/工序筛选控件与两张折线图，旧计划趋势图与旧变化柱状图已移除，KPI 与物料排行保持正常。

### T3: 看板中文文案与无障碍标签校验

- Result: passed
- Covers: P2-AC3, P3-AC3
- Command run: `cd fronted; npm run e2e:playwright -- tests/e2e/copy-verification.spec.ts --grep "T1 sidebar dashboard metadata copy"`
- Environment proof: 调度员真实登录后检查页面标题、侧边栏文案、Top N 选项和图表 `aria-label`
- Evidence refs: fronted/test-results/e2e/t1-sidebar-dashboard-metadata-copy-0.png, fronted/test-results/e2e/t1-sidebar-dashboard-metadata-copy-0.trace.zip
- Notes: 排产看板标题、Top N 选项、两张折线图与物料饼图的无障碍标签均为正式中文，未出现旧柱状图标签或乱码。

### T4: 前端静态质量门禁

- Result: passed
- Covers: P3-AC4
- Command run: `npm --prefix D:\ProjectPackage\ProductionPlan\fronted run lint`；`cd fronted; npm run build`
- Environment proof: 本地工作区内执行 ESLint 与 Next.js 生产构建
- Evidence refs: fronted/test-results/e2e/t6-scheduler-dashboard-metrics-and-charts-0.trace.zip
- Notes: ESLint 通过；构建首次使用 `npm --prefix ... run build` 时命中沙箱 `spawn EPERM`，改用已放行的 `cd fronted; npm run build` 后构建成功，判定为环境限制而非代码缺陷。

## Final Verdict

- Outcome: passed
- Verified acceptance ids: P1-AC1, P1-AC2, P1-AC3, P1-AC4, P2-AC1, P2-AC2, P2-AC3, P2-AC4, P3-AC1, P3-AC2, P3-AC3, P3-AC4
- Blocking prerequisites:
- Summary: 看板接口、前端展示与真实浏览器验证均通过。新双筛选折线图满足需求，旧计划趋势图已移除，相关页面文案已统一为正式中文。

## Open Issues

- None.
