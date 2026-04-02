from __future__ import annotations

from ..errors import server_error
from ..config import get_settings
from .erp_client import ERPClient
from .k3cloud_client import K3CloudClient
from .models import ERPInventorySnapshot


def _render_path(template: str | None, **values: str) -> str | None:
    if not template:
        return template
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


class ERPInventoryGateway:
    def __init__(self, client: ERPClient | None = None) -> None:
        self.settings = get_settings()
        self.client = client or ERPClient(self.settings)
        self.k3cloud_client = K3CloudClient(self.settings)

    def fetch_inventory(self, material_codes: list[str]) -> list[dict[str, object]]:
        if self.settings.erp_inventory_source == "K3CLOUD":
            return self._fetch_inventory_from_k3cloud(material_codes)
        if self.settings.erp_inventory_source != "HTTP":
            raise server_error(
                code="ERP_INVENTORY_SOURCE_INVALID",
                message="PRODUCTION_PLAN_ERP_INVENTORY_SOURCE is invalid.",
                details={"value": self.settings.erp_inventory_source},
            )
        if self.settings.erp_inventory_method == "GET":
            rows: list[dict[str, object]] = []
            for code in material_codes:
                payload = self.client.request_json(
                    _render_path(self.settings.erp_inventory_path, material_code=code),
                    method="GET",
                )
                items = payload.get("items")
                total_stock_qty = payload.get("total_stock_qty")
                if isinstance(items, list):
                    stock_qty = 0.0
                    for item in items:
                        try:
                            stock_qty += float(item.get("stock_qty") or 0)
                        except (TypeError, ValueError):
                            continue
                    rows.append(
                        {
                            "material_code": payload.get("material_code") or code,
                            "inventory_qty": stock_qty,
                            "inventory_status": "KNOWN",
                        }
                    )
                else:
                    rows.append(
                        {
                            "material_code": payload.get("material_code") or code,
                            "inventory_qty": total_stock_qty,
                            "inventory_status": "KNOWN" if total_stock_qty is not None else "UNKNOWN",
                        }
                    )
            return [ERPInventorySnapshot.model_validate(item).model_dump() for item in rows]

        items = self.client.request_items(
            self.settings.erp_inventory_path,
            method=self.settings.erp_inventory_method,
            payload={"material_codes": material_codes},
        )
        return [ERPInventorySnapshot.model_validate(item).model_dump() for item in items]

    def _fetch_inventory_from_k3cloud(self, material_codes: list[str]) -> list[dict[str, object]]:
        if not material_codes:
            return []
        session = self.k3cloud_client.create_session()
        rows: list[dict[str, object]] = []
        field_keys = "FMATERIALID.FNumber,FBaseQty,FStockId.FNumber,FStockStatusId.FNumber"
        for code in material_codes:
            safe_code = str(code or "").strip().replace("'", "''")
            items = self.k3cloud_client.execute_bill_query(
                session,
                form_id="STK_Inventory",
                field_keys=field_keys,
                filter_string=f"FMATERIALID.FNumber = '{safe_code}'",
                start_row=0,
                limit=500,
            )
            inventory_qty = 0.0
            for item in items:
                try:
                    inventory_qty += float(item.get("FBaseQty") or 0)
                except (TypeError, ValueError):
                    continue
            rows.append(
                {
                    "material_code": code,
                    "inventory_qty": inventory_qty,
                    "inventory_status": "KNOWN",
                }
            )
        return [ERPInventorySnapshot.model_validate(item).model_dump() for item in rows]
