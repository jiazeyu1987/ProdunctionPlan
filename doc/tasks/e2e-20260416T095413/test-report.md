# Test Report

- Task ID: `e2e-20260416T095413`
- Created: `2026-04-16T09:54:13`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `补全缺失的E2E测试用例`

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-browser
- Tools: playwright
- Initial readable artifacts: prd.md, test-plan.md
- Initial withheld artifacts: task-state.json, execution-log.md
- Initial verdict before withheld inspection: yes

## Results

### T1: Lite scheduler route and toolbar smoke

- Result: passed
- Covers: P1-AC1
- Command run: `npm --prefix D:\ProjectPackage\ProductionPlan\fronted run e2e:playwright -- tests/e2e/lite-scheduler.e2e.spec.ts`
- Environment proof: Playwright Chromium with repo `webServer`, frontend `http://127.0.0.1:2798`, backend `http://127.0.0.1:8000`, authenticated as `scheduler_e2e`.
- Evidence refs: fronted/test-results/e2e/t1-lite-scheduler-route-and-toolbar-smoke-0.png, fronted/test-results/e2e/t1-lite-scheduler-route-and-toolbar-smoke-0.trace.zip
- Notes: `/schedule/lite` 可访问，工具栏、排产模式区和四个主 tab 均可见。

### T2: Lite scheduler snapshot persistence flow

- Result: passed
- Covers: P1-AC2, P1-AC3
- Command run: `npm --prefix D:\ProjectPackage\ProductionPlan\fronted run e2e:playwright -- tests/e2e/lite-scheduler.e2e.spec.ts`
- Environment proof: Playwright Chromium with repo `webServer`; same browser session中完成模式切换、快照保存、推进一天与快照读取，并核对 `localStorage`。
- Evidence refs: fronted/test-results/e2e/t2-lite-scheduler-snapshot-persistence-flow-0.png, fronted/test-results/e2e/t2-lite-scheduler-snapshot-persistence-flow-0.trace.zip
- Notes: 用例验证了快照写入、场景推进后的状态变化，以及读取快照后 UI/存储状态恢复一致。

### T3: Test tools route and tab switching

- Result: passed
- Covers: P2-AC1, P2-AC2
- Command run: `npm --prefix D:\ProjectPackage\ProductionPlan\fronted run e2e:playwright -- tests/e2e/test-tools.e2e.spec.ts`
- Environment proof: Playwright Chromium with repo `webServer`, authenticated as `scheduler_e2e`, route `/test` loaded in real browser.
- Evidence refs: fronted/test-results/e2e/t1-test-tools-route-and-tab-switching-0.png, fronted/test-results/e2e/t1-test-tools-route-and-tab-switching-0.trace.zip
- Notes: 四个 tab 可见且切换后面板内容发生实际变化，不是仅静态按钮存在。

### T4: Test tools local validation without external ERP

- Result: passed
- Covers: P2-AC3
- Command run: `npm --prefix D:\ProjectPackage\ProductionPlan\fronted run e2e:playwright -- tests/e2e/test-tools.e2e.spec.ts`
- Environment proof: Playwright Chromium with repo `webServer`; 在真实页面提交空输入，触发本地校验分支，无需外部 ERP 服务。
- Evidence refs: fronted/test-results/e2e/t2-test-tools-local-validation-without-external-erp-0.png, fronted/test-results/e2e/t2-test-tools-local-validation-without-external-erp-0.trace.zip
- Notes: 订单池、物料供应、物料库存三个输入校验分支都展示了明确错误提示。

### T5: Added specs pass under repo Playwright runner

- Result: passed
- Covers: P3-AC1
- Command run: `npm --prefix D:\ProjectPackage\ProductionPlan\fronted run e2e:playwright -- tests/e2e/lite-scheduler.e2e.spec.ts tests/e2e/test-tools.e2e.spec.ts`
- Environment proof: Repo standard Playwright runner executed both added specs in one Chromium run and returned exit code `0`.
- Evidence refs: fronted/test-results/playwright-report/index.html, fronted/test-results/e2e/t2-test-tools-local-validation-without-external-erp-0.trace.zip
- Notes: 联合执行共 4 条新增测试，全部通过。

### T6: Schedule regression remains passing

- Result: passed
- Covers: P3-AC2
- Command run: `npm --prefix D:\ProjectPackage\ProductionPlan\fronted run e2e:playwright -- tests/e2e/simulation-calendar.e2e.spec.ts`
- Environment proof: Playwright Chromium with repo `webServer`; 既有 `/schedule/calendar` 真实浏览器回归执行通过。
- Evidence refs: fronted/test-results/e2e/t1-simulation-advance-one-day-5-times-and-reset-simulation-0.png, fronted/test-results/e2e/t1-simulation-advance-one-day-5-times-and-reset-simulation-0.trace.zip
- Notes: 相邻排程页面回归未受新增用例和定位点影响。

### T7: Task artifacts capture execution evidence

- Result: passed
- Covers: P3-AC3
- Command run: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id e2e-20260416T095413`
- Environment proof: 本地任务工件与 Playwright 证据文件均存在；`test-report.md` 与 `execution-log.md` 共同记录了命令、结果和证据路径。
- Evidence refs: fronted/test-results/e2e/t1-lite-scheduler-route-and-toolbar-smoke-0.trace.zip, fronted/test-results/e2e/t1-test-tools-route-and-tab-switching-0.trace.zip
- Notes: 该项在报告落盘后通过结构化校验脚本复核。

## Final Verdict

- Outcome: passed
- Verified acceptance ids: P1-AC1, P1-AC2, P1-AC3, P2-AC1, P2-AC2, P2-AC3, P3-AC1, P3-AC2, P3-AC3
- Blocking prerequisites:
- Summary: 新增 `/schedule/lite` 与 `/test` 的真实浏览器 E2E 已通过，联合 runner 与相邻 `/schedule/calendar` 回归也通过，所有 PRD acceptance ids 均有对应测试结果与真实证据文件。

## Open Issues

- Playwright 命令若在同一终端中并行发起多次，会因 `8000/2798` 端口复用而相互冲突；串行执行可稳定通过。
