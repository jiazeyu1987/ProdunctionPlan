# Test Plan

- Task ID: `python-gui-codex-cli-20260410T201416`
- Created: `2026-04-10T20:14:16`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `写一个单 python 的 GUI 程序，使用 codex CLI 进行问答`

## Test Scope

必须验证一个真实可运行的 Windows 桌面 GUI（tkinter）对 `codex exec` 的封装能力，重点覆盖：

- GUI 能启动、可交互、不会在执行期间冻结。
- 问答闭环：输入问题 -> 触发 `codex exec` -> 展示最终回答（last message）。
- fail-fast：前置条件缺失或 `codex exec` 失败必须明确报错，禁止“默认成功”“空答案当成功”“静默降级”。
- 单文件与无第三方依赖约束：脚本必须只用标准库。
- 目录与参数：默认在仓库根目录执行，支持选择 `--cd` 目录；若支持 `--model`，必须真实透传给 CLI。

明确不在本测试计划范围内：

- 任何浏览器验证、Playwright 自动化或 web 架构验证。本任务是桌面 GUI，验证面为真实桌面会话（real-runtime desktop session）。
- Codex 的回答质量评测（语义正确性）不作为通过条件；我们只验证“真实调用、输出被捕获、错误被暴露”。

## Environment

- OS: Windows（PowerShell）
- Python: 系统 `python`（必须包含标准库 `tkinter`）
- Codex CLI: `codex` 命令可执行；`codex exec` 与 `codex login status` 可用
- Workspace: `D:\ProjectPackage\ProductionPlan`
- Validation surface: real-runtime
- Required tools:
  - `python`
  - `codex`
  - （可选取证）截图工具或录屏工具

说明：不使用 `playwright` 的理由（基于仓库与任务现实）：

- 该任务交付物是 `tool/` 下的单文件 tkinter GUI，不是浏览器 UI。
- `playwright` 属于真实浏览器验证工具，与本任务的验证面不匹配；引入/依赖它会与“单文件、避免不必要依赖”的要求冲突。

## Accounts and Fixtures

- 若当前 Codex provider 需要登录态：必须确保 `codex login status` 显示可用。
- 不需要仓库内的任何账号/数据库种子/后端服务。
- 若 Codex provider 依赖网络：测试机器需要能访问该 provider；若 provider 发生持续 `503 Service Unavailable` / `No available providers`，本测试必须 fail fast 并记录为阻塞（不是产品缺陷，但属于环境阻塞）。

## Commands

1. 验证 Python + tkinter 可用
   - Command: `python -c "import tkinter; print('tkinter-ok')"`
   - Expected success signal: 输出包含 `tkinter-ok` 且退出码为 `0`

2. 验证 codex CLI 可用
   - Command: `codex --help`
   - Expected success signal: 输出包含 `Codex CLI` 且退出码为 `0`

3. 验证 codex exec 可用
   - Command: `codex exec --help`
   - Expected success signal: 输出包含 `Run Codex non-interactively` 且退出码为 `0`

4. （如需要登录态）验证登录状态
   - Command: `codex login status`
   - Expected success signal: 输出显示已登录/可用（以本机实际输出为准）；若未登录则测试 fail fast

5. 启动桌面 GUI（控制台方式）
   - Command: `cd D:\ProjectPackage\ProductionPlan; python tool\codex_gui_qa.py`
   - Expected success signal: 弹出窗口且保持响应；关闭窗口后进程退出码为 `0`

6. 启动桌面 GUI（可选：无控制台窗口）
   - Command: `cd D:\ProjectPackage\ProductionPlan; pythonw tool\codex_gui_qa.py`
   - Expected success signal: 弹出窗口；关闭窗口后无残留进程

## Test Cases

### T1: GUI 启动与基础控件存在

- Covers: P1-AC1
- Level: manual
- Command: `python tool\codex_gui_qa.py`
- Expected: 窗口能打开且可操作；具备问题输入区/发送按钮/回答显示区或日志区/状态指示；关闭窗口后程序正常退出。

### T2: 单次问答成功路径（真实 codex exec 调用 + last message 捕获）

- Covers: P1-AC2
- Level: manual + integration
- Command: 启动 GUI，输入 `用一句话解释什么是 fastapi？` 并点击发送（真实调用一次 `codex exec`）。
- Expected: UI 显示 running 且不冻结；完成后回答区显示非空文本；日志区可见关键参数（`codex exec`、`-C/--cd`、`--output-last-message` 或等价策略）。

### T3: 多行输入与中文编码验证（stdin 传入）

- Covers: P1-AC2
- Level: manual + integration
- Command: 在 GUI 输入多行中文问题（含换行与标点，例如“请用要点回答：…”，三行以上）并点击发送。
- Expected: 回答区能正确显示中文与换行，无乱码/丢行；若 Codex 返回错误，必须以可读方式显示且标记失败（不吞错）。

### T4: fail-fast：选择非 git 目录导致 codex exec 失败时必须明确报错

- Covers: P1-AC3
- Level: manual + integration
- Command: 在 GUI 将工作目录切换到非 git 目录（如 `C:\Windows`），发送任意问题触发一次 `codex exec`。
- Expected: `codex exec` 失败时，GUI 显示失败状态、退出码与 stderr 摘要；不得显示空回答或伪成功结果。

### T5: fail-fast：codex 不可用时的启动/运行行为

- Covers: P1-AC3
- Level: manual
- Command: 在 `codex` 不可用的环境下启动 GUI 并发送问题（例如使用不包含 codex 的 PATH 启动会话）。
- Expected: 程序明确报告 `codex` 不可用并 fail fast；不得出现任何模拟回答或自动替代路径。

### T6: 无第三方依赖与单文件约束验证

- Covers: P1-AC4
- Level: review
- Command: Review PR diff / 文件列表与 imports。
- Expected: 仅新增 `tool/codex_gui_qa.py`（任务工件除外）；未新增 `pyproject.toml` 且未修改 `backend/requirements.txt`；脚本 imports 仅来自 Python 标准库。

### T7: UI 不冻结（长耗时调用下仍可交互）

- Covers: P2-AC1
- Level: manual
- Command: 发送较耗时问题（例如“请用不少于 200 字介绍 FastAPI 的优缺点。”），运行中尝试移动窗口/滚动/聚焦输入/（若有）点击取消。
- Expected: 窗口不未响应；状态指示与控件 disable/enable 符合设计且无静默错误。

### T8: 取消运行（终止子进程且恢复 UI）

- Covers: P2-AC2
- Level: manual + integration
- Command: 发送耗时问题并在 1-3 秒内点击“取消”。
- Expected: `codex` 子进程被终止且无残留；回答区不继续追加该次内容；UI 恢复可再次发送；取消失败时必须明确报错。

### T9: 保存记录（UTF-8 输出、字段齐全、失败可见）

- Covers: P2-AC3
- Level: manual
- Command: 完成至少一次成功问答后点击“保存记录”，选择可写目录保存。
- Expected: 生成 UTF-8 文件，包含时间戳/工作目录/问题/回答；若路径不可写，必须明确报错且不丢失当前 UI 内容。

### T10: 透传模型参数（如提供 model 选择）

- Covers: P2-AC4
- Level: manual + integration
- Command: 在 GUI 指定一个 model（可用一个明显不存在的模型名触发错误），发送问题。
- Expected: 日志区可验证实际通过 `codex exec -m <MODEL>` 传参；模型无效导致失败时，错误原样暴露并 fail fast（不自动切换/降级）。

## Coverage Matrix

| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | GUI | 启动与控件存在 | manual | P1-AC1 | 窗口截图 |
| T2 | codex exec integration | 单次问答成功与 last message 展示 | manual+integration | P1-AC2 | 成功问答截图，日志区命令摘要 |
| T3 | Encoding / stdin | 多行中文输入可用 | manual+integration | P1-AC2 | 输入与输出截图 |
| T4 | Fail-fast | 非 git 目录导致 codex 失败 | manual+integration | P1-AC3 | 失败截图（含退出码/错误摘要） |
| T5 | Fail-fast | codex 不可用 | manual | P1-AC3 | 失败截图（找不到命令） |
| T6 | Repo constraints | 单文件、无第三方依赖 | review | P1-AC4 | PR diff / 文件列表证据 |
| T7 | Responsiveness | 长耗时 UI 不冻结 | manual | P2-AC1 | 运行中截图/录屏（可选） |
| T8 | Process control | 取消运行并无残留进程 | manual+integration | P2-AC2 | 取消后截图 + 任务管理器/`Get-Process` 证据（可选） |
| T9 | Persistence | 保存记录 UTF-8 | manual | P2-AC3 | 保存文件路径与内容摘要截图 |
| T10 | CLI passthrough | `-m/--model` 透传且错误可见 | manual+integration | P2-AC4 | 日志区参数截图 + 失败截图 |

## Evaluator Independence

- Mode: blind-first-pass
- Validation surface: real-runtime
- Required tools: python, codex
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: 必须在真实 Windows 桌面会话中启动 GUI 并交互，且必须真实调用 `codex exec`；若 provider/network/login 不满足导致无法得到真实回答，记录为阻塞并附原始错误信息。
- Escalation rule: tester 首轮给出初始结论前不得查看 `execution-log.md` 和 `task-state.json`；只有在需要差异分析时才允许解锁。

## Pass / Fail Criteria

- Pass when:
  - `tool/codex_gui_qa.py` 能启动并完成至少一次真实问答展示（P1-AC1, P1-AC2）。
  - 所有 fail-fast 场景都能明确报错且无静默降级（P1-AC3）。
  - 仓库未引入任何 Python 第三方依赖且保持单文件交付（P1-AC4）。
  - UI 在执行期间不冻结、支持取消（若在范围内）且可保存记录（P2-AC1..P2-AC3）。
  - 若支持 model 参数，透传真实且错误可见（P2-AC4）。
- Fail when:
  - 任一前置条件缺失但产品仍“看起来工作”（例如显示空答案/默认答案）。
  - `codex exec` 失败被吞掉或被静默替换成其它路径。
  - 引入额外依赖、拆分成多文件、或修改 `backend/requirements.txt` / 新增 `pyproject.toml`。

## Regression Scope

- `tool/` 下现有脚本不应被影响（本任务只新增文件）。
- 运行目录选择与路径处理不应破坏 Windows 路径（空格、中文路径、反斜杠）。
- 编码：GUI 显示区与保存文件必须保证 UTF-8 与中文可读性。

## Reporting Notes

- 测试结果与证据写入 `doc/tasks/python-gui-codex-cli-20260410T201416/test-report.md`。
- 建议最少证据：
  - 启动截图（T1）
  - 成功问答截图（T2）
  - 失败路径截图（T4 或 T5）
  - 保存记录文件的路径与内容摘要截图（T9）
