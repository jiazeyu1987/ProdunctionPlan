from __future__ import annotations

from typing import Any

from .dashboard_query_service import DashboardQueryService


class DashboardQueryFacade:
    def __init__(self, query_service: DashboardQueryService) -> None:
        self.query_service = query_service

    def get_scheduler_dashboard(
        self,
        *,
        start_date: str,
        end_date: str,
        top_n: int = 8,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.query_service.get_scheduler_dashboard(
            start_date=start_date,
            end_date=end_date,
            top_n=top_n,
            current_user=current_user,
        )
