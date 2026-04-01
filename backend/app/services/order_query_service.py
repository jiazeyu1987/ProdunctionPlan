from __future__ import annotations

from ..errors import not_found
from ..repositories.orders import ProductionOrderRepository


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
        return self.repository.list(
            keyword=keyword,
            status=status,
            page=page,
            page_size=page_size,
        )

    def get_order(self, order_no: str) -> dict[str, object]:
        item = self.repository.get(order_no)
        if item is None:
            raise not_found(
                code="ORDER_NOT_FOUND",
                message="Order does not exist.",
                details={"order_no": order_no},
            )
        return item
