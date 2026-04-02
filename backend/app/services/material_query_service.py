from __future__ import annotations

from ..errors import not_found, server_error
from ..repositories.inventory import InventoryRepository
from ..repositories.materials import BomChildrenRepository, MaterialIssueRepository
from ..repositories.orders import ProductionOrderRepository
from ..repositories.supply import MaterialSupplyRepository


class MaterialQueryService:
    def __init__(
        self,
        *,
        order_repository: ProductionOrderRepository,
        material_issue_repository: MaterialIssueRepository,
        bom_children_repository: BomChildrenRepository,
        inventory_repository: InventoryRepository,
        supply_repository: MaterialSupplyRepository,
    ) -> None:
        self.order_repository = order_repository
        self.material_issue_repository = material_issue_repository
        self.bom_children_repository = bom_children_repository
        self.inventory_repository = inventory_repository
        self.supply_repository = supply_repository

    def list_order_materials(self, order_no: str) -> list[dict[str, object]]:
        if self.order_repository.get(order_no) is None:
            raise not_found(
                code="ORDER_NOT_FOUND",
                message="Order does not exist.",
                details={"order_no": order_no},
            )
        rows = self.material_issue_repository.list_by_order(order_no)
        return self._compose_rows(rows, row_type="ROOT")

    def list_bom_children(self, parent_material_code: str) -> list[dict[str, object]]:
        rows = self.bom_children_repository.list_by_parent(parent_material_code)
        return self._compose_rows(rows, row_type="CHILD")

    def _compose_rows(
        self,
        rows: list[dict[str, object]],
        *,
        row_type: str,
    ) -> list[dict[str, object]]:
        material_codes = [str(row["child_material_code"]) for row in rows]
        inventory_map = self.inventory_repository.get_map(material_codes)
        supply_map = self.supply_repository.get_map(material_codes)
        items: list[dict[str, object]] = []

        for row in rows:
            material_code = str(row["child_material_code"])
            inventory_row = inventory_map.get(material_code, {})
            supply_row = supply_map.get(material_code, {})
            supply_type_code = supply_row.get("supply_type_code") or row.get("supply_type_code")
            supply_type_name = supply_row.get("supply_type_name") or row.get("supply_type_name")

            if not supply_type_code or not supply_type_name:
                raise server_error(
                    code="SUPPLY_TYPE_MISSING",
                    message="Supply type cache is missing for material.",
                    details={"material_code": material_code},
                )

            inventory_status = (
                inventory_row.get("inventory_status")
                or row.get("inventory_status")
                or "UNKNOWN"
            )
            items.append(
                {
                    "row_type": row_type,
                    "production_order_no": row.get("production_order_no"),
                    "parent_material_code": row.get("parent_material_code"),
                    "child_material_code": material_code,
                    "child_material_name": row["child_material_name"],
                    "spec_model": row.get("spec_model") or row.get("child_specification"),
                    "issue_qty": row.get("issue_qty"),
                    "usage_numerator": row.get("usage_numerator"),
                    "usage_denominator": row.get("usage_denominator"),
                    "child_unit": row.get("child_unit"),
                    "supply_type_code": str(supply_type_code),
                    "supply_type_name": str(supply_type_name),
                    "child_material_supply_type": str(supply_type_code),
                    "child_material_supply_type_name_cn": str(supply_type_name),
                    "inventory_qty": inventory_row.get("inventory_qty", row.get("inventory_qty")),
                    "inventory_status": str(inventory_status),
                    "child_material_inventory_qty": inventory_row.get(
                        "inventory_qty",
                        row.get("inventory_qty"),
                    ),
                    "child_material_inventory_status": str(inventory_status),
                    "expandable": bool(row.get("expandable"))
                    or supply_type_code == "SELF_MADE",
                }
            )

        return items
