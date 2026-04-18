# Test Plan

- Task ID: `task-4133d905b2-20260418T233206`
- Created: `2026-04-18T23:32:06`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `系统里排产参数变化之后,点击排产按钮,订单的完成日期也要跟随参数的变化而变化`

## Test Scope

验证排产日历页中的排产参数在点击“排产”或“重排”后是否真实进入后端排产计算，并验证订单完成日期展示是否来自最新排产事实。重点覆盖首次排产前的规则保存、额外夜班对完成日期的影响、以及完成日期展示与排产事实字段的一致性。

不覆盖 Lite Scheduler 手工完工逻辑，不覆盖与本任务无关的 ERP 同步正确性。

## Environment

- 平台：Windows，本地仓库 `D:\ProjectPackage\ProductionPlan`
- 后端数据库：测试时优先使用隔离 SQLite 副本或 pytest 临时库
- 前端：`fronted`
- 真实浏览器验证：Playwright Chromium
- 若需要真实页面验证，使用仓库现有本地前后端或隔离 e2e 运行时

## Accounts and Fixtures

- 排产员角色账号，能够访问排产日历页与订单池页
- 一组可控测试夹具，满足：
  - 至少一张订单在默认规则下跨多天排产
  - 打开额外夜班后，该订单或对照订单的 `scheduled_finish_date` / `scheduled_finish_time` 会变化
- 若真实库无法稳定提供敏感性场景，测试必须在隔离数据库中显式构造该夹具

## Commands

- `python -m pytest backend/tests/test_app_service_generate_schedule_unlocked_only.py -k simulation_current_day -q`
  期望：通过，证明模拟当前日约束仍有效。
- `python -m pytest backend/tests/test_app_service_schedule_trust.py -q`
  期望：通过，证明排产事实与订单展示口径未回归。
- `python -m pytest backend/tests/test_shift_capacity_schedule.py -q`
  期望：通过，证明班次/夜班规则仍参与排产。
- `python -m pytest backend/tests/test_simulation_manual_advance.py -q`
  期望：通过，证明模拟推进逻辑未回归。
- `npx playwright test ...` 或仓库已有浏览器脚本
  期望：真实浏览器下修改额外夜班并点击首次排产后，页面中的完成日期展示与最新排产事实一致。

## Test Cases

### T1: 首次排产前保存日历规则

- Covers: P1-AC1, P2-AC1
- Level: integration
- Command: 后端/前端针对首次排产入口的自动化验证
- Expected: 首次点击“排产”前会先保存 `skip_statutory_holidays`、`weekend_rest_mode`、`date_shift_mode_by_date`，随后排产使用保存后的规则。

### T2: 额外夜班改变排产完成日期

- Covers: P1-AC2, P2-AC2
- Level: integration
- Command: pytest 夹具验证，构造默认规则与额外夜班规则的对照排产
- Expected: 同一订单在开启额外夜班后，`scheduled_finish_date` 或 `scheduled_finish_time` 相比默认规则发生变化。

### T3: 完成日期展示使用当前排产事实

- Covers: P2-AC3, P3-AC1
- Level: e2e
- Command: `npx playwright test tests/e2e/production-plan.e2e.spec.ts -g "schedule parameter finish-date refresh"` 或同等真实浏览器脚本
- Expected: 订单池列表与详情中的“预计完工日期 / 末道预计完工 / 建议计划完工”使用当前排产事实字段；参数变化后页面展示刷新为最新结果。

### T4: 参数已进入计算但未改关键路径时的可解释性

- Covers: P3-AC2
- Level: manual
- Command: 使用真实浏览器对同一订单执行“修改额外夜班 -> 点击排产 -> 对照完成日期和任务明细”，必要时配合隔离数据库对照实验
- Expected: 若当前真实数据下某个参数没有改变某张订单的完成日期，测试报告必须给出“任务已变化但关键路径未变化”或“当前订单不受该参数影响”的证据，而不是接受陈旧展示。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | 排产日历页 / 排产入口 | 首次排产前保存当前日历规则 | integration | P1-AC1, P2-AC1 | `execution-log.md`, pytest 输出 |
| T2 | 后端排产引擎 | 额外夜班改变订单完成日期 | integration | P1-AC2, P2-AC2 | `execution-log.md`, 新增/更新测试 |
| T3 | 订单池展示 / 真实浏览器 | 页面展示的完成日期随最新排产事实更新 | e2e | P2-AC3, P3-AC1 | `test-report.md`, screenshot/trace |
| T4 | 参数敏感性说明 | 参数生效但关键路径不变时给出证据解释 | e2e/manual | P3-AC2 | `test-report.md` |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: pytest, playwright
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: 在真实仓库和真实浏览器中执行。涉及 UI 的验收必须使用真实浏览器并产出截图、trace 或视频等证据。
- Escalation rule: 初次给出结论前，不查看 `execution-log.md` 和 `task-state.json`。

## Pass / Fail Criteria

- Pass when:
  - 首次排产路径保存并使用了最新日历规则；
  - 受控场景下，额外夜班等参数变化会导致订单完成日期变化；
  - 真实浏览器页面展示与最新排产事实一致；
  - 若某场景下完成日期未变，测试报告能证明是关键路径未变化而非参数失效或展示陈旧。
- Fail when:
  - 首次排产仍绕过规则保存；
  - 参数变化后后端排产结果完全不变且无法证明是数据敏感性问题；
  - 页面继续展示旧的完成日期字段；
  - 任一必需验证命令失败或浏览器证据缺失。

## Regression Scope

- 模拟推进一天 / 重置模拟
- 周末模式与法定假日对班次可用性的影响
- 订单池中的排程事实字段与风险标签
- 当前排产与已保存存档的切换

## Reporting Notes

结果写入 `test-report.md`。

测试者必须保持独立，不修产品代码；真实浏览器通过的用例必须附带至少一个证据文件路径。
