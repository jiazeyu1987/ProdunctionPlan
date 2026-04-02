from __future__ import annotations

from ..config import get_settings
from .erp_client import ERPClient
from .models import UpstreamEquipmentProcessCapability, UpstreamProcessRoute


class UpstreamMasterdataGateway:
    def __init__(self, client: ERPClient | None = None) -> None:
        self.settings = get_settings()
        self.client = client or ERPClient(self.settings)

    def fetch_process_routes(self) -> list[dict[str, object]]:
        items = self.client.request_items(
            self.settings.masterdata_process_routes_path,
            method=self.settings.masterdata_process_routes_method,
            payload={},
        )
        normalized_items = [
            {
                "route_no": item.get("route_no"),
                "product_code": item.get("product_code"),
                "product_name_cn": item.get("product_name_cn"),
                "route_name_cn": item.get("route_name_cn"),
                "sequence_no": item.get("sequence_no"),
                "process_code": item.get("process_code"),
                "process_name_cn": item.get("process_name_cn"),
                "dependency_type": item.get("dependency_type"),
                "capacity_per_shift": item.get("capacity_per_shift"),
                "required_manpower_per_group": item.get("required_manpower_per_group"),
                "required_equipment_count": item.get("required_equipment_count"),
                "enabled_flag": item.get("enabled_flag"),
            }
            for item in items
        ]
        return [
            UpstreamProcessRoute.model_validate(item).model_dump()
            for item in normalized_items
        ]

    def fetch_equipment_process_capabilities(self) -> list[dict[str, object]]:
        items = self.client.request_items(
            self.settings.masterdata_equipment_capabilities_path,
            method=self.settings.masterdata_equipment_capabilities_method,
            payload={},
        )
        normalized_items = [
            {
                "equipment_code": item.get("equipment_code"),
                "process_code": item.get("process_code"),
                "company_code": item.get("company_code"),
                "line_code": item.get("line_code"),
                "line_name": item.get("line_name"),
                "workshop_code": item.get("workshop_code"),
                "enabled_flag": item.get("enabled_flag"),
                "capacity_factor": item.get("capacity_factor"),
                "process_name_cn": item.get("process_name_cn"),
            }
            for item in items
        ]
        return [
            UpstreamEquipmentProcessCapability.model_validate(item).model_dump()
            for item in normalized_items
        ]
