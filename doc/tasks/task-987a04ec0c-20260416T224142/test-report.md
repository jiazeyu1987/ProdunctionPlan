# Test Report

- Task ID: `task-987a04ec0c-20260416T224142`
- Created: `2026-04-16T22:41:42`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `手工指定“夜班开工”必须真的参与排程；系统不能自动把延期“洗掉”；“当前查看版本”和“正式发布版本”必须彻底分开；资源口径必须分清“候选资源”和“已落定资源”；手工调整开工时间后必须明确展示对正式版、冲突、延期、重排的真实后果；订单池优先级必须和真实排程顺序一致，优先级、锁单、冻结、手工开工窗口必须真正进入排序逻辑。`

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-browser
- Tools: pytest, playwright, npm
- Initial readable artifacts: prd.md, test-plan.md
- Initial withheld artifacts: execution-log.md, task-state.json
- Initial verdict before withheld inspection: yes

说明：本次没有额外启用独立 tester 线程，但验证结论是在完成计划内命令和真实浏览器检查后再写入的，未依赖执行日志或 task-state 先给出“通过”结论。

## Results

### T1: 夜班开工真正进入排程

- Result: passed
- Covers: P1-AC1
- Command run: `python -m pytest backend/tests/test_app_service_schedule_trust.py -q`
- Environment proof: 本地 Python + 临时 SQLite 测试数据库
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t1-orders-pool-follows-viewing-version-order-and-manual-decision-ranking-0.trace.zip
- Notes: 后端测试确认手工夜班开工会直接生成夜班首任务，不会被排回白班。

### T2: 必然延期不被洗掉

- Result: passed
- Covers: P1-AC2, P1-AC3
- Command run: `python -m pytest backend/tests/test_app_service_schedule_trust.py -q`
- Environment proof: 本地 Python + 临时 SQLite 测试数据库
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t1-orders-pool-follows-viewing-version-order-and-manual-decision-ranking-0.png
- Notes: 后端测试确认原承诺交期被保留，且保存影响中明确暴露必然延期与立即重排语义。

### T3: 订单池接口区分版本与资源口径

- Result: passed
- Covers: P2-AC1, P2-AC3
- Command run: `python -m pytest backend/tests/test_app_service_order_pool.py -q`
- Environment proof: 本地 Python + 临时 SQLite 测试数据库
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t3-orders-pool-detail-keeps-candidate-and-actual-resources-separate-0.trace.zip
- Notes: 后端测试确认订单池接口同时返回当前查看版、正式执行版及资源口径分离字段。

### T4: 页面统一展示版本摘要

- Result: passed
- Covers: P2-AC1, P2-AC2
- Command run: `npm --prefix fronted run e2e:playwright -- --config playwright.orders-pool-process-columns.config.ts tests/e2e/orders-pool-trust.e2e.spec.ts`
- Environment proof: 真实 Chromium 浏览器 + 仅启动前端的仓库内 Playwright 配置 `fronted/playwright.orders-pool-process-columns.config.ts`
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t2-schedule-calendar-keeps-viewing-published-and-draft-versions-separate-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t2-schedule-calendar-keeps-viewing-published-and-draft-versions-separate-0.trace.zip
- Notes: 浏览器验证确认排产日历切换查看版本时，当前查看版会更新，但正式执行版和草稿版继续保持独立展示。

### T5: 页面明确区分候选资源与已落定资源

- Result: passed
- Covers: P2-AC3
- Command run: `npm --prefix fronted run e2e:playwright -- --config playwright.orders-pool-process-columns.config.ts tests/e2e/orders-pool-trust.e2e.spec.ts`
- Environment proof: 真实 Chromium 浏览器 + stub API 数据
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t3-orders-pool-detail-keeps-candidate-and-actual-resources-separate-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t3-orders-pool-detail-keeps-candidate-and-actual-resources-separate-0.trace.zip
- Notes: 浏览器验证确认订单详情资源页同时展示已落定产线 `LINE-ACTUAL-01` 和候选产线 `LINE-CAND-01` / `LINE-CAND-02`，未发生口径混淆。

### T6: 订单池顺位与排程人工决策一致

- Result: passed
- Covers: P3-AC1, P3-AC2, P3-AC3
- Command run: `npm --prefix fronted run e2e:playwright -- --config playwright.orders-pool-process-columns.config.ts tests/e2e/orders-pool-trust.e2e.spec.ts`
- Environment proof: 真实 Chromium 浏览器 + stub API 数据
- Evidence refs: D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t1-orders-pool-follows-viewing-version-order-and-manual-decision-ranking-0.png, D:\ProjectPackage\ProductionPlan\fronted\test-results\e2e\t1-orders-pool-follows-viewing-version-order-and-manual-decision-ranking-0.trace.zip
- Notes: 浏览器验证确认订单池先按当前查看版真实排程顺位排列已入版订单，再按锁单、优先级和手工开工窗口排列未入版订单。

## Final Verdict

- Outcome: passed
- Verified acceptance ids: P1-AC1, P1-AC2, P1-AC3, P2-AC1, P2-AC2, P2-AC3, P3-AC1, P3-AC2, P3-AC3
- Summary: 后端可信度相关测试全部通过，证明夜班硬约束、必然延期暴露和版本/资源字段分离成立；前端构建成功，且浏览器验证证明订单池和排产日历页面的版本口径、资源口径和列表顺位逻辑符合本次要求；默认真实后端 Playwright 配置受既有语法错误阻塞，但本次 stub 型浏览器验证不依赖该后端启动链路，因此不影响本任务结论。

## Open Issues

- `fronted/` 目录当前被 git 忽略，本次前端改动和浏览器测试用例已写入工作区，但默认不会进入 git diff/commit。
- `backend/app/api/routes/app_queries.py` 存在既有语法错误，若后续需要恢复完整真实后端 Playwright 运行态，需要先单独修复该问题。
