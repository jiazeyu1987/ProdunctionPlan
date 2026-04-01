from __future__ import annotations

from ..config import get_settings
from .erp_client import ERPClient
from .models import ERPBomChildItem, ERPMaterialIssueItem


class ERPMaterialGateway:
    def __init__(self, client: ERPClient | None = None) -> None:
        self.settings = get_settings()
        self.client = client or ERPClient(self.settings)

    def fetch_order_materials(self, order_no: str) -> list[dict[str, object]]:
        items = self.client.post_items(
            self.settings.erp_order_materials_path,
            {"production_order_no": order_no},
        )
        return [ERPMaterialIssueItem.model_validate(item).model_dump() for item in items]

    def fetch_bom_children(self, parent_material_code: str) -> list[dict[str, object]]:
        items = self.client.post_items(
            self.settings.erp_bom_children_path,
            {"parent_material_code": parent_material_code},
        )
        return [ERPBomChildItem.model_validate(item).model_dump() for item in items]
