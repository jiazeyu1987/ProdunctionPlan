from __future__ import annotations

from typing import Any

from .masterdata_query_service import MasterdataQueryService


class MasterdataQueryFacade:
    def __init__(self, query_service: MasterdataQueryService) -> None:
        self.query_service = query_service

    def get_masterdata_config(self) -> dict[str, Any]:
        return self.query_service.get_masterdata_config()

    def get_schedule_calendar_rules(self) -> dict[str, Any]:
        return self.query_service.get_schedule_calendar_rules()

    def list_process_routes(self) -> dict[str, Any]:
        return self.query_service.list_process_routes()

    def list_line_daily_capacity(
        self,
        calendar_date: str,
        *,
        workshop_code: str | None = None,
        line_code: str | None = None,
        process_code: str | None = None,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.query_service.list_line_daily_capacity(
            calendar_date,
            workshop_code=workshop_code,
            line_code=line_code,
            process_code=process_code,
            current_user=current_user,
        )

    def list_line_daily_capacity_audits(
        self,
        calendar_date: str,
        *,
        workshop_code: str | None = None,
        line_code: str | None = None,
        process_code: str | None = None,
        operator_keyword: str | None = None,
        changed_only: bool = False,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.query_service.list_line_daily_capacity_audits(
            calendar_date,
            workshop_code=workshop_code,
            line_code=line_code,
            process_code=process_code,
            operator_keyword=operator_keyword,
            changed_only=changed_only,
            current_user=current_user,
        )
