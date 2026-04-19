from __future__ import annotations

from typing import Any

from .order_summary_query_service import OrderSummaryQueryService


class OrderSummaryQueryFacade:
    def __init__(self, query_service: OrderSummaryQueryService) -> None:
        self.query_service = query_service

    def get_order_summary(
        self,
        *,
        start_date: str,
        end_date: str,
        workshop_manager_user_id: str | None = None,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.query_service.get_order_summary(
            start_date=start_date,
            end_date=end_date,
            workshop_manager_user_id=workshop_manager_user_id,
            current_user=current_user,
        )

    def list_order_summary_workshop_managers(
        self,
        *,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.query_service.list_order_summary_workshop_managers(
            current_user=current_user,
        )
