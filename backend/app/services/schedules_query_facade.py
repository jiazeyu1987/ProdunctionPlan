from __future__ import annotations

from typing import Any

from .schedules_query_service import SchedulesQueryService


class SchedulesQueryFacade:
    def __init__(self, query_service: SchedulesQueryService) -> None:
        self.query_service = query_service

    def get_current_schedule(self) -> dict[str, Any]:
        return self.query_service.get_current_schedule()

    def list_current_schedule_tasks(self) -> dict[str, Any]:
        return self.query_service.list_current_schedule_tasks()

    def list_schedule_snapshots(self) -> dict[str, Any]:
        return self.query_service.list_schedule_snapshots()
