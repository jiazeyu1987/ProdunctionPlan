from __future__ import annotations

from typing import Any

from ..config import Settings
from ..errors import server_error
from .k3cloud_client import K3CloudClient
from .models import ERPProductionOrder

def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_date_text(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    if "T" in text:
        return text.split("T", 1)[0]
    if " " in text:
        return text.split(" ", 1)[0]
    return text


def _to_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise server_error(
            code="K3CLOUD_ORDER_QTY_INVALID",
            message="K3Cloud returned a non-numeric production quantity.",
            details={"value": value},
        ) from exc


class K3CloudERPOrderGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = K3CloudClient(settings)

    def fetch_orders(
        self,
        *,
        material_code: str | None = None,
        keyword: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        self._validate_settings()
        filter_string = self._build_filter_string(material_code=material_code, keyword=keyword)
        session = self.client.create_session()
        rows = self.client.execute_bill_query(
            session,
            form_id=str(self.settings.erp_k3cloud_orders_form_id),
            field_keys=str(self.settings.erp_k3cloud_orders_field_keys),
            filter_string=filter_string,
            order_string=self.settings.erp_k3cloud_orders_order_string or "FID DESC",
            start_row=0,
            limit=limit or self.settings.erp_k3cloud_orders_limit,
        )
        normalized_rows = [self._normalize_row(row) for row in rows]
        return [
            ERPProductionOrder.model_validate(item).model_dump()
            for item in normalized_rows
            if item["production_order_no"] and item["material_code"]
        ]

    def _build_filter_string(
        self,
        *,
        material_code: str | None,
        keyword: str | None,
    ) -> str | None:
        parts: list[str] = []
        normalized_material_code = _normalize_text(material_code)
        normalized_keyword = _normalize_text(keyword)
        if normalized_material_code:
            safe_material = normalized_material_code.replace("'", "''")
            parts.append(
                f"{self.settings.erp_k3cloud_orders_material_field} = '{safe_material}'"
            )
        if normalized_keyword:
            safe_keyword = normalized_keyword.replace("'", "''")
            parts.append(
                f"{self.settings.erp_k3cloud_orders_name_field} like '%{safe_keyword}%'"
            )
        if not parts:
            return None
        return " and ".join(parts)

    def _validate_settings(self) -> None:
        self.client.validate_base_settings()
        required = {
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_FORM_ID": self.settings.erp_k3cloud_orders_form_id,
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_FIELD_KEYS": self.settings.erp_k3cloud_orders_field_keys,
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_BILL_NO_FIELD": self.settings.erp_k3cloud_orders_bill_no_field,
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_MATERIAL_FIELD": self.settings.erp_k3cloud_orders_material_field,
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_NAME_FIELD": self.settings.erp_k3cloud_orders_name_field,
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_QTY_FIELD": self.settings.erp_k3cloud_orders_qty_field,
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_STATUS_FIELD": self.settings.erp_k3cloud_orders_status_field,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise server_error(
                code="K3CLOUD_CONFIG_MISSING",
                message="K3Cloud ERP order import is not fully configured.",
                details={"missing_env": missing},
            )

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, object]:
        return {
            "production_order_no": _normalize_text(
                row.get(str(self.settings.erp_k3cloud_orders_bill_no_field))
            ),
            "material_code": _normalize_text(
                row.get(str(self.settings.erp_k3cloud_orders_material_field))
            ),
            "material_name": _normalize_text(
                row.get(str(self.settings.erp_k3cloud_orders_name_field))
            )
            or _normalize_text(row.get(str(self.settings.erp_k3cloud_orders_material_field)))
            or "",
            "material_specification": _normalize_text(
                row.get(str(self.settings.erp_k3cloud_orders_spec_field))
            )
            if self.settings.erp_k3cloud_orders_spec_field
            else None,
            "production_qty": _to_number(
                row.get(str(self.settings.erp_k3cloud_orders_qty_field))
            ),
            "status": _normalize_text(
                row.get(str(self.settings.erp_k3cloud_orders_status_field))
            )
            or "OPEN",
            "planned_start_date": _normalize_date_text(
                row.get(str(self.settings.erp_k3cloud_orders_start_date_field))
            )
            if self.settings.erp_k3cloud_orders_start_date_field
            else None,
            "planned_end_date": _normalize_date_text(
                row.get(str(self.settings.erp_k3cloud_orders_end_date_field))
            )
            if self.settings.erp_k3cloud_orders_end_date_field
            else None,
            "source_bill_no": _normalize_text(
                row.get(str(self.settings.erp_k3cloud_orders_source_bill_field))
            )
            if self.settings.erp_k3cloud_orders_source_bill_field
            else None,
            "material_list_no": _normalize_text(
                row.get(str(self.settings.erp_k3cloud_orders_material_list_field))
            )
            if self.settings.erp_k3cloud_orders_material_list_field
            else None,
        }
