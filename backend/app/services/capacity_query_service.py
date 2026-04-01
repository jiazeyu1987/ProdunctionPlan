from __future__ import annotations

from ..repositories.capacity import CapacityRepository
from ..repositories.orders import ProductionOrderRepository
from .order_query_service import OrderQueryService


class CapacityQueryService:
    def __init__(
        self,
        *,
        order_repository: ProductionOrderRepository,
        capacity_repository: CapacityRepository,
    ) -> None:
        self.order_service = OrderQueryService(order_repository)
        self.capacity_repository = capacity_repository

    def list_capacity(self, order_no: str) -> list[dict[str, object]]:
        self.order_service.get_order(order_no)
        return self.capacity_repository.list_by_order(order_no)
