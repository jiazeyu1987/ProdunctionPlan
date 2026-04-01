from __future__ import annotations

from ..repositories.orders import ProductionOrderRepository
from ..repositories.reports import WorkReportRepository
from .order_query_service import OrderQueryService


class ReportQueryService:
    def __init__(
        self,
        *,
        order_repository: ProductionOrderRepository,
        report_repository: WorkReportRepository,
    ) -> None:
        self.order_service = OrderQueryService(order_repository)
        self.report_repository = report_repository

    def list_reports(self, order_no: str) -> list[dict[str, object]]:
        self.order_service.get_order(order_no)
        return self.report_repository.list_by_order(order_no)
