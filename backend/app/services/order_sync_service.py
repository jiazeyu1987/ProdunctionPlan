from __future__ import annotations

import sqlite3

from ..db import transaction, utc_now
from ..gateway.orders import ERPOrderGateway
from ..repositories.orders import ProductionOrderRepository


class OrderSyncService:
    def __init__(
        self,
        *,
        connection: sqlite3.Connection,
        order_repository: ProductionOrderRepository,
        order_gateway: ERPOrderGateway,
    ) -> None:
        self.connection = connection
        self.order_repository = order_repository
        self.order_gateway = order_gateway

    def sync_orders(self) -> dict[str, object]:
        items = self.order_gateway.fetch_orders()
        updated_at = utc_now()
        rows_to_store = [
            {
                "production_order_no": item["production_order_no"],
                "material_code": item["material_code"],
                "material_name": item["material_name"],
                "material_specification": item.get("material_specification"),
                "production_qty": item["production_qty"],
                "status": item["status"],
                "planned_start_date": item.get("planned_start_date"),
                "planned_end_date": item.get("planned_end_date"),
                "source_bill_no": item.get("source_bill_no"),
                "material_list_no": item.get("material_list_no"),
                "updated_at": updated_at,
            }
            for item in items
        ]

        with transaction(self.connection):
            self.order_repository.replace_all(rows_to_store)

        return {"message": f"Synchronized {len(rows_to_store)} production orders."}
