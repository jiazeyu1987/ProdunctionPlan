from __future__ import annotations

import asyncio

from .config import get_settings
from .db import managed_connection
from .errors import AppError
from .repositories.jobs import JobRepository
from .services.job_dispatcher import JobDispatcher


class JobWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._poll_interval = get_settings().worker_poll_interval_seconds

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

    def _process_next_job(self) -> bool:
        with managed_connection() as connection:
            job_repository = JobRepository(connection)
            job = job_repository.claim_next_pending()

        if job is None:
            return False

        try:
            with managed_connection() as connection:
                dispatcher = JobDispatcher(connection)
                result = dispatcher.dispatch(job)
            with managed_connection() as connection:
                JobRepository(connection).mark_succeeded(str(job["job_id"]), result)
        except AppError as exc:
            with managed_connection() as connection:
                JobRepository(connection).mark_failed(
                    str(job["job_id"]),
                    exc.code,
                    exc.message,
                )
        except Exception as exc:
            with managed_connection() as connection:
                JobRepository(connection).mark_failed(
                    str(job["job_id"]),
                    "UNEXPECTED_ERROR",
                    str(exc),
                )

        return True
