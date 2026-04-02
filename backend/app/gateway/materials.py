from __future__ import annotations

from ..errors import server_error
from ..config import get_settings
from .erp_client import ERPClient
from .k3cloud_client import K3CloudClient
from .k3cloud_material_utils import (
    material_name,
    material_number,
    material_spec,
    material_supply_type,
    material_unit_number,
)
from .models import ERPBomChildItem, ERPMaterialIssueItem


def _render_path(template: str | None, **values: str) -> str | None:
    if not template:
        return template
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


class ERPMaterialGateway:
    def __init__(self, client: ERPClient | None = None) -> None:
        self.settings = get_settings()
        self.client = client or ERPClient(self.settings)
        self.k3cloud_client = K3CloudClient(self.settings)

    def fetch_order_materials(
        self,
        order_no: str,
        *,
        mode: str | None = None,
    ) -> list[dict[str, object]]:
        if self.settings.erp_order_materials_source == "K3CLOUD":
            return self._fetch_order_materials_from_k3cloud(order_no)
        if self.settings.erp_order_materials_source != "HTTP":
            raise server_error(
                code="ERP_ORDER_MATERIALS_SOURCE_INVALID",
                message="PRODUCTION_PLAN_ERP_ORDER_MATERIALS_SOURCE is invalid.",
                details={"value": self.settings.erp_order_materials_source},
            )
        endpoint_path = _render_path(
            self.settings.erp_order_materials_path,
            production_order_no=order_no,
        )
        normalized_mode = str(mode or "").strip().lower()
        if normalized_mode and endpoint_path and "mode=real" in endpoint_path:
            endpoint_path = endpoint_path.replace("mode=real", f"mode={normalized_mode}")
        items = self.client.request_items(
            endpoint_path,
            method=self.settings.erp_order_materials_method,
            payload={"production_order_no": order_no},
        )
        normalized_items = [
            {
                "production_order_no": item.get("production_order_no") or item.get("order_no") or order_no,
                "child_material_code": item.get("child_material_code"),
                "child_material_name": item.get("child_material_name") or item.get("child_material_name_cn"),
                "spec_model": item.get("spec_model"),
                "issue_qty": item.get("issue_qty") or item.get("required_qty"),
                "supply_type_code": item.get("supply_type_code") or item.get("child_material_supply_type"),
                "supply_type_name": item.get("supply_type_name")
                or item.get("supply_type_name_cn")
                or item.get("child_material_supply_type_name_cn"),
            }
            for item in items
        ]
        return [ERPMaterialIssueItem.model_validate(item).model_dump() for item in normalized_items]

    def fetch_bom_children(self, parent_material_code: str) -> list[dict[str, object]]:
        if self.settings.erp_bom_children_source == "K3CLOUD":
            return self._fetch_bom_children_from_k3cloud(parent_material_code)
        if self.settings.erp_bom_children_source != "HTTP":
            raise server_error(
                code="ERP_BOM_CHILDREN_SOURCE_INVALID",
                message="PRODUCTION_PLAN_ERP_BOM_CHILDREN_SOURCE is invalid.",
                details={"value": self.settings.erp_bom_children_source},
            )
        items = self.client.request_items(
            _render_path(
                self.settings.erp_bom_children_path,
                parent_material_code=parent_material_code,
            ),
            method=self.settings.erp_bom_children_method,
            payload={"parent_material_code": parent_material_code},
        )
        normalized_items = [
            {
                "parent_material_code": item.get("parent_material_code") or parent_material_code,
                "child_material_code": item.get("child_material_code"),
                "child_material_name": item.get("child_material_name") or item.get("child_material_name_cn"),
                "child_specification": item.get("child_specification") or item.get("spec_model"),
                "usage_numerator": item.get("usage_numerator"),
                "usage_denominator": item.get("usage_denominator"),
                "child_unit": item.get("child_unit"),
                "supply_type_code": item.get("supply_type_code") or item.get("child_material_supply_type"),
                "supply_type_name": item.get("supply_type_name")
                or item.get("supply_type_name_cn")
                or item.get("child_material_supply_type_name_cn"),
            }
            for item in items
        ]
        return [ERPBomChildItem.model_validate(item).model_dump() for item in normalized_items]

    def _fetch_order_materials_from_k3cloud(self, order_no: str) -> list[dict[str, object]]:
        session = self.k3cloud_client.create_session()
        safe_order_no = str(order_no).strip().replace("'", "''")
        rows = self.k3cloud_client.execute_bill_query(
            session,
            form_id="PRD_PPBOM",
            field_keys="FBillNo,FMOBillNo",
            filter_string=f"FMOBillNo = '{safe_order_no}'",
            order_string="FID DESC",
            start_row=0,
            limit=1,
        )
        if not rows:
            return []
        bill_no = str(rows[0].get("FBillNo") or "").strip()
        if not bill_no:
            return []
        payload = self.k3cloud_client.view_by_number(
            session,
            form_id="PRD_PPBOM",
            number=bill_no,
        )
        entry_rows = payload.get("PPBomEntry")
        if not isinstance(entry_rows, list):
            raise server_error(
                code="K3CLOUD_ORDER_MATERIALS_INVALID_PAYLOAD",
                message="K3Cloud PRD_PPBOM view payload is missing PPBomEntry.",
                details={"order_no": order_no, "bill_no": bill_no},
            )

        normalized_items: list[dict[str, object]] = []
        for item in entry_rows:
            if not isinstance(item, dict):
                continue
            material = item.get("MaterialID")
            code = material_number(material)
            name = material_name(material)
            if not code or not name:
                continue
            supply_type_code, supply_type_name = material_supply_type(material)
            normalized_items.append(
                {
                    "production_order_no": str(item.get("MoBillNo") or order_no),
                    "child_material_code": code,
                    "child_material_name": name,
                    "spec_model": material_spec(material),
                    "issue_qty": item.get("NeedQty") or item.get("MustQty") or item.get("StdQty"),
                    "supply_type_code": supply_type_code,
                    "supply_type_name": supply_type_name,
                }
            )
        return [ERPMaterialIssueItem.model_validate(item).model_dump() for item in normalized_items]

    def _fetch_bom_children_from_k3cloud(self, parent_material_code: str) -> list[dict[str, object]]:
        session = self.k3cloud_client.create_session()
        safe_parent_material_code = str(parent_material_code).strip().replace("'", "''")
        rows = self.k3cloud_client.execute_bill_query(
            session,
            form_id="ENG_BOM",
            field_keys="FNumber,FMATERIALID.FNumber,FUseOrgId.FNumber,FDocumentStatus,FForbidStatus,FModifyDate",
            filter_string=(
                f"FMATERIALID.FNumber = '{safe_parent_material_code}' "
                "and FDocumentStatus = 'C' and FForbidStatus = 'A'"
            ),
            order_string="FModifyDate DESC,FID DESC",
            start_row=0,
            limit=1,
        )
        if not rows:
            return []
        bom_number = str(rows[0].get("FNumber") or "").strip()
        if not bom_number:
            return []
        payload = self.k3cloud_client.view_by_number(
            session,
            form_id="ENG_BOM",
            number=bom_number,
        )
        entry_rows = payload.get("TreeEntity")
        if not isinstance(entry_rows, list):
            raise server_error(
                code="K3CLOUD_BOM_CHILDREN_INVALID_PAYLOAD",
                message="K3Cloud ENG_BOM view payload is missing TreeEntity.",
                details={"parent_material_code": parent_material_code, "bom_number": bom_number},
            )

        normalized_items: list[dict[str, object]] = []
        for item in entry_rows:
            if not isinstance(item, dict):
                continue
            material = item.get("MATERIALIDCHILD")
            code = material_number(material)
            name = material_name(material)
            if not code or not name:
                continue
            supply_type_code, supply_type_name = material_supply_type(material)
            normalized_items.append(
                {
                    "parent_material_code": parent_material_code,
                    "child_material_code": code,
                    "child_material_name": name,
                    "child_specification": material_spec(material),
                    "usage_numerator": item.get("NUMERATOR"),
                    "usage_denominator": item.get("DENOMINATOR"),
                    "child_unit": material_unit_number(item.get("CHILDUNITID")),
                    "supply_type_code": supply_type_code,
                    "supply_type_name": supply_type_name,
                }
            )
        return [ERPBomChildItem.model_validate(item).model_dump() for item in normalized_items]
