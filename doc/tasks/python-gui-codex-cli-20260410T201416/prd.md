# PRD

- Task ID: `python-gui-codex-cli-20260410T201416`
- Created: `2026-04-10T20:14:16`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `写一个单 python 的 GUI 程序，使用 codex CLI 进行问答`

## Goal

在本仓库内提供一个“单文件 Python 桌面 GUI”工具脚本，作为 `codex exec` 的可视化外壳：用户在窗口中输入问题并点击发送，程序使用真实的 `codex exec` 非交互式调用获取回答并展示；同时对缺失前提（`codex` 不可用、登录态不可用、provider 不可用、`tkinter` 缺失等）严格 fail fast，明确报错，不引入 mock、兼容性兜底或静默降级。

## Scope

- 新增单个 Python 文件（标准库实现，桌面 GUI）：
  - `tool/codex_gui_qa.py`
- GUI 的核心用户流（以真实 CLI 调用为中心）：
  - 选择工作目录（默认仓库根目录），用于 `codex exec -C/--cd`。
  - 输入问题（支持多行），点击发送。
  - 在后台执行一次 `codex exec`，拿到“最后一条消息”的纯文本并展示。
  - 展示运行状态（running / finished / failed），并在失败时展示退出码与 stderr 摘要。
  - 可选：取消正在运行的一次问答（终止子进程）。
  - 可选：保存问答记录到本地文件（UTF-8）。
- 仅围绕真实 CLI 调用设计，不假设存在任何 Codex SDK/API。

## Non-Goals

- 不新增任何 Python 第三方依赖，不新增 `pyproject.toml`，不修改 `backend/requirements.txt`（该文件当前仅包含 fastapi/uvicorn/requests）。
- 不把本工具做成浏览器前端（非 web），不引入 Playwright，不以浏览器自动化作为验证手段。
- 不实现“离线模式”“本地替代模型”“失败自动重试/降级”等任何兜底路径。
- 不为仓库业务系统（FastAPI/Next/SQLite 等）新增功能或重构；本任务仅交付工具脚本。

## Preconditions

以下任一前提缺失都必须停止执行并记录为阻塞（严格 no-fallback）：

- OS: Windows（PowerShell 环境），具备可交互桌面会话（能显示窗口）。
- `python` 可用，且包含 `tkinter`（标准库 GUI）。验证方式：`python -c "import tkinter"`.
- `codex` CLI 可用且在 PATH 上。验证方式：`codex --help`。
- `codex exec --help` 可用（确认 GUI 依赖真实 `codex exec` 调用）。验证方式：`codex exec --help`。
- 若当前 Codex provider 需要登录态：`codex login status` 显示已登录且可用。
- 若 provider 需要网络：本机可访问对应 provider（若 provider 返回持续 `503 Service Unavailable` / `No available providers`，必须明确失败，不得伪造成功）。

## Impacted Areas

- 新增：`tool/codex_gui_qa.py`（单文件 GUI 工具）
- 文档/任务工件（由 workflow 维护）：`doc/tasks/python-gui-codex-cli-20260410T201416/*`
- 可参考的脚本风格：`tool/deploy/publish_to_server.py`（UTF-8 输出与 fail-fast 错误处理）

## Phase Plan

### P1: MVP GUI 封装与真实 codex exec 调用

- Objective:
  - 提供可运行的 tkinter GUI，完成一次完整问答闭环，并用真实 `codex exec` 获取回答。
  - 处理最关键的 fail-fast：工具缺失/命令失败/非 git 目录/编码错误等都要明确报错。
- Owned paths:
  - `tool/codex_gui_qa.py`
- Dependencies:
  - 系统 Python 标准库（`tkinter`, `subprocess`, `threading`, `queue`, `tempfile`, `pathlib`）
  - 外部工具：`codex` CLI（真实可执行文件）
- Deliverables:
  - 一个可直接运行的单文件脚本：`python tool/codex_gui_qa.py`
  - GUI 使用 `codex exec` 的明确命令构造方式（不 `shell=True`）
  - 成功与失败两类路径都可验证（错误信息可读、无静默吞错）

### P2: 可观测性与桌面可用性增强（仍保持单文件与无依赖）

- Objective:
  - 增强桌面体验，确保长耗时调用不冻结 UI，并提供可追溯输出与记录导出。
  - 增加最小的高级参数入口（如 `--model`），但不做任何“自动修复/降级”。
- Owned paths:
  - `tool/codex_gui_qa.py`
- Dependencies:
  - `codex exec` 已确认支持：`-m/--model`、`-C/--cd`、`-o/--output-last-message`、`--color`、`--json`（是否启用由设计决定）
- Deliverables:
  - 问答历史（同一窗口内可回看）
  - “保存记录”到本地文件（UTF-8，包含时间戳、工作目录、模型参数、问题与回答）
  - 可取消正在运行的问答（终止子进程并恢复 UI 状态）

## Phase Acceptance Criteria

### P1

- P1-AC1: 在 `D:\ProjectPackage\ProductionPlan` 下执行 `python tool/codex_gui_qa.py` 能打开桌面窗口，包含“问题输入区”“发送按钮”“回答显示区/日志区”“状态指示”。
- P1-AC2: 发送一次问题时，程序必须通过真实 CLI 调用 `codex exec` 获取回答，并将回答展示在 GUI 中；命令必须使用 `codex exec` 的真实参数能力：
  - 使用 `PROMPT` 为 `-` 并通过 stdin 传入多行文本，避免引号/转义问题。
  - 使用 `--output-last-message <file>` 或等价方式稳定提取最终回答（而不是脆弱解析彩色输出）。
  - 使用 `-C/--cd <dir>` 指定工作目录（默认仓库根目录，可由用户选择）。
- P1-AC3: 若 `codex` 不存在、`tkinter` 不可导入、工作目录不是 git repo 导致 `codex exec` 失败、或 `codex exec` 返回非 0 退出码，程序必须明确失败并展示：
  - 失败原因摘要（含退出码）
  - stderr 或关键错误信息（不吞异常、不显示“默认成功”）
  - 不得生成任何伪造回答或“空回答当成功”
- P1-AC4: 脚本运行不依赖任何第三方 pip 包；仓库不新增 `pyproject.toml`，不修改 `backend/requirements.txt`。
- Evidence expectation:
  - 最少包含：启动截图、一次成功问答截图、一次失败路径截图（例如选择非 git 目录触发 `codex exec` 错误）、以及 GUI 内显示的执行命令字符串。

### P2

- P2-AC1: UI 不能因为调用 `codex exec` 而冻结；调用期间输入/按钮状态与“正在运行”提示明确，结束后恢复。
- P2-AC2: 提供取消当前运行的能力；取消后不得继续写入回答，不得遗留后台 `codex` 子进程，UI 状态回到可再次发送。
- P2-AC3: 提供“保存记录”功能，保存的文件为 UTF-8，内容至少包含时间戳、工作目录、（若提供）模型参数、问题文本、回答文本与失败时的错误摘要；保存失败必须显式报错。
- P2-AC4: 若提供模型选择，则必须真实通过 `codex exec -m <MODEL>` 传递，且当模型名无效时 `codex` 的错误必须原样可见（不做自动纠正/降级）。
- Evidence expectation:
  - 运行期间 UI 状态变化截图、取消操作截图、保存出的记录文件样例（路径与内容摘要）以及一次带 `-m` 参数的运行日志。

## Done Definition

- P1、P2 两个 phase 全部完成，且所有 acceptance ids（P1-AC1..P1-AC4、P2-AC1..P2-AC4）均可被独立测试者在真实 Windows 桌面会话下复现验证。
- 工具脚本落在 `tool/` 下，单文件可运行，且不引入任何第三方 Python 依赖。
- 所有失败均为明确失败（fail fast），不引入 mock、兜底、静默降级；错误信息对排查足够可读。
- 测试计划中的命令与手工步骤可执行，且 `test-plan.md` 的每个测试用例都能产出证据写入 `test-report.md`。

## Blocking Conditions

- `python` 不可用或不包含 `tkinter`，无法启动桌面 GUI。
- `codex` CLI 不可用（`codex --help` 失败）或 `codex exec --help` 不存在。
- `codex login status` 显示未登录且当前 provider 需要登录态。
- 当前 provider 持续不可用（例如连续 `503 Service Unavailable` / `No available providers`），导致无法产生真实回答。
- 任何需要通过 mock、默认成功、自动重试/降级才能“看起来可用”的实现方案。

