from __future__ import annotations

import json
import shutil
import sys
import tarfile
import time
from pathlib import Path

import paramiko


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).with_name("deploy-config.json")
TEMP_DIR = ROOT / "tool" / "deploy" / "temp"

EXCLUDED_PARTS = {
    ".git",
    ".codex",
    "node_modules",
    ".next",
    "_tmp",
    "logs",
    ".logs",
    "__pycache__",
    ".pytest_cache",
}
EXCLUDED_NAMES = {
    "productionplan_deploy.tar.gz",
}


def log(message: str) -> None:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"[{now}] {message}")


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def should_exclude(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if path.name in EXCLUDED_NAMES:
        return True
    return any(part in EXCLUDED_PARTS for part in rel.parts)


def build_archive(archive_path: Path) -> None:
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as tar:
        for path in ROOT.rglob("*"):
            if should_exclude(path):
                continue
            try:
                tar.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
            except PermissionError as exc:
                raise RuntimeError(f"cannot package path due to permission error: {path}") from exc


def run_remote(ssh: paramiko.SSHClient, command: str, timeout: int = 7200) -> tuple[int, str, str]:
    _, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def require_success(step: str, code: int, out: str, err: str) -> None:
    if code == 0:
        return
    detail = (out + "\n" + err).strip()
    raise RuntimeError(f"{step} failed.\n{detail}")


def run_remote_with_retry(
    ssh: paramiko.SSHClient,
    *,
    step: str,
    command: str,
    retries: int = 10,
    delay_seconds: int = 3,
    timeout: int = 7200,
) -> tuple[int, str, str]:
    last: tuple[int, str, str] = (1, "", "")
    for attempt in range(1, retries + 1):
        code, out, err = run_remote(ssh, command, timeout=timeout)
        last = (code, out, err)
        if code == 0:
            return last
        if attempt < retries:
            log(f"{step} retry {attempt}/{retries - 1}")
            time.sleep(delay_seconds)
    return last


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    config = load_config()
    server = config["server"]
    deploy = config["deploy"]
    healthcheck = config["healthcheck"]

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = TEMP_DIR / deploy["archive_name"]

    log("Start packaging local source")
    build_archive(archive_path)
    log(f"Archive ready: {archive_path} ({archive_path.stat().st_size} bytes)")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        log(f"Connect server {server['user']}@{server['host']}:{server['port']}")
        ssh.connect(
            hostname=server["host"],
            port=int(server["port"]),
            username=server["user"],
            password=server["password"],
            timeout=30,
        )

        remote_dir = deploy["remote_dir"]
        remote_archive = f"{remote_dir}/{deploy['archive_name']}"
        remote_app_dir = f"{remote_dir}/app"
        compose_file = deploy["compose_file"]

        code, out, err = run_remote(
            ssh,
            f"mkdir -p {remote_dir} && rm -rf {remote_app_dir} && mkdir -p {remote_app_dir}",
        )
        require_success("prepare remote directory", code, out, err)

        log("Upload archive to server")
        sftp = ssh.open_sftp()
        try:
            sftp.put(str(archive_path), remote_archive)
        finally:
            sftp.close()

        commands = [
            ("extract archive", f"tar -xzf {remote_archive} -C {remote_app_dir}"),
            (
                "docker compose deploy",
                f"cd {remote_app_dir} && docker compose -f {compose_file} up -d --build --remove-orphans",
            ),
        ]

        for step, command in commands:
            log(step)
            code, out, err = run_remote(ssh, command)
            require_success(step, code, out, err)
            if out.strip():
                print(out.strip())
            if err.strip():
                print(err.strip())

        healthchecks = [
            ("backend healthcheck", f"curl -fsS {healthcheck['backend_url']}"),
            ("frontend healthcheck", f"curl -fsSI {healthcheck['frontend_url']} | head -n 5"),
        ]
        for step, command in healthchecks:
            log(step)
            code, out, err = run_remote_with_retry(
                ssh,
                step=step,
                command=command,
                retries=10,
                delay_seconds=3,
            )
            require_success(step, code, out, err)
            if out.strip():
                print(out.strip())
            if err.strip():
                print(err.strip())

        code, out, err = run_remote(
            ssh,
            "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | egrep 'productionplan|NAMES'",
        )
        require_success("list deployed containers", code, out, err)
        if out.strip():
            print(out.strip())

        log("Publish complete")
        return 0
    finally:
        ssh.close()
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
