from __future__ import annotations

from ..config import get_settings
from .erp_client import ERPClient
from .models import ERPMaterialSupplyInfo


class ERPSupplyGateway:
    def __init__(self, client: ERPClient | None = None) -> None:
        self.settings = get_settings()
        self.client = client or ERPClient(self.settings)

    def fetch_material_supply(self, material_codes: list[str]) -> list[dict[str, object]]:
        if not material_codes:
            return []
        items = self.client.post_items(
            self.settings.erp_supply_path,
            {"material_codes": material_codes},
        )
        return [ERPMaterialSupplyInfo.model_validate(item).model_dump() for item in items]
