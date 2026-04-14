from __future__ import annotations

from typing import Any

from ..config import Settings
from ..errors import server_error
from .k3cloud_client import K3CloudClient
from .models import ERPProductionOrder, ERPProductionOrderSyncRecord
from .order_material_filters import (
    ALLOWED_ORDER_MATERIAL_CODE_PREFIXES,
    is_allowed_order_material_code,
)


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
        rows = self._execute_bill_query(
            session,
            filter_string=filter_string,
            start_row=0,
            limit=limit or self.settings.erp_k3cloud_orders_limit,
        )
        normalized_rows = [self._normalize_order_row(row) for row in rows]
        return [
            ERPProductionOrder.model_validate(item).model_dump()
            for item in normalized_rows
            if item["production_order_no"]
            and item["material_code"]
            and is_allowed_order_material_code(item["material_code"])
        ]

    def fetch_sync_orders(self) -> list[dict[str, object]]:
        business_status_field = self._validate_sync_settings()
        page_size = self._resolve_page_size(self.settings.erp_k3cloud_orders_limit)
        session = self.client.create_session()
        start_row = 0
        normalized_rows: list[dict[str, object]] = []

        while True:
            rows = self._execute_bill_query(
                session,
                filter_string=self._build_allowed_material_prefix_filter(),
                start_row=start_row,
                limit=page_size,
            )
            normalized_rows.extend(
                self._normalize_sync_row(row, business_status_field=business_status_field)
                for row in rows
            )
            if len(rows) < page_size:
                break
            start_row += page_size

        return [
            ERPProductionOrderSyncRecord.model_validate(item).model_dump()
            for item in normalized_rows
            if item["production_order_no"]
            and item["material_code"]
            and is_allowed_order_material_code(item["material_code"])
        ]

    def _build_filter_string(
        self,
        *,
        material_code: str | None,
        keyword: str | None,
    ) -> str | None:
        parts: list[str] = [self._build_allowed_material_prefix_filter()]
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

    def _build_allowed_material_prefix_filter(self) -> str:
        material_field = str(self.settings.erp_k3cloud_orders_material_field)
        parts = [
            f"{material_field} like '{prefix}%'"
            for prefix in ALLOWED_ORDER_MATERIAL_CODE_PREFIXES
        ]
        return f"({' or '.join(parts)})"

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

    def _validate_sync_settings(self) -> str:
        self._validate_settings()
        business_status_field = _normalize_text(
            self.settings.erp_orders_business_status_field
        )
        if not business_status_field:
            raise server_error(
                code="ERP_SYNC_BUSINESS_STATUS_FIELD_MISSING",
                message="未配置 ERP 生产订单业务状态字段，无法执行 ERP 全量同步。",
            )
        if business_status_field not in self._field_keys_set():
            raise server_error(
                code="ERP_SYNC_BUSINESS_STATUS_FIELD_NOT_INCLUDED",
                message="ERP 业务状态字段未包含在 K3Cloud 订单查询字段中，无法执行 ERP 全量同步。",
                details={"field": business_status_field},
            )
        return business_status_field

    def _field_keys_set(self) -> set[str]:
        return {
            field.strip()
            for field in str(self.settings.erp_k3cloud_orders_field_keys or "").split(",")
            if field.strip()
        }

    def _resolve_page_size(self, value: int | None) -> int:
        try:
            page_size = int(value or 0)
        except (TypeError, ValueError):
            page_size = 0
        return page_size if page_size > 0 else 200

    def _execute_bill_query(
        self,
        session: Any,
        *,
        filter_string: str | None,
        start_row: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        return self.client.execute_bill_query(
            session,
            form_id=str(self.settings.erp_k3cloud_orders_form_id),
            field_keys=str(self.settings.erp_k3cloud_orders_field_keys),
            filter_string=filter_string,
            order_string=self.settings.erp_k3cloud_orders_order_string or "FID DESC",
            start_row=start_row,
            limit=self._resolve_page_size(limit),
        )

    def _normalize_order_row(self, row: dict[str, Any]) -> dict[str, object]:
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

    def _normalize_sync_row(
        self,
        row: dict[str, Any],
        *,
        business_status_field: str,
    ) -> dict[str, object]:
        if business_status_field not in row:
            raise server_error(
                code="ERP_SYNC_BUSINESS_STATUS_FIELD_UNAVAILABLE",
                message="K3Cloud 返回结果缺少配置的业务状态字段，无法执行 ERP 全量同步。",
                details={"field": business_status_field},
            )
        normalized = self._normalize_order_row(row)
        normalized["business_status"] = _normalize_text(row.get(business_status_field))
        return normalized
