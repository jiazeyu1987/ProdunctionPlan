from __future__ import annotations

from ..errors import server_error
from ..config import get_settings
from .erp_client import ERPClient
from .k3cloud_client import K3CloudClient
from .k3cloud_material_utils import material_supply_type
from .models import ERPMaterialSupplyInfo


def _render_path(template: str | None, **values: str) -> str | None:
    if not template:
        return template
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


class ERPSupplyGateway:
    def __init__(self, client: ERPClient | None = None) -> None:
        self.settings = get_settings()
        self.client = client or ERPClient(self.settings)
        self.k3cloud_client = K3CloudClient(self.settings)

    def fetch_material_supply(self, material_codes: list[str]) -> list[dict[str, object]]:
        if not material_codes:
            return []
        if self.settings.erp_supply_source == "K3CLOUD":
            return self._fetch_supply_from_k3cloud(material_codes)
        if self.settings.erp_supply_source != "HTTP":
            raise server_error(
                code="ERP_SUPPLY_SOURCE_INVALID",
                message="PRODUCTION_PLAN_ERP_SUPPLY_SOURCE is invalid.",
                details={"value": self.settings.erp_supply_source},
            )
        if self.settings.erp_supply_method == "GET":
            rows: list[dict[str, object]] = []
            for code in material_codes:
                payload = self.client.request_json(
                    _render_path(self.settings.erp_supply_path, material_code=code),
                    method="GET",
                )
                rows.append(
                    {
                        "material_code": payload.get("material_code") or code,
                        "supply_type_code": payload.get("supply_type_code") or payload.get("supply_type"),
                        "supply_type_name": payload.get("supply_type_name") or payload.get("supply_type_name_cn"),
                    }
                )
            return [ERPMaterialSupplyInfo.model_validate(item).model_dump() for item in rows]

        items = self.client.request_items(
            self.settings.erp_supply_path,
            method=self.settings.erp_supply_method,
            payload={"material_codes": material_codes},
        )
        return [ERPMaterialSupplyInfo.model_validate(item).model_dump() for item in items]

    def _fetch_supply_from_k3cloud(self, material_codes: list[str]) -> list[dict[str, object]]:
        session = self.k3cloud_client.create_session()
        rows: list[dict[str, object]] = []
        for code in material_codes:
            number = str(code or "").strip()
            if not number:
                continue
            matched = self.k3cloud_client.view_by_number(
                session,
                form_id="BD_MATERIAL",
                number=number,
            )
            supply_type_code, supply_type_name = material_supply_type(matched)
            rows.append(
                {
                    "material_code": code,
                    "supply_type_code": supply_type_code,
                    "supply_type_name": supply_type_name,
                }
            )
        return [ERPMaterialSupplyInfo.model_validate(item).model_dump() for item in rows]
