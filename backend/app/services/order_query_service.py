from __future__ import annotations

from ..errors import not_found
from ..repositories.orders import ProductionOrderRepository
from .final_process_metrics import build_order_final_process_metrics


class OrderQueryService:
    def __init__(self, repository: ProductionOrderRepository) -> None:
        self.repository = repository

    def list_orders(
        self,
        *,
        keyword: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, object]], int]:
        items, total = self.repository.list(
            keyword=keyword,
            status=status,
            page=page,
            page_size=page_size,
        )
        metrics_by_order = build_order_final_process_metrics(
            self.repository.connection,
            items,
        )
        enriched_items = [
            self._with_final_process_metrics(item, metrics_by_order)
            for item in items
        ]
        return enriched_items, total

    def get_order(self, order_no: str) -> dict[str, object]:
        item = self.repository.get(order_no)
        if item is None:
            raise not_found(
                code="ORDER_NOT_FOUND",
                message="Order does not exist.",
                details={"order_no": order_no},
            )
        metrics_by_order = build_order_final_process_metrics(
            self.repository.connection,
            [item],
        )
        return self._with_final_process_metrics(item, metrics_by_order)

    def _with_final_process_metrics(
        self,
        item: dict[str, object],
        metrics_by_order: dict[str, dict[str, object]],
    ) -> dict[str, object]:
        order_no = str(item.get("production_order_no") or "").strip()
        metrics = metrics_by_order.get(order_no) or {}
        return {
            **item,
            "final_process_code": metrics.get("final_process_code"),
            "final_process_name_cn": metrics.get("final_process_name_cn"),
            "final_process_completed_qty": metrics.get("final_process_completed_qty", 0),
            "final_process_eta_date": metrics.get("final_process_eta_date"),
        }
