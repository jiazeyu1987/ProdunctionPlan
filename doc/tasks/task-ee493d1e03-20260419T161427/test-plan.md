# Test Plan

- Task ID: `task-ee493d1e03-20260419T161427`
- Created: `2026-04-19T16:14:27`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `删除上一轮为订单池局部刷新引入的过度设计，并确保锁单、解锁、升权、降权对排产结果有实际影响`

## Test Scope

验证两类结果：

- 删除跨页订单池局部刷新信号设计后，系统不再依赖该机制，且订单池页内局部刷新能力仍保留。
- 锁单、解锁、升权、降权在普通排产与事实重排中会真实改变排产结果，而不是只改状态字段。

不覆盖：

- 大规模性能优化
- ERP 同步业务语义变化
- 排产页跨页联动体验优化

## Environment

- Windows 本地开发环境
- 仓库路径：`D:\ProjectPackage\ProductionPlan`
- 前后端可启动
- Python / pytest 可运行
- 如需页面验证，浏览器和 Playwright 可用

## Accounts and Fixtures

- 需要具备调度员权限的可登录账号，或可替代的本地 stub 环境
- 需要有可控测试库或单测夹具，能构造至少两张会竞争同一产能的订单
- 若缺少可竞争订单夹具，则测试必须失败并记录阻塞

## Commands

- `python -m pytest backend\tests\test_app_service_generate_schedule_unlocked_only.py -q`
  期望：锁单相关普通排产回归通过
- `python -m pytest backend\tests\test_schedule_fact_replan.py -q`
  期望：事实重排相关回归通过
- `python -m pytest backend\tests\test_app_service_batch_dispatch.py -q`
  期望：锁单/解锁/升权/降权状态变更回归通过
- 代码级验证
  期望：跨页刷新信号文件与调用点被删除，不再存在残余引用

## Test Cases

### T1: 删除跨页订单池刷新信号设计

- Covers: P1-AC1, P2-AC1, P4-AC1
- Level: integration
- Command: 代码检索 `ordersPoolRefreshSignal`、`affected_order_nos` 跨页消费点，并确认相关文件与引用已删除或收口
- Expected: 不再存在跨页局部刷新信号文件、发布逻辑、消费逻辑及残余引用

### T2: 订单池页内局部刷新能力保留

- Covers: P2-AC2
- Level: integration/manual
- Command: 复核订单池页内锁单/解锁/升权/降权/删除/保存预计开始时间的局部 item 更新路径
- Expected: 订单池页内操作仍然走 item 级更新，不退化回整表刷新

### T3: 普通排产中锁单会影响结果

- Covers: P1-AC2, P3-AC1
- Level: unit/integration
- Command: 新增或更新普通排产测试，构造锁单与未锁单订单竞争同一产能
- Expected: 锁单状态改变后，排产结果顺序或起始时间发生变化；锁单订单不再被简单跳过

### T4: 升权/降权会影响普通排产结果

- Covers: P1-AC2, P3-AC3
- Level: unit/integration
- Command: 新增或更新排序测试，构造两张竞争订单并调整 `priority_level`
- Expected: 升权或降权后，排产结果顺序发生变化

### T5: 事实重排中锁单/优先级会影响未来结果

- Covers: P1-AC2, P3-AC2
- Level: unit/integration
- Command: 新增或更新事实重排测试，构造事实边界后的未来订单竞争场景
- Expected: 锁单/优先级会影响事实重排后的未来任务顺序

### T6: 解锁后排产恢复普通约束

- Covers: P3-AC1, P3-AC2
- Level: unit/integration
- Command: 在同一组夹具中比较锁单前后与解锁后的排产结果
- Expected: 解锁后不再保留锁单带来的优先结果

### T7: 测试报告区分设计删减与排产影响

- Covers: P4-AC2
- Level: review
- Command: 审查 `test-report.md`
- Expected: 测试报告单独记录“删除了什么过度设计”与“锁单/优先级如何影响排产结果”两类结论与证据

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | 设计收口 | 删除跨页订单池刷新信号机制 | integration | P1-AC1, P2-AC1, P4-AC1 | 代码检索输出、执行日志 |
| T2 | 订单池页面 | 页内局部 item 更新能力保留 | integration/manual | P2-AC2 | 执行日志、必要的页面证据 |
| T3 | 普通排产 | 锁单影响排产结果 | unit/integration | P1-AC2, P3-AC1 | pytest 输出 |
| T4 | 普通排产 | 升权/降权影响排产结果 | unit/integration | P1-AC2, P3-AC3 | pytest 输出 |
| T5 | 事实重排 | 锁单/优先级影响未来任务结果 | unit/integration | P1-AC2, P3-AC2 | pytest 输出 |
| T6 | 普通/事实排产 | 解锁后恢复普通约束 | unit/integration | P3-AC1, P3-AC2 | pytest 输出 |
| T7 | 测试收口 | 测试报告区分设计删减与排产影响 | review | P4-AC2 | `test-report.md` |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-runtime
- Required tools: pytest
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: 先用真实代码和测试夹具验证；若需要页面确认，只在测试计划已有结论后补做手工检查
- Escalation rule: 在测试者给出初始结论前，不查看 `execution-log.md` 和 `task-state.json`

## Pass / Fail Criteria

- Pass when:
  - 跨页局部刷新信号相关设计已删除且无残留引用
  - 订单池页内局部 item 更新能力仍保留
  - 锁单/解锁/升权/降权至少在一组普通排产和一组事实重排测试中被证明会改变结果
- Fail when:
  - 仍存在跨页信号残留
  - 删除过度设计后订单池页内操作退化为整表刷新
  - 锁单/升权只改状态字段，没有改变排产结果

## Regression Scope

- 订单池页内单条和批量操作
- 普通排产
- 事实重排
- 候选排序逻辑
- 已有锁单/优先级批处理状态更新测试

## Reporting Notes

结果写入 `test-report.md`。

如发现“过度设计删除”与“排产影响恢复”之间存在冲突，必须明确记录是哪一侧被阻塞，而不是默认保留较复杂设计。
