# PRD

- Task ID: `task-987a04ec0c-20260416T224142`
- Created: `2026-04-16T22:41:42`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `手工指定“夜班开工”必须真的参与排程；系统不能自动把延期“洗掉”；“当前查看版本”和“正式发布版本”必须彻底分开；资源口径必须分清“候选资源”和“已落定资源”；手工调整开工时间后必须明确展示对正式版、冲突、延期、重排的真实后果；订单池优先级必须和真实排程顺序一致，优先级、锁单、冻结、手工开工窗口必须真正进入排序逻辑。`

## Goal

收口当前生产排程系统的“可信执行口径”，让排产员在订单池、订单详情和排产日历里看到的约束、风险、版本和资源含义，与排程引擎真实使用的逻辑保持一致，不再出现“夜班只是展示值”“延期被洗掉”“查看版和正式版混口径”“候选资源看起来像已落线”“订单池排序和算法顺序不一致”的情况。

## Scope

- `backend/app/services/app_service.py` 中订单池、订单详情、版本上下文、手工开工保存影响、排程候选排序与生成逻辑。
- `backend/tests/test_app_service_schedule_trust.py`、`backend/tests/test_app_service_order_pool.py` 中与排程可信度相关的后端回归用例。
- `fronted/src/legacy/features/order-execution/ordersPoolService.js` 中订单池快照与版本上下文映射。
- `fronted/src/legacy/features/orders-pool/page/*` 与 `fronted/src/legacy/features/orders-pool/selectors.js` 中订单池列表、详情、保存开工预览、资源口径和页面排序逻辑。
- `fronted/src/legacy/features/schedule-calendar/*` 中排产日历版本口径展示。
- 如有必要，新增与上述改动直接相关的前端 Playwright 回归用例。

## Non-Goals

- 不重写整个排产引擎，不引入新的排产策略类型。
- 不扩展到报工、产能维护、ERP 同步、部署脚本等与本次可信度收口无直接关系的链路。
- 不新增 fallback、兼容分支、默认成功占位值或“看起来正常”的风险掩盖逻辑。
- 不批量清理仓库内现有乱码或历史文案问题，除非这些文案正好位于本次改动路径且会影响当前需求表达。

## Preconditions

- 本地 Python 环境可运行仓库现有后端测试。
- `backend` 现有 SQLite 初始化逻辑和测试夹具可正常创建临时数据库。
- `fronted` 依赖已安装，能够运行现有 Playwright 或前端构建相关命令。
- 当前仓库中的未提交改动不会阻塞本次目标路径的继续修改；若发现直接冲突，必须停止并明确报告冲突文件和影响。

## Impacted Areas

- 订单池接口 `list_order_pool` 和订单详情接口 `get_order_pool_item` 的返回字段将决定前端版本口径、风险提示和资源口径展示。
- `patch_order_pool_order` 的保存结果会影响手工开工预览和保存后反馈。
- `generate_schedule`、`_sort_schedule_candidates`、`_select_next_candidate_index` 和相关候选上下文生成逻辑决定夜班开工、优先级、锁单、冻结和手工窗口是否真正进入排程顺序。
- 订单池前端排序、表格渲染和详情面板文案决定用户是否把页面顺序误解为真实执行顺序。
- 排产日历设置面板的版本摘要决定“当前查看版 / 正式执行版 / 草稿版”是否在不同页面保持一致。

## Phase Plan

### P1: 收口排程硬约束与延期暴露

- Objective: 让手工开工日期/班次真实进入排程窗口与候选顺序，并保证必然延期风险直接暴露，不允许通过顺延交期或模糊提示掩盖。
- Owned paths:
  - `backend/app/services/app_service.py`
  - `backend/tests/test_app_service_schedule_trust.py`
  - `backend/tests/test_app_service_order_pool.py`
- Dependencies:
  - `order_pool_state.expected_start_date`
  - `order_pool_state.expected_start_time`
  - `order_pool_state.promised_due_date`
  - `schedule_tasks`
- Deliverables:
  - 排程生成逻辑对手工夜班开工的真实使用与回归测试
  - 必然延期判断、保存影响摘要与相关回归测试

### P2: 统一版本与资源口径展示

- Objective: 在订单池与排产日历中统一“当前查看版 / 正式执行版 / 草稿版”表达，并确保“候选资源”与“已落定资源”在数据和 UI 上彻底分开。
- Owned paths:
  - `backend/app/services/app_service.py`
  - `fronted/src/legacy/features/order-execution/ordersPoolService.js`
  - `fronted/src/legacy/features/orders-pool/page/OrdersPoolOrdersTable.jsx`
  - `fronted/src/legacy/features/orders-pool/page/OrdersPoolOrderDetailPanel.jsx`
  - `fronted/src/legacy/features/orders-pool/page/OrdersPoolToolbar.jsx`
  - `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
  - `fronted/src/legacy/features/schedule-calendar/components/ScheduleCalendarSettingsPanel.jsx`
- Dependencies:
  - `schedule_versions`
  - 订单池接口返回的版本与资源上下文字段
- Deliverables:
  - 统一的版本上下文映射与页面展示
  - 资源口径说明与渲染保持“候选 / 已落定”分离

### P3: 对齐订单池排序与真实排程顺位

- Objective: 让订单池展示顺序优先反映排程算法实际尊重的人工决策，避免页面优先级与生成排程顺序相互打架。
- Owned paths:
  - `backend/app/services/app_service.py`
  - `fronted/src/legacy/features/orders-pool/selectors.js`
  - `fronted/src/legacy/features/orders-pool/page/useOrdersPoolPageController.js`
  - `fronted/tests/e2e/*`（仅限与本任务直接相关的新/改用例）
- Dependencies:
  - 排程候选排序逻辑
  - 当前查看版排程事实
  - 订单池筛选与排序逻辑
- Deliverables:
  - 订单池排序键与排程逻辑对齐
  - 至少一条验证“人工决策进入顺序逻辑”的测试证据

## Phase Acceptance Criteria

### P1

- P1-AC1: 当 `use_order_state_window=true` 且订单存在手工 `expected_start_date`/`expected_start_shift` 时，排程生成的首个任务必须从该日期和班次开始，夜班不能退回白班。
- P1-AC2: 当手工开工时间已经晚于承诺交期，或在承诺交期当天选择夜班导致晚于交期时，系统必须保留原承诺交期并将订单标记为“必然延期”。
- P1-AC3: 保存手工开工后返回的影响信息必须能明确表达是否影响当前正式执行版、是否与当前查看版/正式版产生冲突、是否导致延期、是否需要立即重排。
- Evidence expectation: 后端单元/集成测试通过，并在执行记录中注明覆盖的字段与判断逻辑。

### P2

- P2-AC1: 订单池列表、订单详情和顶部版本摘要必须同时区分当前查看版、正式执行版和草稿版，不得复用同一标签冒充不同口径。
- P2-AC2: 排产日历页必须使用与订单池一致的版本术语，用户能在同页同时看清当前查看版本与正式执行版本，不需要自行推断。
- P2-AC3: 订单详情中的资源区域必须把候选资源与已落定资源分开展示，并明确说明“可排到”不等于“已经排到”。
- Evidence expectation: UI 渲染或 Playwright 证据能证明页面同时呈现正确版本摘要与资源口径。

### P3

- P3-AC1: 订单池排序必须优先体现冻结、锁单、优先级和手工开工窗口这些人工决策，不再仅按风险聚合结果排序。
- P3-AC2: 对于已进入当前查看版排程的订单，订单池中的相对顺位必须与当前查看版中的实际开工顺序保持一致或可由同一排序依据解释。
- P3-AC3: 对于尚未进入当前查看版排程的订单，订单池中的相对顺位必须沿用排程算法会采用的核心人工约束，而不是与排程算法无关的展示排序。
- Evidence expectation: 选择器/页面测试或浏览器证据能证明调整优先级、锁单、冻结、手工开工窗口后，列表顺位与排程逻辑一致变化。

## Done Definition

- P1-P3 全部完成并被记录为 `completed`。
- 后端回归测试证明夜班硬约束、必然延期暴露和版本字段分离成立。
- 前端验证证明订单池和排产日历页面版本口径一致，资源口径不混淆，手工开工影响提示真实可见。
- 订单池排序不再与排程算法的核心人工决策相冲突。
- `execution-log.md` 与 `test-report.md` 中都能找到每个 acceptance id 的证据引用。

## Blocking Conditions

- 找不到可运行的后端测试环境或测试数据库初始化失败。
- 前端依赖或 Playwright 运行环境缺失，导致本次 UI 验证无法按真实浏览器执行。
- 当前工作区中已有未提交改动与本次目标文件发生直接冲突，无法在不覆盖用户修改的前提下安全继续。
- 任何需要依赖的版本、资源或订单状态字段缺失且无法从现有仓库真实推导时，必须停止并报告缺失前提，而不是回退到推测值。
