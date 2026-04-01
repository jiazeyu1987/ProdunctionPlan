from __future__ import annotations

import sqlite3

from ..db import transaction, utc_now
from ..gateway.inventory import ERPInventoryGateway
from ..repositories.inventory import InventoryRepository
from ..repositories.materials import BomChildrenRepository, MaterialIssueRepository


class InventoryRefreshService:
    def __init__(
        self,
        *,
        connection: sqlite3.Connection,
        inventory_repository: InventoryRepository,
        material_issue_repository: MaterialIssueRepository,
        bom_children_repository: BomChildrenRepository,
        inventory_gateway: ERPInventoryGateway,
    ) -> None:
        self.connection = connection
        self.inventory_repository = inventory_repository
        self.material_issue_repository = material_issue_repository
        self.bom_children_repository = bom_children_repository
        self.inventory_gateway = inventory_gateway

    def refresh_inventory(self, material_codes: list[str]) -> dict[str, object]:
        deduplicated_codes = list(dict.fromkeys(material_codes))
        if not deduplicated_codes:
            deduplicated_codes = list(
                dict.fromkeys(
                    self.material_issue_repository.list_all_material_codes()
                    + self.bom_children_repository.list_all_material_codes()
                )
            )

        if not deduplicated_codes:
            return {
                "message": "No material codes available for inventory refresh.",
                "material_count": 0,
            }

        snapshots = self.inventory_gateway.fetch_inventory(deduplicated_codes)
        snapshot_map = {str(row["material_code"]): row for row in snapshots}
        updated_at = utc_now()
        rows_to_store: list[dict[str, object]] = []

        for material_code in deduplicated_codes:
            snapshot = snapshot_map.get(material_code)
            if snapshot is None:
                rows_to_store.append(
                    {
                        "material_code": material_code,
                        "inventory_qty": None,
                        "inventory_status": "UNKNOWN",
                        "snapshot_time": updated_at,
                        "updated_at": updated_at,
                    }
                )
            else:
                rows_to_store.append(
                    {
                        "material_code": material_code,
                        "inventory_qty": snapshot.get("inventory_qty"),
                        "inventory_status": snapshot["inventory_status"],
                        "snapshot_time": updated_at,
                        "updated_at": updated_at,
                    }
                )

        with transaction(self.connection):
            self.inventory_repository.upsert_many(rows_to_store)

        return {
            "message": f"Refreshed inventory for {len(deduplicated_codes)} materials.",
            "material_count": len(deduplicated_codes),
            "known_count": len(snapshots),
        }
