from __future__ import annotations

import sqlite3

from ..db import fetch_all


class MaterialIssueRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_by_order(self, order_no: str) -> list[dict[str, object]]:
        return fetch_all(
            self.connection,
            """
            SELECT
                production_order_no,
                child_material_code,
                child_material_name,
                spec_model,
                issue_qty,
                supply_type_code,
                supply_type_name,
                inventory_qty,
                inventory_status,
                usage_numerator,
                usage_denominator,
                child_unit,
                expandable,
                display_order
            FROM material_issue_items
            WHERE production_order_no = ?
            ORDER BY display_order, child_material_code
            """,
            (order_no,),
        )

    def replace_for_order(self, order_no: str, rows: list[dict[str, object]]) -> None:
        self.connection.execute(
            "DELETE FROM material_issue_items WHERE production_order_no = ?",
            (order_no,),
        )
        if not rows:
            return
        self.connection.executemany(
            """
            INSERT INTO material_issue_items (
                production_order_no,
                child_material_code,
                child_material_name,
                spec_model,
                issue_qty,
                supply_type_code,
                supply_type_name,
                inventory_qty,
                inventory_status,
                usage_numerator,
                usage_denominator,
                child_unit,
                expandable,
                display_order,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["production_order_no"],
                    row["child_material_code"],
                    row["child_material_name"],
                    row.get("spec_model"),
                    row.get("issue_qty"),
                    row.get("supply_type_code"),
                    row.get("supply_type_name"),
                    row.get("inventory_qty"),
                    row["inventory_status"],
                    row.get("usage_numerator"),
                    row.get("usage_denominator"),
                    row.get("child_unit"),
                    int(bool(row.get("expandable"))),
                    row.get("display_order", 0),
                    row["updated_at"],
                )
                for row in rows
            ],
        )

    def list_all_material_codes(self) -> list[str]:
        rows = fetch_all(
            self.connection,
            "SELECT DISTINCT child_material_code FROM material_issue_items",
        )
        return [str(row["child_material_code"]) for row in rows]


class BomChildrenRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_by_parent(self, parent_material_code: str) -> list[dict[str, object]]:
        return fetch_all(
            self.connection,
            """
            SELECT
                parent_material_code,
                child_material_code,
                child_material_name,
                child_specification,
                usage_numerator,
                usage_denominator,
                child_unit,
                supply_type_code,
                supply_type_name,
                inventory_qty,
                inventory_status,
                expandable,
                display_order
            FROM bom_children
            WHERE parent_material_code = ?
            ORDER BY display_order, child_material_code
            """,
            (parent_material_code,),
        )

    def replace_for_parent(
        self,
        parent_material_code: str,
        rows: list[dict[str, object]],
    ) -> None:
        self.connection.execute(
            "DELETE FROM bom_children WHERE parent_material_code = ?",
            (parent_material_code,),
        )
        if not rows:
            return
        self.connection.executemany(
            """
            INSERT INTO bom_children (
                parent_material_code,
                child_material_code,
                child_material_name,
                child_specification,
                usage_numerator,
                usage_denominator,
                child_unit,
                supply_type_code,
                supply_type_name,
                inventory_qty,
                inventory_status,
                expandable,
                display_order,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["parent_material_code"],
                    row["child_material_code"],
                    row["child_material_name"],
                    row.get("child_specification"),
                    row.get("usage_numerator"),
                    row.get("usage_denominator"),
                    row.get("child_unit"),
                    row.get("supply_type_code"),
                    row.get("supply_type_name"),
                    row.get("inventory_qty"),
                    row["inventory_status"],
                    int(bool(row.get("expandable"))),
                    row.get("display_order", 0),
                    row["updated_at"],
                )
                for row in rows
            ],
        )

    def list_all_material_codes(self) -> list[str]:
        rows = fetch_all(
            self.connection,
            "SELECT DISTINCT child_material_code FROM bom_children",
        )
        return [str(row["child_material_code"]) for row in rows]
