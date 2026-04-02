from __future__ import annotations

import sqlite3

from ..db import transaction, utc_now
from ..errors import not_found, server_error
from ..gateway.materials import ERPMaterialGateway
from ..gateway.supply import ERPSupplyGateway
from ..repositories.materials import BomChildrenRepository, MaterialIssueRepository
from ..repositories.orders import ProductionOrderRepository
from ..repositories.supply import MaterialSupplyRepository


class MaterialRefreshService:
    def __init__(
        self,
        *,
        connection: sqlite3.Connection,
        order_repository: ProductionOrderRepository,
        material_issue_repository: MaterialIssueRepository,
        bom_children_repository: BomChildrenRepository,
        supply_repository: MaterialSupplyRepository,
        material_gateway: ERPMaterialGateway,
        supply_gateway: ERPSupplyGateway,
    ) -> None:
        self.connection = connection
        self.order_repository = order_repository
        self.material_issue_repository = material_issue_repository
        self.bom_children_repository = bom_children_repository
        self.supply_repository = supply_repository
        self.material_gateway = material_gateway
        self.supply_gateway = supply_gateway

    def refresh_order_materials(self, order_no: str) -> dict[str, object]:
        if self.order_repository.get(order_no) is None:
            raise not_found(
                code="ORDER_NOT_FOUND",
                message="Order does not exist.",
                details={"order_no": order_no},
            )

        items = self.material_gateway.fetch_order_materials(order_no, mode="fast")
        material_codes = [str(item["child_material_code"]) for item in items]
        supply_rows = self.supply_gateway.fetch_material_supply(material_codes)
        supply_map = {str(row["material_code"]): row for row in supply_rows}
        updated_at = utc_now()

        rows_to_store: list[dict[str, object]] = []
        for index, item in enumerate(items):
            material_code = str(item["child_material_code"])
            supply_row = supply_map.get(material_code, {})
            supply_type_code = item.get("supply_type_code") or supply_row.get("supply_type_code")
            supply_type_name = item.get("supply_type_name") or supply_row.get("supply_type_name")
            if not supply_type_code or not supply_type_name:
                raise server_error(
                    code="SUPPLY_TYPE_MISSING",
                    message="Supply type is missing in ERP refresh result.",
                    details={"material_code": material_code},
                )

            rows_to_store.append(
                {
                    "production_order_no": order_no,
                    "child_material_code": material_code,
                    "child_material_name": item["child_material_name"],
                    "spec_model": item.get("spec_model"),
                    "issue_qty": item.get("issue_qty"),
                    "supply_type_code": supply_type_code,
                    "supply_type_name": supply_type_name,
                    "inventory_qty": None,
                    "inventory_status": "UNKNOWN",
                    "usage_numerator": None,
                    "usage_denominator": None,
                    "child_unit": None,
                    "expandable": supply_type_code == "SELF_MADE",
                    "display_order": index,
                    "updated_at": updated_at,
                }
            )

        normalized_supply_rows = [
            {
                "material_code": str(row["material_code"]),
                "supply_type_code": row["supply_type_code"],
                "supply_type_name": row["supply_type_name"],
                "snapshot_time": updated_at,
                "updated_at": updated_at,
            }
            for row in supply_rows
        ]

        with transaction(self.connection):
            self.supply_repository.upsert_many(normalized_supply_rows)
            self.material_issue_repository.replace_for_order(order_no, rows_to_store)

        return {
            "message": f"Refreshed {len(rows_to_store)} root material rows.",
            "order_no": order_no,
            "row_count": len(rows_to_store),
        }

    def refresh_self_made_materials(
        self,
        order_no: str,
        parent_material_codes: list[str],
    ) -> dict[str, object]:
        if self.order_repository.get(order_no) is None:
            raise not_found(
                code="ORDER_NOT_FOUND",
                message="Order does not exist.",
                details={"order_no": order_no},
            )

        unique_parent_codes = list(dict.fromkeys(parent_material_codes))
        updated_at = utc_now()
        supply_accumulator: dict[str, dict[str, object]] = {}
        rows_by_parent: dict[str, list[dict[str, object]]] = {}

        for parent_code in unique_parent_codes:
            children = self.material_gateway.fetch_bom_children(parent_code)
            child_codes = [str(item["child_material_code"]) for item in children]
            supply_rows = self.supply_gateway.fetch_material_supply(child_codes)
            supply_map = {str(row["material_code"]): row for row in supply_rows}
            for row in supply_rows:
                supply_accumulator[str(row["material_code"])] = {
                    "material_code": str(row["material_code"]),
                    "supply_type_code": row["supply_type_code"],
                    "supply_type_name": row["supply_type_name"],
                    "snapshot_time": updated_at,
                    "updated_at": updated_at,
                }

            stored_rows: list[dict[str, object]] = []
            for index, item in enumerate(children):
                material_code = str(item["child_material_code"])
                supply_row = supply_map.get(material_code, {})
                supply_type_code = item.get("supply_type_code") or supply_row.get("supply_type_code")
                supply_type_name = item.get("supply_type_name") or supply_row.get("supply_type_name")
                if not supply_type_code or not supply_type_name:
                    raise server_error(
                        code="SUPPLY_TYPE_MISSING",
                        message="Supply type is missing in ERP BOM refresh result.",
                        details={"material_code": material_code},
                    )

                stored_rows.append(
                    {
                        "parent_material_code": parent_code,
                        "child_material_code": material_code,
                        "child_material_name": item["child_material_name"],
                        "child_specification": item.get("child_specification"),
                        "usage_numerator": item.get("usage_numerator"),
                        "usage_denominator": item.get("usage_denominator"),
                        "child_unit": item.get("child_unit"),
                        "supply_type_code": supply_type_code,
                        "supply_type_name": supply_type_name,
                        "inventory_qty": None,
                        "inventory_status": "UNKNOWN",
                        "expandable": supply_type_code == "SELF_MADE",
                        "display_order": index,
                        "updated_at": updated_at,
                    }
                )
            rows_by_parent[parent_code] = stored_rows

        with transaction(self.connection):
            self.supply_repository.upsert_many(list(supply_accumulator.values()))
            for parent_code, rows in rows_by_parent.items():
                self.bom_children_repository.replace_for_parent(parent_code, rows)

        return {
            "message": f"Refreshed {len(unique_parent_codes)} self-made parent nodes.",
            "order_no": order_no,
            "parent_count": len(unique_parent_codes),
            "row_count": sum(len(rows) for rows in rows_by_parent.values()),
        }
