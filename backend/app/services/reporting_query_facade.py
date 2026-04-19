from __future__ import annotations

from typing import Any

from .reporting_query_service import ReportingQueryService


class ReportingQueryFacade:
    def __init__(self, query_service: ReportingQueryService) -> None:
        self.query_service = query_service

    def list_mes_reportings(
        self,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.query_service.list_mes_reportings(
            start_time=start_time,
            end_time=end_time,
            current_user=current_user,
        )

    def list_reporting_import_files(self, *, limit: int = 50) -> dict[str, Any]:
        return self.query_service.list_reporting_import_files(limit=limit)
