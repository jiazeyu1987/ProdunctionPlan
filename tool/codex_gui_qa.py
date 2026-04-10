"""
Single-file (stdlib-only) Windows desktop GUI wrapper around `codex exec`.

Features:
- Real `codex exec` invocation using stdin prompt input (`-`) and
  `--output-last-message` for stable final-answer capture.
- Working directory selection via `-C/--cd`.
- Optional model passthrough via `-m/--model`.
- Background execution so the tkinter UI stays responsive.
- Explicit failure states with surfaced exit code / stderr excerpts.
- Cancel support for the active Codex subprocess.
- Conversation history and UTF-8 record export.
"""

from __future__ import annotations

import datetime as _dt
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, ttk
except Exception as exc:  # pragma: no cover - only hit when tkinter is missing.
    raise SystemExit(f"FATAL: tkinter is required but could not be imported: {exc!r}")


_LOGIN_BAD_PAT = re.compile(
    r"(not\s+logged|logged\s+out|unauthori[sz]ed|please\s+log\s*in|run\s+.*\bcodex\s+login\b)",
    re.IGNORECASE,
)

_APP_TITLE = "Codex CLI Q&A"
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _now_str() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _shorten(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    summary: str
    details: str


@dataclass(frozen=True)
class ExecResult:
    ok: bool
    cancelled: bool
    answer: str
    returncode: int
    stderr: str
    stdout: str
    cmd: list[str]
    output_file: str
    exception_trace: str
    cleanup_error: str
    workdir: str
    model: str
    prompt: str


@dataclass(frozen=True)
class HistoryEntry:
    timestamp: str
    workdir: str
    model: str
    prompt: str
    answer: str
    status: str
    error_summary: str
    command: str


class CodexRunner:
    def __init__(self) -> None:
        self._codex_path = shutil.which("codex")

    def preflight(self) -> PreflightResult:
        if not self._codex_path:
            return PreflightResult(
                ok=False,
                summary="codex not found in PATH",
                details="`codex` executable was not found. Ensure Codex CLI is installed and on PATH.",
            )

        # Use the resolved absolute path so Windows subprocess invocation does not
        # accidentally hit a non-executable wrapper like the extensionless npm shim.
        codex = self._codex_path
        checks: list[tuple[list[str], str]] = [
            ([codex, "--help"], "codex --help"),
            ([codex, "exec", "--help"], "codex exec --help"),
            ([codex, "login", "status"], "codex login status"),
        ]

        details: list[str] = []
        for cmd, label in checks:
            try:
                completed = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception:
                return PreflightResult(
                    ok=False,
                    summary=f"preflight failed running: {label}",
                    details=traceback.format_exc(),
                )

            details.append(f"$ {' '.join(cmd)}")
            details.append(f"exit={completed.returncode}")
            if completed.stdout:
                details.append("stdout:")
                details.append(_shorten(completed.stdout, 2000).rstrip())
            if completed.stderr:
                details.append("stderr:")
                details.append(_shorten(completed.stderr, 2000).rstrip())

            if completed.returncode != 0:
                return PreflightResult(
                    ok=False,
                    summary=f"{label} failed (exit={completed.returncode})",
                    details="\n".join(details).rstrip(),
                )

            if label == "codex login status":
                combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
                if _LOGIN_BAD_PAT.search(combined):
                    return PreflightResult(
                        ok=False,
                        summary="codex login status indicates not logged in",
                        details="\n".join(details).rstrip(),
                    )

        return PreflightResult(
            ok=True,
            summary="preflight ok",
            details="\n".join(details).rstrip(),
        )

    def exec_qa(
        self,
        *,
        workdir: str,
        prompt: str,
        model: str,
        register_process: Callable[[subprocess.Popen[str] | None], None] | None = None,
    ) -> ExecResult:
        wd = Path(workdir).expanduser()
        if not wd.exists() or not wd.is_dir():
            return ExecResult(
                ok=False,
                cancelled=False,
                answer="",
                returncode=2,
                stderr=f"Invalid workdir: {workdir!r} (directory does not exist).",
                stdout="",
                cmd=[],
                output_file="",
                exception_trace="",
                cleanup_error="",
                workdir=str(wd),
                model=model.strip(),
                prompt=prompt,
            )
        if prompt.strip() == "":
            return ExecResult(
                ok=False,
                cancelled=False,
                answer="",
                returncode=2,
                stderr="Question is empty. Please enter a question before sending.",
                stdout="",
                cmd=[],
                output_file="",
                exception_trace="",
                cleanup_error="",
                workdir=str(wd),
                model=model.strip(),
                prompt=prompt,
            )

        out_path = Path(tempfile.gettempdir()) / f"codex-last-message-{uuid.uuid4().hex}.txt"
        codex = self._codex_path
        if not codex:
            return ExecResult(
                ok=False,
                cancelled=False,
                answer="",
                returncode=2,
                stderr="`codex` executable was not found in PATH.",
                stdout="",
                cmd=[],
                output_file="",
                exception_trace="",
                cleanup_error="",
                workdir=str(wd),
                model=model.strip(),
                prompt=prompt,
            )

        cmd = [codex, "exec", "-C", str(wd)]
        if model.strip():
            cmd.extend(["-m", model.strip()])
        cmd.extend(["--output-last-message", str(out_path), "-"])

        proc: subprocess.Popen[str] | None = None
        stdout = ""
        stderr = ""
        cleanup_error = ""

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            )
            if register_process is not None:
                register_process(proc)

            stdout, stderr = proc.communicate(input=prompt)
        except Exception:
            return ExecResult(
                ok=False,
                cancelled=False,
                answer="",
                returncode=1,
                stderr="Exception while running codex exec.",
                stdout=stdout,
                cmd=cmd,
                output_file=str(out_path),
                exception_trace=traceback.format_exc(),
                cleanup_error="",
                workdir=str(wd),
                model=model.strip(),
                prompt=prompt,
            )
        finally:
            if register_process is not None:
                register_process(None)

        answer_text = ""
        if out_path.exists():
            try:
                answer_text = out_path.read_text(encoding="utf-8")
            except Exception:
                return ExecResult(
                    ok=False,
                    cancelled=False,
                    answer="",
                    returncode=proc.returncode if proc and proc.returncode != 0 else 1,
                    stderr="Failed to read/decode --output-last-message file as UTF-8.",
                    stdout=stdout,
                    cmd=cmd,
                    output_file=str(out_path),
                    exception_trace=traceback.format_exc(),
                    cleanup_error="",
                    workdir=str(wd),
                    model=model.strip(),
                    prompt=prompt,
                )
            finally:
                try:
                    out_path.unlink(missing_ok=True)
                except Exception:
                    cleanup_error = traceback.format_exc()

        returncode = proc.returncode if proc is not None else 1
        if returncode == 0 and answer_text.strip() == "":
            return ExecResult(
                ok=False,
                cancelled=False,
                answer="",
                returncode=1,
                stderr="codex exec returned exit=0 but produced an empty last-message output (treated as failure).",
                stdout=stdout,
                cmd=cmd,
                output_file=str(out_path),
                exception_trace="",
                cleanup_error=cleanup_error,
                workdir=str(wd),
                model=model.strip(),
                prompt=prompt,
            )

        return ExecResult(
            ok=returncode == 0 and answer_text.strip() != "",
            cancelled=False,
            answer=answer_text,
            returncode=returncode,
            stderr=stderr,
            stdout=stdout,
            cmd=cmd,
            output_file=str(out_path),
            exception_trace="",
            cleanup_error=cleanup_error,
            workdir=str(wd),
            model=model.strip(),
            prompt=prompt,
        )


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title(_APP_TITLE)
        self.geometry("1080x820")
        self.minsize(960, 700)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._runner = CodexRunner()
        self._ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._busy = False
        self._cancel_requested = False
        self._active_process: subprocess.Popen[str] | None = None
        self._active_lock = threading.Lock()
        self._history_entries: list[HistoryEntry] = []

        self._build_ui()
        self._set_busy(False)
        self._log(f"[{_now_str()}] App started.")
        self._log(f"[{_now_str()}] Running preflight checks...")

        threading.Thread(target=self._preflight_worker, daemon=True).start()
        self.after(100, self._drain_queue)

    def _build_ui(self) -> None:
        self._apply_style()

        root = ttk.Frame(self, padding=12)
        root.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)
        root.rowconfigure(5, weight=1)

        top = ttk.LabelFrame(root, text="Execution Settings", padding=10)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        top.columnconfigure(3, weight=1)

        ttk.Label(top, text="Dir:").grid(row=0, column=0, sticky="w")
        self.workdir_var = tk.StringVar(value=str(_REPO_ROOT))
        self.workdir_entry = ttk.Entry(top, textvariable=self.workdir_var)
        self.workdir_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))

        self.browse_btn = ttk.Button(top, text="Browse...", command=self._on_browse)
        self.browse_btn.grid(row=0, column=2, sticky="e", padx=(0, 8))

        ttk.Label(top, text="Model:").grid(row=0, column=3, sticky="e")
        self.model_var = tk.StringVar(value="")
        self.model_entry = ttk.Entry(top, textvariable=self.model_var)
        self.model_entry.grid(row=0, column=4, sticky="ew", padx=(8, 0))

        q_frame = ttk.LabelFrame(root, text="Question (stdin prompt; PROMPT is '-')", padding=10)
        q_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        q_frame.columnconfigure(0, weight=1)

        self.question_text = tk.Text(q_frame, height=7, wrap="word", undo=True)
        self.question_text.grid(row=0, column=0, sticky="ew")

        action = ttk.Frame(root)
        action.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        action.columnconfigure(4, weight=1)

        self.send_btn = ttk.Button(action, text="Send", command=self._on_send)
        self.send_btn.grid(row=0, column=0, sticky="w")

        self.cancel_btn = ttk.Button(action, text="Cancel", command=self._on_cancel)
        self.cancel_btn.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.save_btn = ttk.Button(action, text="Save Record...", command=self._on_save)
        self.save_btn.grid(row=0, column=2, sticky="w", padx=(8, 0))

        self.clear_btn = ttk.Button(action, text="Clear Question", command=self._on_clear_question)
        self.clear_btn.grid(row=0, column=3, sticky="w", padx=(8, 0))

        self.status_var = tk.StringVar(value="Status: idle")
        self.status_label = ttk.Label(action, textvariable=self.status_var)
        self.status_label.grid(row=0, column=5, sticky="e")

        transcript = ttk.LabelFrame(root, text="Conversation / Results", padding=10)
        transcript.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        transcript.columnconfigure(0, weight=1)
        transcript.rowconfigure(0, weight=1)

        self.transcript_text = tk.Text(transcript, wrap="word", height=16)
        self.transcript_text.grid(row=0, column=0, sticky="nsew")
        self._set_text_readonly(self.transcript_text, True)

        log_frame = ttk.LabelFrame(root, text="Log / Diagnostics", padding=10)
        log_frame.grid(row=5, column=0, sticky="nsew", pady=(12, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", height=10)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self._set_text_readonly(self.log_text, True)

        self.bind("<Control-Return>", self._shortcut_send)
        self.bind("<Control-s>", self._shortcut_save)
        self.bind("<Escape>", self._shortcut_cancel)

    def _apply_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

    def _set_text_readonly(self, widget: tk.Text, readonly: bool) -> None:
        widget.configure(state=("disabled" if readonly else "normal"))

    def _log(self, line: str) -> None:
        self._set_text_readonly(self.log_text, False)
        self.log_text.insert("end", line.rstrip() + "\n")
        self.log_text.see("end")
        self._set_text_readonly(self.log_text, True)

    def _append_history(self, entry: HistoryEntry) -> None:
        self._history_entries.append(entry)
        block = self._format_history_entry(entry)

        self._set_text_readonly(self.transcript_text, False)
        if self.transcript_text.index("end-1c") != "1.0":
            self.transcript_text.insert("end", "\n" + ("-" * 72) + "\n\n")
        self.transcript_text.insert("end", block)
        self.transcript_text.see("end")
        self._set_text_readonly(self.transcript_text, True)

    def _format_history_entry(self, entry: HistoryEntry) -> str:
        lines = [
            f"[{entry.timestamp}] {entry.status}",
            f"Workdir: {entry.workdir}",
            f"Model: {entry.model or '(default)'}",
            "Question:",
            entry.prompt or "(empty)",
        ]
        if entry.answer:
            lines.extend(["", "Answer:", entry.answer.rstrip()])
        if entry.error_summary:
            lines.extend(["", "Error:", entry.error_summary.rstrip()])
        if entry.command:
            lines.extend(["", "Command:", entry.command])
        return "\n".join(lines).rstrip() + "\n"

    def _render_history_dump(self) -> str:
        header = [
            f"Codex GUI Q&A export",
            f"Exported at: {_now_str()}",
            "",
        ]
        body: list[str] = []
        for index, entry in enumerate(self._history_entries, start=1):
            body.append(f"## Entry {index}")
            body.append(self._format_history_entry(entry).rstrip())
            body.append("")
        return "\n".join(header + body).rstrip() + "\n"

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self.send_btn.configure(state="disabled")
            self.cancel_btn.configure(state="normal")
            self.save_btn.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
            self.model_entry.configure(state="disabled")
            self.workdir_entry.configure(state="disabled")
            self.clear_btn.configure(state="disabled")
            self.status_var.set("Status: running...")
        else:
            self.send_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")
            self.save_btn.configure(state=("normal" if self._history_entries else "disabled"))
            self.browse_btn.configure(state="normal")
            self.model_entry.configure(state="normal")
            self.workdir_entry.configure(state="normal")
            self.clear_btn.configure(state="normal")
            if self.status_var.get() == "Status: running...":
                self.status_var.set("Status: idle")

    def _register_active_process(self, proc: subprocess.Popen[str] | None) -> None:
        with self._active_lock:
            self._active_process = proc

    def _shortcut_send(self, _event: tk.Event[tk.Misc]) -> str:
        self._on_send()
        return "break"

    def _shortcut_save(self, _event: tk.Event[tk.Misc]) -> str:
        self._on_save()
        return "break"

    def _shortcut_cancel(self, _event: tk.Event[tk.Misc]) -> str:
        self._on_cancel()
        return "break"

    def _on_browse(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.workdir_var.get() or os.getcwd())
        if chosen:
            self.workdir_var.set(chosen)
            self._log(f"[{_now_str()}] Workdir set to: {chosen}")

    def _on_clear_question(self) -> None:
        self.question_text.delete("1.0", "end")
        self._log(f"[{_now_str()}] Question input cleared.")

    def _on_send(self) -> None:
        if self._busy:
            return

        workdir = self.workdir_var.get().strip()
        model = self.model_var.get().strip()
        prompt = self.question_text.get("1.0", "end").rstrip("\n")

        self._cancel_requested = False
        self._set_busy(True)
        self.status_var.set("Status: running...")
        self._log(
            f"[{_now_str()}] Sending question (len={len(prompt)} chars, model={model or '(default)'})"
        )

        threading.Thread(
            target=self._exec_worker,
            args=(workdir, model, prompt),
            daemon=True,
        ).start()

    def _terminate_active_process(self) -> str:
        with self._active_lock:
            proc = self._active_process

        if proc is None or proc.poll() is not None:
            return "No active Codex process to cancel."

        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
            else:
                proc.terminate()

            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            return f"Cancelled active Codex process (pid={proc.pid})."
        except Exception:
            return traceback.format_exc()

    def _on_cancel(self) -> None:
        if not self._busy:
            return
        self._cancel_requested = True
        message = self._terminate_active_process()
        self._log(f"[{_now_str()}] {message}")
        self.status_var.set("Status: cancelling...")

    def _on_save(self) -> None:
        if self._busy or not self._history_entries:
            return

        default_name = f"codex-qa-history-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        path = filedialog.asksaveasfilename(
            title="Save Codex Q&A Record",
            initialdir=self.workdir_var.get() or str(_REPO_ROOT),
            initialfile=default_name,
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if not path:
            return

        try:
            Path(path).write_text(self._render_history_dump(), encoding="utf-8")
        except Exception:
            self.status_var.set("Status: save failed")
            self._log(f"[{_now_str()}] Save FAILED: {path}")
            self._log(_shorten(traceback.format_exc(), 4000).rstrip())
            return

        self.status_var.set("Status: saved")
        self._log(f"[{_now_str()}] Record saved to: {path}")

    def _preflight_worker(self) -> None:
        self._ui_queue.put(("preflight", self._runner.preflight()))

    def _exec_worker(self, workdir: str, model: str, prompt: str) -> None:
        preflight = self._runner.preflight()
        if not preflight.ok:
            self._ui_queue.put(("exec_preflight_failed", preflight))
            return

        result = self._runner.exec_qa(
            workdir=workdir,
            prompt=prompt,
            model=model,
            register_process=self._register_active_process,
        )

        if self._cancel_requested:
            cancelled = ExecResult(
                ok=False,
                cancelled=True,
                answer="",
                returncode=result.returncode,
                stderr=result.stderr,
                stdout=result.stdout,
                cmd=result.cmd,
                output_file=result.output_file,
                exception_trace=result.exception_trace,
                cleanup_error=result.cleanup_error,
                workdir=result.workdir,
                model=result.model,
                prompt=result.prompt,
            )
            self._ui_queue.put(("exec_cancelled", cancelled))
            return

        self._ui_queue.put(("exec_done", result))

    def _record_history_from_result(self, status: str, result: ExecResult, error_summary: str) -> None:
        self._append_history(
            HistoryEntry(
                timestamp=_now_str(),
                workdir=result.workdir,
                model=result.model,
                prompt=result.prompt,
                answer=result.answer.rstrip(),
                status=status,
                error_summary=error_summary.rstrip(),
                command=(" ".join(result.cmd) if result.cmd else "(no command)"),
            )
        )

    def _handle_exec_result(self, result: ExecResult) -> None:
        cmd_str = " ".join(result.cmd) if result.cmd else "(no command)"
        self._log(f"[{_now_str()}] Command: {cmd_str}")

        if result.ok:
            self._record_history_from_result("finished (ok)", result, "")
            self._log(f"[{_now_str()}] Finished OK (exit={result.returncode}).")
            self.status_var.set("Status: finished (ok)")
        else:
            error_summary = result.stderr or result.exception_trace or "stderr: (empty)"
            self._record_history_from_result("failed", result, error_summary)
            self._log(f"[{_now_str()}] FAILED (exit={result.returncode}).")
            if result.stderr:
                self._log("stderr (excerpt):")
                self._log(_shorten(result.stderr, 4000).rstrip())
            elif result.exception_trace:
                self._log("exception trace:")
                self._log(_shorten(result.exception_trace, 8000).rstrip())
            else:
                self._log("stderr: (empty)")

            if result.stdout:
                self._log("stdout (excerpt):")
                self._log(_shorten(result.stdout, 2000).rstrip())
            self.status_var.set("Status: failed")

        if result.cleanup_error:
            self._log("cleanup error (non-fatal):")
            self._log(_shorten(result.cleanup_error, 2000).rstrip())

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "preflight":
                    pre: PreflightResult = payload  # type: ignore[assignment]
                    if pre.ok:
                        self._log(f"[{_now_str()}] Preflight OK.")
                    else:
                        self._log(f"[{_now_str()}] Preflight FAILED: {pre.summary}")
                        self._log(pre.details)
                        self.send_btn.configure(state="disabled")
                        self.status_var.set("Status: preflight failed")
                elif kind == "exec_preflight_failed":
                    pre = payload  # type: ignore[assignment]
                    self._set_busy(False)
                    self._log(f"[{_now_str()}] Preflight before send FAILED: {pre.summary}")
                    self._log(pre.details)
                    self.status_var.set("Status: preflight failed")
                    self.send_btn.configure(state="disabled")
                elif kind == "exec_cancelled":
                    result: ExecResult = payload  # type: ignore[assignment]
                    self._set_busy(False)
                    self._record_history_from_result(
                        "cancelled",
                        result,
                        result.stderr or "Cancelled by user before a final answer was accepted.",
                    )
                    self._log(f"[{_now_str()}] Request cancelled.")
                    if result.stderr:
                        self._log("stderr (excerpt):")
                        self._log(_shorten(result.stderr, 3000).rstrip())
                    self.status_var.set("Status: cancelled")
                elif kind == "exec_done":
                    result = payload  # type: ignore[assignment]
                    self._set_busy(False)
                    self._handle_exec_result(result)
                else:
                    self._log(f"[{_now_str()}] Unknown UI event: {kind!r}")
        except queue.Empty:
            pass
        finally:
            self.after(150, self._drain_queue)

    def _on_close(self) -> None:
        if self._busy:
            self._cancel_requested = True
            self._log(f"[{_now_str()}] Closing window: terminating active Codex process.")
            self._terminate_active_process()
        self.destroy()


def main() -> int:
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
