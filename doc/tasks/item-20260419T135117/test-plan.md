# Test Plan

- Task ID: `item-20260419T135117`
- Created: `2026-04-19T13:51:17`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `把当前会整表刷新订单池/生产订单列表的操作改成只更新对应 item；只有手动点击刷新生产订单时才允许刷新整个订单列表`

## Test Scope

验证订单池页面中与订单 item 更新直接相关的操作是否从整表刷新改为局部更新，并验证手动 ERP 同步仍然保留整表刷新。重点覆盖：

- 单张订单操作后的局部刷新
- 批量订单操作后的局部刷新
- 保存手工预计开始时间后的局部刷新
- 手动 ERP 同步后的整表刷新保留行为

不覆盖：

- 排产算法正确性
- 报工导入、物料刷新、库存刷新逻辑
- 与订单池无关的页面性能问题

## Environment

- Windows 本地开发环境
- 仓库路径：`D:\ProjectPackage\ProductionPlan`
- 前后端启动命令：`重启前后端.bat`
- 后端地址：`http://127.0.0.1:8000`
- 前端地址：`http://127.0.0.1:2798`
- 若执行真实页面验证，需要可用浏览器和 Playwright

## Accounts and Fixtures

- 需要具备调度员权限账号，能够访问订单池页面与 ERP 同步按钮
- 需要数据库内存在可操作的订单池数据，至少包含：
  - 可锁单/解锁订单
  - 可提优先级订单
  - 可编辑预计开始日期的订单
- 若缺少上述数据，测试必须失败并在 `test-report.md` 记录阻塞

## Commands

- `python -m pytest backend\tests\test_app_service_order_pool.py -q`
  期望：订单池单条查询与相关后端契约测试通过
- `python -m pytest backend\tests\test_job_dispatcher_command_services.py -q`
  期望：相关命令分发链路未被破坏
- `python -m pytest backend\tests\test_shift_capacity_schedule.py -q`
  期望：既有排产行为回归通过，证明本任务未误伤排产链路
- 浏览器真实验证
  期望：通过 Network 观察到局部操作不再重新拉取整张 `/api/order-pool`；手动 ERP 同步仍会整表刷新

## Test Cases

### T1: 单张锁单/解锁不整表刷新

- Covers: P1-AC1, P2-AC1, P3-AC1
- Level: manual
- Command: 启动前后端后在订单池页面执行单张锁单或解锁，观察 Network
- Expected: 不出现新的整表 `/api/order-pool` 全量请求；受影响订单行状态更新正确

### T2: 单张优先级调整不整表刷新

- Covers: P2-AC1, P3-AC1
- Level: manual
- Command: 在订单池页面执行单张优先级调整，观察 Network 与列表展示
- Expected: 不出现新的整表 `/api/order-pool` 全量请求；对应订单优先级显示更新正确

### T3: 批量操作只更新受影响 item

- Covers: P2-AC2, P3-AC1
- Level: manual
- Command: 在订单池页面勾选多张订单后执行批量锁单、批量解锁或批量提优先级
- Expected: 不出现新的整表 `/api/order-pool` 全量请求；仅受影响订单行发生变化

### T4: 保存手工预计开始时间只刷新当前订单

- Covers: P2-AC3, P3-AC1
- Level: manual
- Command: 在订单池详情区修改预计开始日期/班次并保存
- Expected: 不出现新的整表 `/api/order-pool` 全量请求；当前订单列表行与详情区字段同步更新

### T5: 手动 ERP 同步仍整表刷新

- Covers: P1-AC2, P2-AC4, P3-AC2, P3-AC3
- Level: manual
- Command: 在订单池页面点击“ERP 刷新生产订单”并确认执行
- Expected: 允许出现整表刷新；列表根据同步结果整体更新；不会误退化为只改单个 item

### T6: 单条订单查询契约支撑局部更新

- Covers: P1-AC3
- Level: unit/integration
- Command: `python -m pytest backend\tests\test_app_service_order_pool.py -q`
- Expected: `/api/order-pool/{order_no}` 所依赖的后端契约测试通过，返回字段足以支撑前端 item 替换

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | 订单池页面 | 单张锁单/解锁后不整表刷新 | manual | P1-AC1, P2-AC1, P3-AC1 | `test-report.md` + 浏览器网络证据 |
| T2 | 订单池页面 | 单张优先级调整后不整表刷新 | manual | P2-AC1, P3-AC1 | `test-report.md` + 浏览器网络证据 |
| T3 | 订单池页面 | 批量操作后只更新受影响 item | manual | P2-AC2, P3-AC1 | `test-report.md` + 浏览器网络证据 |
| T4 | 订单池详情区 | 保存预计开始时间后局部更新 | manual | P2-AC3, P3-AC1 | `test-report.md` + 浏览器网络证据 |
| T5 | ERP 同步入口 | 手动 ERP 同步仍整表刷新 | manual | P1-AC2, P2-AC4, P3-AC2, P3-AC3 | `test-report.md` + 浏览器网络证据 |
| T6 | 后端契约 | 单条订单查询契约可支撑 item 更新 | unit/integration | P1-AC3 | pytest 输出 |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: playwright, pytest
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: 使用真实前后端运行时与真实浏览器验证订单池页面行为；浏览器验证必须包含具体网络或截图证据。
- Escalation rule: 在测试者给出首轮结论前，不查看 `execution-log.md` 与 `task-state.json`。

## Pass / Fail Criteria

- Pass when:
  - T1-T4 均证明非 ERP 手动同步操作不会重新拉整张 `/api/order-pool`
  - T5 证明手动 ERP 同步仍然保留整表刷新
  - T6 通过，且没有出现因 item 级刷新导致的后端契约缺口
- Fail when:
  - 任一局部操作仍触发整表 `/api/order-pool` 请求
  - 手动 ERP 同步失去整表刷新能力
  - 详情区与列表在局部更新后出现不一致
  - 测试缺少真实浏览器或真实请求级证据

## Regression Scope

- 订单池筛选、排序、选中态保留
- 订单详情区展示一致性
- 批量操作结果提示
- ERP 同步预览与执行链路
- 单条订单查询接口返回结构

## Reporting Notes

将结果写入 `test-report.md`。

测试者必须保持独立，不修改产品代码；若真实浏览器验证通过，每个通过的 real-browser 用例至少引用一个截图、trace、HAR 或网络日志证据。
