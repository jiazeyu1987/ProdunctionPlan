# PRD

- Task ID: `task-9a33f950da-20260417T225748`
- Created: `2026-04-17T22:57:48`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `将现有排程重排逻辑扫描结果整理成一份从上到下的开发计划，先定方案，不零碎改点。`

## Goal

为当前生产排程系统输出一份可执行的开发计划，明确如何从现有“参考旧排程结果继续重排”的模型，演进到“基于业务事实从当天重排未来”的模型，并把实施顺序、约束边界、测试策略和停止条件写清楚。

该计划必须满足以下目标：

- 先解决概念和数据职责混杂的问题，再进入算法改造。
- 保留现有 legacy 重排链路，避免在未完成语义迁移前直接推翻现网逻辑。
- 对“事实”“人工约束”“排程结果”三类来源做清晰边界划分。
- 对锁定和冻结在新模式下的含义给出显式定义，不允许靠隐式 fallback 或模糊解释兜底。

## Scope

- 现状扫描结果整理与结构化落盘：
  - `backend/app/services/app_service.py`
  - `backend/app/services/final_process_metrics.py`
  - `backend/app/api/routes/commands.py`
  - `backend/app/services/job_dispatcher.py`
  - `fronted/src/legacy/features/schedule-calendar/*`
  - `fronted/src/legacy/features/orders-pool/*`
- 未来实施阶段的分解，包括：
  - 模型拆分
  - 接口与页面入口拆分
  - 调度器输入构造重构
  - 锁定和冻结语义重定义
  - 测试与上线策略
- 为后续执行提供稳定 phase ids、acceptance ids 和验证命令。

## Non-Goals

- 本任务不直接修改排程算法、不落数据库迁移、不新增接口行为。
- 本任务不直接修复“基准版本缺少锁定/冻结订单”报错本身。
- 本任务不把现有排程页面、订单池页面或报工链路顺手重构为新架构。
- 本任务不引入 fallback、兼容分支、默认成功占位值或 silent downgrade。
- 本任务不在未确定业务语义前直接把锁定/冻结降级成普通优先级。

## Preconditions

- 仓库可读，且以下关键代码存在并可扫描：
  - `generate_schedule`
  - `save_current_schedule_version`
  - `load_saved_schedule_version`
  - `list_order_pool`
  - `create_reporting`
- `doc/tasks` 任务工件工作流可用，允许保存 PRD、测试计划和状态文件。
- 本地具备后续执行阶段所需的基础运行环境：
  - Python 可运行 `pytest`
  - `fronted` 目录下 Node 依赖可运行 `eslint` 与 `playwright`
- 若后续执行阶段发现以下前置条件缺失，必须 fail fast：
  - 无法区分人工窗口与系统回写排程窗口
  - 无法为锁定/冻结在新模式下提供明确业务定义
  - 无法获得真实浏览器验证环境

## Impacted Areas

- 排程入口语义：
  - 当前“初始排产”走 `base_version_no = null`
  - 当前“计划能力重排/实际报工重排”强制走 `base_version_no = selectedVersionNo`
- 调度器核心：
  - `generate_schedule` 中基于 `base_version_no` 的 fixed order 复制逻辑
  - `_build_base_schedule_hints`
  - `_sort_schedule_candidates`
  - `_select_next_candidate_index`
- 订单状态与事实：
  - `order_pool_state.expected_start_date`
  - `order_pool_state.expected_start_time`
  - `order_pool_state.completed_qty`
  - `order_pool_state.remaining_qty`
  - `work_reports`
  - `simulation_state`
  - `daily_line_capacity_plan`
  - `daily_line_capacity_actual`
- 页面口径：
  - 当前排产 / 存档 / 当前查看版摘要
  - 人工排程窗口 vs 排程事实
  - 订单池排序提示与详情说明
- 测试：
  - `backend/tests/test_app_service_schedule_trust.py`
  - `backend/tests/test_app_service_multi_line_schedule.py`
  - `backend/tests/test_app_service_generate_schedule_unlocked_only.py`
  - `backend/tests/test_shift_capacity_schedule.py`
  - `fronted/tests/e2e/orders-pool-trust.e2e.spec.ts`
  - `fronted/tests/e2e/production-plan.e2e.spec.ts`

## Phase Plan

### P1: 统一术语与边界模型

- Objective: 把“事实”“人工约束”“排程结果”三类来源从概念上拆开，形成后续改造的统一术语和边界。
- Owned paths:
  - `backend/app/services/app_service.py`
  - `backend/app/services/final_process_metrics.py`
  - `fronted/src/legacy/features/schedule-calendar/*`
  - `fronted/src/legacy/features/orders-pool/*`
  - `doc/tasks/task-9a33f950da-20260417T225748/*`
- Dependencies:
  - 当前 `CURRENT/SAVED` 与旧 `PUBLISHED/DRAFT` 口径并存的现实
  - 当前订单池和排程页面对“参考排程/当前排产/存档”的展示差异
- Deliverables:
  - 一套统一术语表
  - 一份现状模型图，明确哪些字段属于事实、约束、结果
  - 一份旧口径到新口径的映射说明

#### P1 术语定义

| 类别 | 定义 | 当前代表表/字段 | 约束 |
| --- | --- | --- | --- |
| 事实（Facts） | 已经发生、已确定或可直接观测的业务输入，用于描述“今天系统知道什么”。事实只能来自业务事件、主数据、仿真日期和产能数据，不能由排程结果回写伪装。 | `work_reports`、`simulation_state.current_date`、`order_pool_state.completed_qty`、`order_pool_state.remaining_qty`、`daily_line_capacity_plan`、`daily_line_capacity_actual`、工艺/拓扑主数据 | 事实缺失时必须阻断后续依赖该事实的设计，不允许拿旧排程结果顶替 |
| 人工约束（Manual Constraints） | 用户显式录入、希望调度器尊重的未来约束，用于描述“人想怎么排”。这类数据不等于系统已排出的结果。 | `order_pool_state.expected_start_date`、`order_pool_state.expected_start_time`、`order_pool_state.expected_finish_time`、`lock_flag`、`frozen_flag`、前端人工排程窗口表单输入 | 约束只能表达用户意图，不得被排程任务回写污染 |
| 排程结果（Schedule Results） | 调度器根据事实和约束计算出的排程输出，用于描述“系统算出了什么”。结果应落在 `schedule_tasks`、排程版本、任务列表或显式导出字段中。 | `schedule_tasks.*`、排程版本摘要、排程页甘特任务块、`save_current_schedule_version` 产物 | 结果只能作为展示、存档和后续 legacy 重排输入，不能反写为人工约束定义 |

#### P1 现状字段映射与问题归类

| 当前对象 | 当前主要用途 | 应归属类别 | 当前问题 | 后续要求 |
| --- | --- | --- | --- | --- |
| `order_pool_state.completed_qty` | 表示订单已报工数量 | 事实 | 无明显口径混用 | 保持为事实来源 |
| `order_pool_state.remaining_qty` | 表示订单剩余待生产量 | 事实 | 依赖报工与订单数量一致性 | 作为事实重排核心输入 |
| `work_reports` | 已发生报工 | 事实 | 若只能提供末道报工，则不足以支撑工序级事实重排 | 缺失即登记前置缺口并阻断 |
| `simulation_state.current_date` | 模拟系统当前日 | 事实 | 可能只在部分入口显式消费 | 新管线必须显式消费 |
| `daily_line_capacity_plan` / `daily_line_capacity_actual` | 计划/实际产能 | 事实 | 当前在入口语义上没有被完整解释 | 进入 P3 时纳入统一输入构造 |
| `order_pool_state.expected_start_date` / `expected_start_time` / `expected_finish_time` | 当前既被当成手工窗口，又可能被系统排程结果同步覆盖 | 人工约束 | 同一字段同时承担约束与结果展示，属于必须拆分的污染点 | P2 必须拆出独立结果字段或改为只读结果来源 |
| `lock_flag` / `frozen_flag` | 表示用户希望保持某订单不被随意改动 | 人工约束 | 现阶段语义依赖旧排程锚点，不足以直接推导新模式行为 | P4 必须重定义 |
| `schedule_tasks` | 存放排程任务、工序排序和时间窗 | 排程结果 | 当前又被 legacy 重排拿来复制为固定订单来源 | 保留为结果层，但拆分 legacy 与事实重排的输入构造 |
| 当前排程页“当前排产/存档/当前查看版”摘要 | 展示结果版本 | 排程结果 | 页面口径和后端状态字段命名并不完全对齐 | P1 先统一术语，P5 再做默认入口切换 |

结论：

- `order_pool_state.expected_start_* / expected_finish_time` 是当前最明显的“一字段多角色”问题，已经被明确标记为 P2 的首要收口对象。
- `schedule_tasks` 属于排程结果，不属于事实，也不应继续伪装成人工约束。
- `lock_flag` / `frozen_flag` 属于人工约束，但它们能否生效取决于是否存在明确锚点，这个依赖要在 P4 显式定义，而不是在 P1 偷偷兜底。

#### P1 入口真实差异

当前系统至少存在三种入口语义，不能再统称为“重排”：

| 入口 | 当前实现特征 | 输入来源 | 风险 |
| --- | --- | --- | --- |
| 初始排产 | `base_version_no = null` | 直接从订单池、产能和约束构造输入，不依赖既有排程版本 | 名称上容易被误认为只是“第一次重排” |
| legacy 重排（计划能力重排/实际报工重排） | `base_version_no = selectedVersionNo` | 先读取选定版本，再把旧 `schedule_tasks` 复制/转换为 fixed order 或锚点后继续排 | 入口语义本质上依赖旧结果，无法代表“按事实从当天重排未来” |
| 目标新入口：按事实从当天重排 | 不允许依赖 `base_version_no` | 从仿真当前日、报工、剩余量、产能、工艺与拓扑直接构造未来输入 | 当前尚未落地，需要在 P3 新增 |

必须明确的行为分叉：

- `base_version_no = null` 代表“没有已选基准版本参与输入构造”，不是“selectedVersionNo 恰好为空时继续走老逻辑”。
- `base_version_no = selectedVersionNo` 代表“把旧排程版本当作本次排程输入的一部分”，因此天然会继承 legacy 锚点、fixed order 和基准版本缺失类报错。
- 所以后续不能用补丁把 legacy 重排强行解释成事实重排；必须单独新增入口并拆分输入构造器。

#### P1 口径漂移清单

| 漂移点 | 当前表现 | 风险 | P1 收口要求 |
| --- | --- | --- | --- |
| `CURRENT/SAVED` 与旧 `PUBLISHED/DRAFT` 混用 | 后端、页面文案和操作者认知中并存两套说法 | 用户无法判断“当前排产”和“当前查看版”是否同一概念 | 从本计划开始统一使用 `CURRENT/SAVED` 描述版本态，旧术语只作为迁移映射保留 |
| “当前排产” vs “存档” vs “当前查看版” | 页面摘要、接口返回和存档动作表达不完全一致 | 容易把浏览态误读为结果态，把存档态误读为运行态 | 后续接口和页面文案必须分别说明“正在查看哪个版本”和“系统当前采用哪个版本” |
| 订单池人工窗口 vs 系统排程窗口 | 订单池详情里可能显示 `expected_start_*`，但这些字段已被系统结果污染 | 用户误以为看到的是手工约束，实际却是上轮结果残留 | P2 将人工窗口与系统结果彻底拆开 |
| 后端状态 vs 页面术语 | 后端围绕版本号和任务表运作，前端则混用“参考排程”“当前排产”“已存档” | 入口语义难以测试，异常信息也难解释 | P3/P5 分别在接口命名和页面文案上完成统一 |

#### P1 旧术语到新术语映射

| 旧说法 | 计划内统一说法 | 说明 |
| --- | --- | --- |
| `PUBLISHED` | `CURRENT` | 指当前被系统采用/发布的排程版本 |
| `DRAFT` | `SAVED` | 指已保存但未成为当前采用版本的排程版本 |
| 参考排程重排 | legacy 重排 | 强调其输入依赖旧版本 |
| 从当天重排 | 按事实从当天重排 | 强调其输入依赖事实而非旧版本 |

### P2: 拆分数据职责并停止结果污染约束字段

- Objective: 先从数据职责上切断“排程结果回写到人工约束字段”的耦合，为事实重排创造干净输入。
- Owned paths:
  - `backend/app/services/app_service.py`
  - `backend/app/db.py`
  - `backend/sqlite/001_init.sql`
  - `fronted/src/legacy/features/orders-pool/*`
  - `doc/07_SQLite表设计草案.md`
- Dependencies:
  - `order_pool_state.expected_start_date/expected_start_time/expected_finish_time`
  - `schedule_tasks`
  - `_sync_order_pool_state_schedule_window_from_tasks`
- Deliverables:
  - 字段职责拆分方案
  - 数据迁移方案
  - 兼容期读写策略

#### P2 字段职责拆分方案

P2 的核心目标不是“再给旧字段多加几个含义”，而是彻底拆开“人工想怎么排”和“系统实际算出了什么”。

| 职责集合 | 推荐承载位置 | 字段/对象 | 读写规则 |
| --- | --- | --- | --- |
| 人工排程窗口字段 | `order_pool_state` | `expected_start_date`、`expected_start_time`、`expected_finish_time` | 只允许人工录入、人工编辑、人工清空；调度器与同步函数不得再覆盖 |
| 排程结果导出字段 | 新增只读结果视图字段或结果表投影 | 推荐新增 `scheduled_start_date`、`scheduled_start_time`、`scheduled_finish_time`，或由 `schedule_tasks` 聚合导出同名只读字段 | 只允许由排程结果生成；前端以“系统排程结果”标签展示，不可当成用户约束写回 |
| 排程任务明细 | `schedule_tasks` | 工序任务开始/结束时间、线体、顺序、版本号 | 继续作为结果明细真源，不承担人工窗口语义 |

必须明确收口的耦合点：

- `_sync_order_pool_state_schedule_window_from_tasks` 当前把 `schedule_tasks` 的结果时间窗同步回 `order_pool_state.expected_start_* / expected_finish_time`，这是 P2 首要收口对象。
- P2 完成后，该函数不能继续承担“把结果伪装成约束”的职责；要么删除，要么收缩为“写入新的结果导出字段/物化视图”，绝不能继续回写人工字段。
- 在进入 P3 前，任何新逻辑都不得再依赖“`expected_start_*` 里顺便混有上一轮排程结果”这个隐式前提。

#### P2 数据库与服务层改造顺序

必须按下面顺序推进，不能直接在旧字段上堆条件分支：

1. 数据层先拆职责
   - 在 `backend/sqlite/001_init.sql` 和 `backend/app/db.py` 中为“系统排程结果时间窗”定义独立承载方式。
   - 如果采用新增字段，则这些字段只服务于结果展示；如果采用结果视图/聚合查询，则需要在数据访问层提供统一读取接口。
2. 服务层收口写路径
   - 修改 `backend/app/services/app_service.py` 中所有将 `schedule_tasks` 回写到 `order_pool_state.expected_*` 的逻辑。
   - `_sync_order_pool_state_schedule_window_from_tasks` 不再更新人工字段，只能更新结果层承载或直接停用。
3. 查询层拆开读模型
   - `list_order_pool` 及相关选择器需要同时区分“人工窗口”和“系统排程窗口”两个来源。
   - 前端拿到的数据结构必须能显式区分 `manualWindow` 与 `scheduledWindow`，不能靠字段是否为空猜测。
4. 算法入口最后调整
   - 在 P2 完成前，不修改 `generate_schedule` 入口语义，只先清理输入污染。
   - P3 才允许在干净职责边界上新增事实重排入口。

执行原则：

- 先完成 schema / 读写职责拆分，再进入入口与算法层改造。
- 禁止在 `expected_start_*` 上新增 `if legacy else fact_mode` 一类分支来同时兼容两种职责。
- 禁止使用后台静默复制旧值的方式维持“看起来没变”；如果结果字段缺失，就应明确暴露为结果缺失，而不是回退写入人工字段。

#### P2 迁移边界

| 层级 | 当前问题 | P2 迁移动作 | 完成判据 |
| --- | --- | --- | --- |
| SQLite schema | 人工窗口与系统结果共用同一组字段 | 为系统结果增加独立承载 | 库结构或查询模型可以同时表达两组窗口 |
| Service | 同步函数把结果回写成约束 | 移除或改写 `_sync_order_pool_state_schedule_window_from_tasks` | 服务层不再覆盖人工字段 |
| API | 订单池接口未显式区分两类窗口 | 返回结构拆成人工窗口与系统窗口两个命名域 | 接口文档与响应示例可区分两个来源 |
| Frontend | 订单池详情/排序提示默认把一个字段解释成两种含义 | 页面文案和展示位拆分，分别标识“人工约束”与“系统排程结果” | 用户无法再把系统结果误读为人工约束 |

#### P2 兼容期策略

P2 可以有迁移期，但不能有语义 fallback。兼容只允许体现在“旧页面还能读到正确语义”，不允许体现在“旧字段继续混合承载”。

| 对象 | 兼容期策略 | 双读/双写规则 | 终止条件 |
| --- | --- | --- | --- |
| legacy 页面 | 可以继续展示原有位置，但必须改文案，明确区分人工窗口和系统结果 | 可临时双读：优先读取新结果字段；若页面还未改完，可同时读取旧展示来源用于对照，但不能把结果反写回人工字段 | 页面完成拆分展示后停止双读 |
| legacy 接口 | 对外响应可短期保留旧字段名，但内部必须改为从新职责源组装 | 可临时双写仅限“结果层内部双写”，例如 `schedule_tasks` 与新结果字段同时写；禁止对人工字段双写 | 所有调用方切换到新响应结构后移除旧字段组装 |
| 新事实重排入口 | 不允许在 P2 兼容期内建立在旧混合字段上 | 不允许读取混合语义字段作为事实输入 | P3 启动前必须完成 |

兼容期硬规则：

- 允许“旧接口名 + 新语义实现”，不允许“旧字段继续承载旧语义和新语义两套解释”。
- 允许结果层临时双写，以支持页面逐步切换；不允许人工字段双写。
- 如果发现某个 legacy 页面只能通过读取被污染的 `expected_*` 才能工作，必须把它登记为迁移欠账，而不是继续保留污染逻辑。

#### P2 对后续阶段的约束

- `P3` 新入口只能消费事实与人工约束，不能再把 `expected_*` 当成系统结果缓存。
- `P4` 对 `lock_flag` / `frozen_flag` 的语义重定义，必须建立在 P2 已经分离“人工窗口”和“排程结果”的前提上。
- 若 P2 无法完成字段职责拆分，应把该问题写入 `blocking_prereqs`，并阻断后续“按事实从当天重排”实现阶段。

### P3: 新增“按事实从当天重排”管线

- Objective: 在不破坏 legacy 重排的前提下，新增一条不依赖 `base_version_no` 的事实驱动重排管线。
- Owned paths:
  - `backend/app/services/app_service.py`
  - `backend/app/api/routes/commands.py`
  - `backend/app/services/job_dispatcher.py`
  - `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
  - `fronted/src/legacy/features/schedule-calendar/components/ScheduleCalendarSettingsPanel.jsx`
- Dependencies:
  - `simulation_state.current_date`
  - `work_reports`
  - `order_pool_state.remaining_qty`
  - `daily_line_capacity_plan`
  - `daily_line_capacity_actual`
- Deliverables:
  - 新入口命名和交互方案
  - 新接口参数设计
  - 调度器输入构造器拆分设计
  - legacy 管线与新管线共用后半段分配器的重构方案

#### P3 新入口定义

P3 不是把 legacy 重排“改名”，而是新增一条与 legacy 管线并存的事实驱动入口。

| 入口类型 | 调用语义 | 是否依赖 `base_version_no` | 是否复制旧 `schedule_tasks` | 用途 |
| --- | --- | --- | --- | --- |
| 初始排产 | 从空白状态首次生成排程 | 否 | 否 | 保留现有首排语义 |
| legacy 重排 | 参考指定版本继续重排 | 是，必须传入 `selectedVersionNo` | 是，可继续使用旧任务作为 fixed order / 锚点输入 | 保留现网行为，服务已有计划能力重排/实际报工重排 |
| 按事实从当天重排 | 以“当前日 + 已发生事实 + 剩余待排量”重新计算未来 | 否，必须显式不传 | 否，禁止把旧任务表复制成固定订单 | 为未来默认模式做准备 |

新入口硬约束：

- “按事实从当天重排”必须显式声明为独立入口，不允许复用 legacy 重排的命令名后靠参数组合偷偷分流。
- 新入口执行时，`base_version_no` 必须为空且不参与输入构造；如果调用端仍传入版本号，应直接报错或拒绝进入事实模式，而不是忽略后继续跑。
- 新入口不能把旧 `schedule_tasks` 复制成固定订单，也不能把上一版排程时间窗回填为事实输入。

#### P3 新管线直接消费的事实来源

新管线输入必须直接来自事实层与人工约束层，至少包含下表：

| 输入类别 | 事实来源 | 在新管线中的作用 | 缺失时处理 |
| --- | --- | --- | --- |
| 当前日 | `simulation_state.current_date` | 定义“从哪一天开始重排未来” | 缺失则阻断，不允许拿版本日期兜底 |
| 已发生报工 | `work_reports` | 判断哪些工序/订单已发生、哪些只剩未来任务 | 若只能提供末道报工且业务要求工序级事实，则登记前置缺口并阻断 |
| 剩余量 | `order_pool_state.remaining_qty` | 决定未来仍需排产的数量 | 缺失则阻断，不允许从旧任务反推 |
| 已完成量 | `order_pool_state.completed_qty` | 与剩余量共同校验订单当前状态 | 与剩余量不一致时应暴露数据问题 |
| 计划产能 | `daily_line_capacity_plan` | 提供未来日期/产线计划能力 | 缺失则阻断未来产能计算 |
| 实际产能 | `daily_line_capacity_actual` | 修正当天及历史实际占用/可用能力 | 缺失则阻断依赖实际能力的计算 |
| 工艺路线 | 工艺主数据 | 决定工序顺序、可过站关系 | 缺失则阻断 |
| 产线/拓扑 | 线体拓扑主数据 | 决定订单可去哪些资源、资源切换关系 | 缺失则阻断 |
| 人工约束 | `expected_start_*`、`lock_flag`、`frozen_flag` | 仅作为约束输入，不作为事实输入 | 若语义未在 P4 明确，不得默认降级解释 |

结论：

- 新管线的“未来待排集合”来自“事实 + 剩余量 + 约束”，不是来自旧任务表拷贝。
- 新管线的“起点”来自 `simulation_state.current_date` 与已发生报工，不来自选中的排程版本。
- 如果事实源不足以支持产品要求的粒度，必须 fail fast 进入 `blocking_prereqs`，而不是退回 legacy 逻辑冒充完成。

#### P3 输入构造器拆分设计

P3 只在输入构造层把新旧两条管线分开，后半段分配核心尽量复用。

| 层级 | legacy 重排 | 按事实从当天重排 | 共享策略 |
| --- | --- | --- | --- |
| API 命令层 | 接收 `selectedVersionNo` 并声明“参考旧排程重排” | 接收事实模式标识，不接收 `selectedVersionNo` | 命令层分流 |
| Job Dispatcher | 为 job payload 注入 `base_version_no`、版本来源、legacy 模式标记 | 为 job payload 注入 `current_date`、事实快照来源、fact 模式标记 | dispatcher 分流 |
| 输入构造器 | 从排程版本 + `schedule_tasks` 构造 fixed order / anchors | 从事实源 + 人工约束构造未来待排集合 | 仅此层分开 |
| 分配核心 | 候选排序、资源分配、工序推进 | 候选排序、资源分配、工序推进 | 尽量共用 `_sort_schedule_candidates`、`_select_next_candidate_index` 等后半段逻辑 |
| 输出层 | 统一写入 `schedule_tasks` / 版本结果 | 统一写入 `schedule_tasks` / 版本结果 | 统一输出格式 |

推荐代码落点：

- `backend/app/api/routes/commands.py`
  - 新增显式事实重排命令名或模式字段，避免与 legacy 重排共用一套语义不清的参数。
- `backend/app/services/job_dispatcher.py`
  - 负责把“legacy 模式”与“fact 模式”翻译成不同 job payload。
- `backend/app/services/app_service.py`
  - 新增独立输入构造函数，例如“从版本构造输入”和“从事实构造输入”两套 builder。
  - `generate_schedule` 后半段分配核心尽量复用，不再让入口差异散落在分配逻辑内部。
- `fronted/src/legacy/features/schedule-calendar/useScheduleCalendarController.js`
  - 显式区分“参考旧排程重排”与“按事实从当天重排”两种提交路径。
- `fronted/src/legacy/features/schedule-calendar/components/ScheduleCalendarSettingsPanel.jsx`
  - 在 UI 中给出明确模式选择、参数解释和阻断文案入口。

#### P3 新旧两条管线的共存边界

必须保持双管线并存，而不是“做出新入口后顺便废掉旧入口”。

| 维度 | legacy 重排 | 按事实从当天重排 |
| --- | --- | --- |
| 触发入口 | 继续保留现有计划能力重排 / 实际报工重排 | 新增独立入口 |
| 输入锚点 | 选中版本、旧任务表、existing anchors | 当前日、报工、剩余量、产能、工艺、拓扑 |
| 是否允许引用旧任务 | 允许 | 不允许 |
| 输出结果 | 新排程版本与 `schedule_tasks` | 新排程版本与 `schedule_tasks` |
| 风险防线 | 保证现有用户流程不被破坏 | 保证新模式不会被旧版本依赖污染 |

共存规则：

- 两条管线只允许在“输入构造层”分开；从候选排序、资源分配到结果写出，优先复用同一套后半段核心。
- 不允许为了快速落地新模式，复制一整套完整调度器分支；那会让后续规则切换和测试矩阵失控。
- 也不允许为了省事，把 fact 模式偷偷接到 legacy builder 上，只是少传一个参数；这样会重新引入 `base_version_no` 隐性依赖。

#### P3 与测试计划的绑定

P3 的设计必须能直接映射到测试计划中的入口分流与双管线验证：

- `T1` 负责验证“初始排产 / legacy 重排 / 按事实从当天重排”三种入口边界。
- `T4` 负责验证 fact 模式不复制旧任务表，而是直接消费事实输入。
- `T5` 负责验证 legacy 管线继续可用，且不会被新模式破坏。
- `T8` 负责验证前端真实浏览器中可显式选择事实重排入口，并看到对应参数与阻断行为。

### P4: 重定义锁定与冻结在新模式下的语义

- Objective: 为新模式定义锁定与冻结的精确行为，明确哪些是硬事实、哪些是未来约束、哪些条件下必须阻断。
- Owned paths:
  - `backend/app/services/app_service.py`
  - `backend/tests/test_app_service_multi_line_schedule.py`
  - `backend/tests/test_app_service_generate_schedule_unlocked_only.py`
  - `fronted/src/legacy/utils/i18n.js`
  - `fronted/src/legacy/features/schedule-calendar/*`
- Dependencies:
  - `lock_flag`
  - `frozen_flag`
  - 是否存在旧排程任务锚点
  - 是否存在已发生任务事实
- Deliverables:
  - 规则矩阵
  - 阻断条件清单
  - 错误文案与用户解释策略
  - 冲突测试清理方案

#### P4 规则矩阵

P4 的目标不是把 `lock_flag` / `frozen_flag` 继续模糊解释成“别动它”，而是明确它们在事实重排模式中到底约束什么。

定义：

- 锁定（`lock_flag`）
  - 表示该订单在新模式下需要保留一个“可验证的排程锚点”。
  - 这个锚点必须来自显式结果事实，例如现存 `schedule_tasks` 锚点、已发布排程中的明确任务位置，或系统定义的可追溯结果记录。
  - 锁定约束的是“相对排程位置/资源承诺不可被重新分配”，不是简单优先级提升。
- 冻结（`frozen_flag`）
  - 表示该订单在新模式下不允许再被系统重算未来安排。
  - 冻结需要有明确冻结对象，要么是已发生事实已经覆盖的部分，要么是有明确锚点的未来任务段。
  - 冻结约束的是“不可修改的未来承诺区间”，不是“看到这个标志就保留旧结果”。

规则矩阵：

| 场景 | 是否存在旧排程锚点 | 是否存在已发生任务事实 | `lock_flag` 处理 | `frozen_flag` 处理 | 结果 |
| --- | --- | --- | --- | --- | --- |
| legacy 重排，且选中版本完整 | 是 | 可有可无 | 允许沿用旧锚点解释为“保持该订单锚定位置” | 允许沿用旧锚点解释为“冻结该未来承诺段” | 非阻断 |
| fact 模式，存在明确结果锚点 | 是 | 可有可无 | 可生效，保持该锚点对应的排位/资源承诺 | 可生效，冻结锚点对应未来任务段 | 非阻断 |
| fact 模式，无旧锚点，但存在已发生事实 | 否 | 是 | 不能自动推导为“保持旧排位”；只能约束不改变已发生事实之前后的可验证边界 | 只能冻结已被事实覆盖或明确映射的未来承诺部分；超出边界则阻断 | 条件阻断 |
| fact 模式，无旧锚点、无已发生事实 | 否 | 否 | 不能解释为“保持旧排位” | 不能解释为“冻结未来安排” | 阻断 |
| fact 模式，锚点与事实冲突 | 是/否 | 是 | 不允许静默选一边 | 不允许静默选一边 | 阻断 |

核心结论：

- 在 fact 模式下，`lock_flag` / `frozen_flag` 不再默认等价于“沿用旧排位”。
- 只有当系统拥有明确锚点信息时，锁定/冻结才可以落成具体约束。
- 缺失锚点时，系统必须告诉用户“缺的是什么业务前提”，而不是沿用“未出现在基准版本中”这种 legacy 报错语义。

#### P4 阻断条件清单

以下情况在新模式下必须阻断：

| 阻断条件 | 原因 | 是否允许继续排 | 说明 |
| --- | --- | --- | --- |
| `lock_flag = true` 但系统没有可验证锚点 | 锁定无法映射到具体排位/资源承诺 | 否 | 不能退化成“尽量别动” |
| `frozen_flag = true` 但系统没有明确冻结区间 | 冻结对象不存在 | 否 | 不能退化成“照抄旧结果” |
| 已发生事实与锚点冲突 | 事实与承诺来源不一致 | 否 | 需要用户或业务先修正数据 |
| 仅有末道报工，但要求工序级锁定/冻结 | 事实粒度不足 | 否 | 属于前置条件缺失 |
| 人工约束字段仍与系统结果字段混用 | 无法判断约束来自用户还是旧结果 | 否 | 违反 P2 前提，必须先停 |

以下情况可非阻断继续：

| 非阻断条件 | 允许原因 | 处理方式 |
| --- | --- | --- |
| fact 模式下无锁定/冻结标记 | 无需解释锚点 | 按事实与人工窗口正常重排 |
| fact 模式下存在明确锚点，且与事实不冲突 | 约束有可追溯来源 | 应用锁定/冻结规则后继续排 |
| 仅冻结已被事实覆盖的已发生区间 | 事实本身已构成硬边界 | 作为硬事实边界处理 |

阻断原则：

- 阻断原因必须来自“缺少锚点”“缺少事实”“事实冲突”“职责未拆分”等明确业务前提。
- 不允许再返回“订单未出现在基准版本中，因此不能锁定/冻结”作为新模式默认解释。
- 不允许在阻断时静默切回 legacy 模式继续计算。

#### P4 错误文案与用户解释策略

错误文案要帮助用户理解缺失前提，而不是暴露旧实现细节。

推荐文案方向：

| 场景 | 文案原则 | 示例表达 |
| --- | --- | --- |
| 锁定缺少锚点 | 说明缺少可验证排程锚点 | “该订单已标记为锁定，但当前事实重排模式下找不到可追溯的排程锚点，请先选择参考版本重排或补充明确锚点后再试。” |
| 冻结缺少冻结区间 | 说明缺少未来承诺对象 | “该订单已标记为冻结，但系统无法确定要冻结的未来任务区间，请先确认冻结来源。” |
| 锚点与事实冲突 | 说明哪个前提冲突 | “该订单的已报工事实与现有排程锚点冲突，系统无法安全重排，请先校正数据后再试。” |
| 事实粒度不足 | 说明缺的是哪类事实 | “当前仅有末道报工数据，无法支撑工序级锁定/冻结判断，请先补足所需事实。” |

前端与接口约束：

- `fronted/src/legacy/utils/i18n.js` 需要承载新模式专用错误语义，不再复用 legacy 的“基准版本缺失”文案。
- `fronted/src/legacy/features/schedule-calendar/*` 需要在 UI 中把阻断原因展示为“缺少哪项前提”和“下一步该做什么”。
- 接口响应中应返回结构化阻断原因码，避免前端只能根据自由文本猜测。

#### P4 冲突测试清理方案

现有围绕 legacy 语义建立的冲突测试，需要按新规则矩阵清理或重写，而不是临时改断言让测试变绿。

| 测试类别 | 旧测试问题 | 新测试要求 | 目标文件 |
| --- | --- | --- | --- |
| multi-line schedule 冲突测试 | 旧测试可能默认“未在基准版本中”即为锁定/冻结失败原因 | 改为验证“缺少锚点”“事实冲突”“粒度不足”等新阻断原因 | `backend/tests/test_app_service_multi_line_schedule.py` |
| unlocked only / fixed 相关测试 | 旧测试可能把锁定/冻结等价成“保留旧排位” | 改为验证 fact 模式下只有存在明确锚点时才允许锁定/冻结 | `backend/tests/test_app_service_generate_schedule_unlocked_only.py` |
| fact constraints 新测试 | 旧矩阵未覆盖 fact 模式阻断/非阻断分支 | 增加 `test_schedule_fact_constraints.py -k fixed` 覆盖新规则矩阵 | `backend/tests/test_schedule_fact_constraints.py` |

测试清理原则：

- 删除或重写的依据只能来自本节规则矩阵，不来自“当前实现先这样过”。
- legacy 模式测试继续保留 legacy 语义，fact 模式测试必须独立断言新语义。
- `T6` 必须成为 P4 的主验证入口，验证阻断与非阻断分支都与新规则矩阵一致。

### P5: 回归验证、迁移策略与上线切换

- Objective: 让新模式具备真实可验证性，并给出从 legacy 模式迁移到双模式共存、再到默认模式切换的上线步骤。
- Owned paths:
  - `backend/tests/*`
  - `fronted/tests/e2e/*`
  - `doc/04_接口契约与命令行为.md`
  - `doc/08_前后端API协议.md`
  - `doc/tasks/task-9a33f950da-20260417T225748/*`
- Dependencies:
  - 后端集成测试
  - 真实浏览器 E2E
  - 操作文档与错误说明
- Deliverables:
  - 回归矩阵
  - 上线开关与切换顺序
  - 回滚策略
  - 发布前检查清单

#### P5 验证命令与 success signal

P5 的验证必须严格落在三类命令上，不能只靠“文档看起来合理”判定完成。

| 验证类型 | 命令 | success signal | 失败解释 |
| --- | --- | --- | --- |
| 后端窄回归 | `python -m pytest backend/tests/test_app_service_schedule_trust.py backend/tests/test_app_service_multi_line_schedule.py backend/tests/test_shift_capacity_schedule.py` | 退出码 `0`，现有可信排程、固定订单、班次产能回归仍通过 | 若失败，说明新方案破坏了既有可信排程语义或约束假设 |
| 后端事实重排测试 | `python -m pytest backend/tests/test_schedule_fact_replan.py backend/tests/test_schedule_fact_constraints.py` | 退出码 `0`，能区分 legacy 与 fact 模式，且锁定/冻结符合新规则矩阵 | 若失败，说明新入口、字段职责或新规则矩阵与实现不一致 |
| 前端静态检查 | `npx eslint --no-ignore src/legacy/features/schedule-calendar/useScheduleCalendarController.js src/legacy/features/schedule-calendar/components/ScheduleCalendarSettingsPanel.jsx src/legacy/features/orders-pool/page/useOrdersPoolPageController.js src/legacy/features/orders-pool/selectors.js src/legacy/features/order-execution/ordersPoolService.js` | 退出码 `0`，入口分流、文案口径、订单池字段职责相关代码无 lint 错误 | 若失败，说明接口分流或 UI 文案落地不稳定 |
| 真实浏览器 E2E | `npx playwright test tests/e2e/production-plan.e2e.spec.ts tests/e2e/orders-pool-trust.e2e.spec.ts` | 退出码 `0`，并产出截图、trace 或视频等真实浏览器证据 | 若失败，说明用户主链路、页面口径或阻断行为未达到可用状态 |

执行要求：

- 上述三类验证缺一不可，不能用单一后端测试替代真实浏览器验证。
- 只有当全部 phase 文档化开发项完成后，才允许执行这组完整测试。
- 测试失败时必须写入 `test-report.md` 和 `execution-log.md`，不能因为“只是文档任务”而跳过。

#### P5 迁移顺序

迁移必须按固定顺序推进，不能倒序：

1. 文档和术语统一
   - 先完成 `P1`，统一“事实 / 人工约束 / 排程结果”和 `CURRENT/SAVED` 口径。
2. 数据职责拆分
   - 再完成 `P2`，把人工窗口与系统排程结果彻底拆开。
3. 新管线落地
   - 完成 `P3`，新增“按事实从当天重排”入口，并保持 legacy 管线继续可用。
4. 规则切换
   - 完成 `P4`，让 `lock_flag` / `frozen_flag` 的解释从 legacy 语义切换到 fact 语义。
5. 默认入口切换
   - 在新模式验证通过后，才评估是否把“按事实从当天重排”提升为默认用户入口。

上线阶段建议：

| 阶段 | 用户可见行为 | 风险控制 |
| --- | --- | --- |
| 阶段 A：双模式共存 | legacy 重排保留，新 fact 入口显式可选 | 用真实浏览器验证用户能理解两种入口差异 |
| 阶段 B：新模式优先推荐 | UI 默认强调 fact 入口，但 legacy 仍可手动选择 | 持续观察阻断原因、错误文案和订单池口径是否稳定 |
| 阶段 C：默认入口切换 | fact 入口成为默认入口，legacy 降为回退方案 | 切换前必须完成完整测试计划并确认回滚链路可执行 |

#### P5 发布前检查清单

发布前必须逐项确认：

| 检查项 | 通过标准 |
| --- | --- |
| 文档一致性 | `prd.md`、`test-plan.md`、接口契约和前后端 API 协议对入口口径描述一致 |
| 字段职责 | 人工窗口与排程结果字段已分离，不再存在回写污染 |
| 入口分流 | legacy 与 fact 两条管线可被明确区分，且命令与 UI 命名一致 |
| 锁定/冻结语义 | 新模式阻断原因来自新规则矩阵，而非 legacy “基准版本缺失”语义 |
| 后端测试 | 两组 `pytest` 命令均通过 |
| 前端静态检查 | `eslint` 命令通过 |
| 真实浏览器验证 | `playwright` 命令通过，并保留证据文件 |
| 回滚链路 | legacy 入口仍可用，且回退步骤被明确文档化 |

任一项失败都不得视为可发布状态。

#### P5 回滚原则

回滚原则必须遵守“回退到 legacy 管线”，而不是引入 fallback 混跑。

| 触发条件 | 回滚动作 | 禁止事项 |
| --- | --- | --- |
| 新模式入口语义错误 | 将默认入口切回 legacy 重排 | 不允许保留 fact 入口半启用并静默切 legacy |
| 锁定/冻结阻断规则误伤 | 暂停 fact 模式默认暴露，恢复 legacy 入口为主 | 不允许临时把 `lock_flag` / `frozen_flag` 降级成普通优先级 |
| 订单池/排程页口径混乱 | 回退到已验证的旧入口 + 旧页面默认视图 | 不允许通过继续双写污染字段来“看起来恢复正常” |
| 真实浏览器主链路失败 | 取消默认切换，保留双模式或全量切回 legacy | 不允许跳过 E2E 证据直接上线 |

回滚策略要点：

- 回滚目标是“恢复 legacy 重排为主路径”，不是“让新旧模式在后台混跑并互相兜底”。
- 回滚时保留 P2 的字段职责拆分成果，不把结果再写回人工字段。
- 若需要重新启用新模式，必须重新通过完整测试计划，不能因之前某次通过过就跳过。

## Phase Acceptance Criteria

### P1

- P1-AC1: 计划文档必须明确给出“事实”“人工约束”“排程结果”三类来源的定义，并把当前系统中的关键表和字段映射到其中一类，不允许同一字段同时扮演多类角色而不被指出。
- P1-AC2: 计划文档必须明确指出当前“初始排产”和“重排”入口的真实差异，包括 `base_version_no = null` 与 `base_version_no = selectedVersionNo` 的行为分叉。
- P1-AC3: 计划文档必须明确列出当前口径漂移点，包括 `CURRENT/SAVED` 与旧 `PUBLISHED/DRAFT` 的混用，以及订单池、排程页、后端状态之间的差异。
- Evidence expectation: `prd.md` 中存在清晰的模型拆分与入口语义说明，且 `task-state.json` 已同步出对应 phase 和 acceptance ids。

### P2

- P2-AC1: 计划文档必须把“人工排程窗口字段”和“排程结果导出字段”拆成两个职责集合，并明确指出当前 `_sync_order_pool_state_schedule_window_from_tasks` 是需要收口的耦合点。
- P2-AC2: 计划文档必须给出数据库和服务层的改造顺序，先拆字段职责，再改算法入口，不允许直接在旧字段上堆条件分支。
- P2-AC3: 计划文档必须定义兼容期策略，说明 legacy 页面和 legacy 接口在迁移中如何继续工作，以及哪些字段需要临时双读或双写。
- Evidence expectation: `prd.md` 的 P2 节包含字段职责拆分、迁移边界和兼容策略，不留“后续再看”的关键空白。

### P3

- P3-AC1: 计划文档必须定义一条新的“按事实从当天重排”管线，明确该管线不依赖 `base_version_no`，也不复制旧任务表作为固定订单。
- P3-AC2: 计划文档必须列出新管线直接消费的事实来源，至少覆盖模拟当前日、报工、剩余量、计划/实际产能、工艺和拓扑。
- P3-AC3: 计划文档必须明确 legacy 重排管线继续保留，并说明两条管线只在输入构造层分开，后半段分配核心尽量复用。
- Evidence expectation: `prd.md` 的 P3 节给出新旧两条管线的边界和文件级落点，测试计划至少有一个 case 专门验证入口分流。

### P4

- P4-AC1: 计划文档必须明确锁定与冻结在新模式下不能再默认解释为“保持旧排位”，除非系统拥有明确锚点信息。
- P4-AC2: 计划文档必须定义哪些情况下新模式应当阻断，且阻断原因必须来自明确缺失的业务前提，而不是继续复用“未出现在基准版本中”这种旧语义。
- P4-AC3: 计划文档必须指出现有冲突测试需要被清理或重写，并说明清理依据来自新的规则矩阵，而不是临时让某条测试绿掉。
- Evidence expectation: `prd.md` 的 P4 节包含规则矩阵和冲突测试处理策略，测试计划存在覆盖阻断与非阻断分支的用例。

### P5

- P5-AC1: 计划文档必须列出后端窄回归、前端静态检查和真实浏览器 E2E 三类验证命令，且每类都有明确 success signal。
- P5-AC2: 计划文档必须给出迁移顺序，至少覆盖“文档和术语统一 -> 数据职责拆分 -> 新管线落地 -> 规则切换 -> 默认入口切换”。
- P5-AC3: 计划文档必须给出发布前检查和回滚原则，确保新模式上线后出现语义错误时可以回退到 legacy 重排，而不是引入 fallback 混跑。
- Evidence expectation: `test-plan.md` 覆盖所有 acceptance ids，且 `prd.md` 中有清晰的发布与回滚策略。

## Done Definition

- 这份开发计划包含可审阅的 phase 分解、稳定 acceptance ids、明确的实施顺序和可运行的验证命令。
- 计划能解释当前系统为什么会出现“锁定/冻结订单未出现在基准版本中就阻断”的现象，以及为什么不能靠单点补丁解决。
- 计划明确指出先做数据职责拆分，再做事实重排入口，再做锁定/冻结语义重定义，不允许倒序执行。
- 所有 acceptance ids 都在 `test-plan.md` 中至少被一个测试用例覆盖。
- `task-state.json` 已同步出 phase 和 acceptance 结构，后续执行者可以直接从该任务目录继续推进。

## Blocking Conditions

- 如果业务方无法明确回答“锁定”和“冻结”在事实重排模式下分别约束什么，则不得进入 P4 以后的实现阶段。
- 如果无法把人工窗口与系统排程结果从同一字段职责中拆开，则不得直接上线“按事实从当天重排”入口。
- 如果后端只能提供末道报工事实，而产品要求工序级在制品事实重排，则必须先把该差距登记为前置缺口，不能假装当前事实已经足够。
- 如果真实浏览器验证环境不可用，则不得把涉及排程入口和订单池口径变更的任务标记为完成。
- 如果当前工作区存在直接覆盖本任务目标文件的未提交冲突改动，则后续执行阶段必须先停下并重新评估合并边界。
