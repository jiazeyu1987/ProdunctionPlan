from __future__ import annotations

from ..config import get_settings
from ..errors import server_error
from .erp_client import ERPClient
from .k3cloud_orders import K3CloudERPOrderGateway
from .models import ERPProductionOrder


class ERPOrderGateway:
    def __init__(self, client: ERPClient | None = None) -> None:
        self.settings = get_settings()
        self.client = client or ERPClient(self.settings)
        self.k3cloud_gateway = K3CloudERPOrderGateway(self.settings)

    def fetch_orders(
        self,
        *,
        material_code: str | None = None,
        keyword: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        if self.settings.erp_orders_source == "K3CLOUD":
            return self.k3cloud_gateway.fetch_orders(
                material_code=material_code,
                keyword=keyword,
                limit=limit,
            )
        if self.settings.erp_orders_source != "HTTP_LIST":
            raise server_error(
                code="ERP_ORDERS_SOURCE_INVALID",
                message="PRODUCTION_PLAN_ERP_ORDERS_SOURCE is invalid.",
                details={"value": self.settings.erp_orders_source},
            )
        items = self.client.request_items(
            self.settings.erp_orders_path,
            method=self.settings.erp_orders_method,
            payload={},
        )
        normalized_items = [
            {
                "production_order_no": item.get("production_order_no") or item.get("order_no"),
                "material_code": item.get("material_code") or item.get("product_code"),
                "material_name": item.get("material_name")
                or item.get("product_name_cn")
                or item.get("product_name"),
                "material_specification": item.get("material_specification") or item.get("spec_model"),
                "production_qty": item.get("production_qty") or item.get("plan_qty") or item.get("order_qty"),
                "status": item.get("status") or item.get("production_status") or "OPEN",
                "planned_start_date": item.get("planned_start_date") or item.get("expected_start_date"),
                "planned_end_date": item.get("planned_end_date") or item.get("expected_finish_date"),
                "source_bill_no": item.get("source_bill_no")
                or item.get("source_plan_order_no")
                or item.get("source_sales_order_no"),
                "material_list_no": item.get("material_list_no"),
            }
            for item in items
        ]
        return [ERPProductionOrder.model_validate(item).model_dump() for item in normalized_items]
