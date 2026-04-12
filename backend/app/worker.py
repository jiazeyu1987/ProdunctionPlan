from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from time import monotonic

from .config import get_settings
from .db import managed_connection
from .errors import AppError
from .repositories.backups import BackupRepository
from .repositories.jobs import JobRepository
from .services.job_dispatcher import JobDispatcher


class JobWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._poll_interval = get_settings().worker_poll_interval_seconds
        self._auto_backup_check_interval_seconds = 60.0
        self._last_auto_backup_check_at = 0.0

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.to_thread(self._maybe_enqueue_auto_backup)
            processed = await asyncio.to_thread(self._process_next_job)
            if processed:
                continue
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._poll_interval,
                )
            except asyncio.TimeoutError:
                continue

    def _job_requires_connectionless_dispatch(self, job: dict[str, object]) -> bool:
        return str(job.get("job_type") or "").strip().upper() == "DB_BACKUP_RESTORE"

    def _mark_job_succeeded(self, job: dict[str, object], result: dict[str, object]) -> None:
        with managed_connection() as connection:
            repository = JobRepository(connection)
            if self._job_requires_connectionless_dispatch(job):
                repository.ensure_exists(job)
            repository.mark_succeeded(str(job["job_id"]), result)

    def _mark_job_failed(self, job: dict[str, object], error_code: str, error_message: str) -> None:
        with managed_connection() as connection:
            repository = JobRepository(connection)
            if self._job_requires_connectionless_dispatch(job):
                repository.ensure_exists(job)
            repository.mark_failed(str(job["job_id"]), error_code, error_message)

    def _parse_timestamp(self, value: str) -> datetime:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _maybe_enqueue_auto_backup(self) -> None:
        now_monotonic = monotonic()
        if (
            now_monotonic - self._last_auto_backup_check_at
            < self._auto_backup_check_interval_seconds
        ):
            return
        self._last_auto_backup_check_at = now_monotonic

        with managed_connection() as connection:
            backup_repository = BackupRepository(connection)
            backup_config = backup_repository.get_backup_config()
            if int(backup_config["enabled_flag"] or 0) != 1:
                return

            frequency_minutes = int(backup_config["frequency_minutes"] or 0)
            latest_auto_backup = backup_repository.get_latest_backup_record(trigger="AUTO")
            now_utc = datetime.now(timezone.utc).replace(microsecond=0)
            if latest_auto_backup is not None:
                last_created_at = self._parse_timestamp(
                    str(latest_auto_backup["created_at"])
                )
                if now_utc < last_created_at + timedelta(minutes=frequency_minutes):
                    return

            request_id = f"db-backup-auto:{now_utc.strftime('%Y%m%dT%H%M')}"
            JobRepository(connection).enqueue(
                job_type="DB_BACKUP_CREATE_AUTO",
                target_type="MASTERDATA_BACKUP",
                target_key="AUTO",
                request_id=request_id,
                payload={},
            )

    def _process_next_job(self) -> bool:
        with managed_connection() as connection:
            job_repository = JobRepository(connection)
            job = job_repository.claim_next_pending()

        if job is None:
            return False

        try:
            if self._job_requires_connectionless_dispatch(job):
                result = JobDispatcher.dispatch_without_connection(job)
            else:
                with managed_connection() as connection:
                    dispatcher = JobDispatcher(connection)
                    result = dispatcher.dispatch(job)
            self._mark_job_succeeded(job, result)
        except AppError as exc:
            self._mark_job_failed(job, exc.code, exc.message)
        except Exception as exc:
            self._mark_job_failed(job, "UNEXPECTED_ERROR", str(exc))

        return True
