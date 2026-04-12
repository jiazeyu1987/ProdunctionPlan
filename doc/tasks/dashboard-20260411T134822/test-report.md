# Test Report

- Task ID: dashboard-20260411T134822
- Created: 2026-04-11T13:48:22
- Workspace: D:\ProjectPackage\ProductionPlan
- User Request: 给排产员做一个 dashboard，默认最近一个月，可统计订单完成率、设备损坏率、总产能、每日产能变化、物料消耗排名，并以柱状图/饼图展示。

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-browser
- Tools: playwright, node, npm, python
- Initial readable artifacts: prd.md, test-plan.md
- Initial withheld artifacts: execution-log.md, task-state.json
- Initial verdict before withheld inspection: yes

## Results

### T1: Backend dashboard API returns required payload

- Result: passed
- Covers: P1-AC1, P1-AC2
- Command run: cd fronted && npm run e2e:browser (T6 includes schedulerApi.getSchedulerDashboard(BASE_DATE, BASE_DATE, 8))
- Environment proof: scheduler authenticated browser session on http://127.0.0.1:2798/dashboard/scheduler
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t6-scheduler-dashboard-metrics-and-charts-0.trace.zip, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t6-scheduler-dashboard-metrics-and-charts-0.png
- Notes: API payload includes range, summary, daily_capacity, material_consumption.

### T2: KPI calculation semantics are correct

- Result: passed
- Covers: P1-AC3, P1-AC4
- Command run: cd fronted && npm run e2e:browser (T6 dashboard assertions)
- Environment proof: runtime DB seeded and exercised through real backend + browser session
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\evidence-manifest.json, D:\ProjectPackage\ProductionPlan\fronted\test-results\playwright-output\production-plan.e2e-produc-5596f-ashboard-metrics-and-charts\video.webm
- Notes: summary fields are numeric and failure-rate semantics match backend rule machine_count < required_machines.

### T3: Scheduler can open dashboard and see default month range

- Result: passed
- Covers: P2-AC1, P2-AC2
- Command run: cd fronted && npm run e2e:browser (T6 dashboard route/filter flow)
- Environment proof: scheduler can open dashboard from sidebar and apply date range filters
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t6-scheduler-dashboard-metrics-and-charts-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t6-scheduler-dashboard-metrics-and-charts-0.trace.zip
- Notes: dashboard loads with default month and supports custom start/end dates.

### T4: Dashboard shows required KPI cards and charts

- Result: passed
- Covers: P2-AC3, P2-AC4
- Command run: cd fronted && npm run e2e:browser (T6 dashboard rendering assertions)
- Environment proof: real-browser scheduler dashboard renders KPI cards, bar charts, pie chart, and ranking table
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t6-scheduler-dashboard-metrics-and-charts-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\playwright-output\production-plan.e2e-produc-5596f-ashboard-metrics-and-charts\video.webm
- Notes: required chart blocks render with non-empty material ranking on base date.

### T5: Non-scheduler access is blocked

- Result: passed
- Covers: P2-AC1
- Command run: cd fronted && npm run e2e:browser (T7 role-guard case)
- Environment proof: workshop manager session redirected to /capacity/daily when opening /dashboard/scheduler
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t7-workshop-manager-cannot-access-scheduler-dashboard-route-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t7-workshop-manager-cannot-access-scheduler-dashboard-route-0.trace.zip
- Notes: scheduler-only nav item is hidden for workshop manager.

### T6: Dashboard regression does not break existing scheduler flow

- Result: passed
- Covers: P3-AC2
- Command run: cd fronted && npm run e2e:browser
- Environment proof: full regression run executed in a single real-browser pass (T2~T7)
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\browser-run-summary.json, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\evidence-manifest.json
- Notes: legacy scheduler/workshop manager cases remained green after dashboard integration.

### T7: Dashboard-specific case is evidence-backed

- Result: passed
- Covers: P3-AC1
- Command run: cd fronted && npm run e2e:browser
- Environment proof: dashboard-specific case T6 passed with screenshot, trace, and video evidence
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t6-scheduler-dashboard-metrics-and-charts-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t6-scheduler-dashboard-metrics-and-charts-0.trace.zip, D:\ProjectPackage\ProductionPlan\fronted\test-results\playwright-output\production-plan.e2e-produc-5596f-ashboard-metrics-and-charts\video.webm
- Notes: evidence artifacts are non-task files under fronted/test-results.

## Final Verdict

- Outcome: passed
- Verified acceptance ids: P1-AC1, P1-AC2, P1-AC3, P1-AC4, P2-AC1, P2-AC2, P2-AC3, P2-AC4, P3-AC1, P3-AC2
- Blocking prerequisites:
- Summary: Scheduler dashboard backend/frontend/test coverage is complete, real-browser validation passed, and regression remained stable.

## Open Issues

- None.
