from __future__ import annotations

import sqlite3

from ..db import fetch_all, fetch_one


class ProductionOrderRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list(
        self,
        *,
        keyword: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, object]], int]:
        where_clauses: list[str] = []
        parameters: list[object] = []

        if keyword:
            fuzzy = f"%{keyword.strip()}%"
            where_clauses.append(
                """
                (
                    production_order_no LIKE ?
                    OR material_code LIKE ?
                    OR material_name LIKE ?
                    OR material_specification LIKE ?
                )
                """
            )
            parameters.extend([fuzzy, fuzzy, fuzzy, fuzzy])

        if status:
            where_clauses.append("status = ?")
            parameters.append(status.strip())

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        total_row = fetch_one(
            self.connection,
            f"SELECT COUNT(1) AS total FROM production_orders {where_sql}",
            tuple(parameters),
        )
        total = int(total_row["total"]) if total_row else 0

        offset = (page - 1) * page_size
        items = fetch_all(
            self.connection,
            f"""
            SELECT
                production_order_no,
                material_code,
                material_name,
                material_specification,
                production_qty,
                status,
                material_list_no,
                planned_start_date,
                planned_end_date,
                source_bill_no
            FROM production_orders
            {where_sql}
            ORDER BY updated_at DESC, production_order_no DESC
            LIMIT ? OFFSET ?
            """,
            tuple(parameters + [page_size, offset]),
        )
        return items, total

    def get(self, order_no: str) -> dict[str, object] | None:
        return fetch_one(
            self.connection,
            """
            SELECT
                production_order_no,
                material_code,
                material_name,
                material_specification,
                production_qty,
                status,
                material_list_no,
                planned_start_date,
                planned_end_date,
                source_bill_no
            FROM production_orders
            WHERE production_order_no = ?
            """,
            (order_no,),
        )

    def replace_all(self, rows: list[dict[str, object]]) -> None:
        if rows:
            order_nos = [str(row["production_order_no"]) for row in rows]
            placeholders = ",".join("?" for _ in order_nos)
            self.connection.execute(
                f"""
                DELETE FROM production_orders
                WHERE production_order_no NOT IN ({placeholders})
                """,
                tuple(order_nos),
            )
        else:
            self.connection.execute("DELETE FROM production_orders")

        self.connection.executemany(
            """
            INSERT INTO production_orders (
                production_order_no,
                material_code,
                material_name,
                material_specification,
                production_qty,
                status,
                planned_start_date,
                planned_end_date,
                source_bill_no,
                material_list_no,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(production_order_no) DO UPDATE SET
                material_code = excluded.material_code,
                material_name = excluded.material_name,
                material_specification = excluded.material_specification,
                production_qty = excluded.production_qty,
                status = excluded.status,
                planned_start_date = excluded.planned_start_date,
                planned_end_date = excluded.planned_end_date,
                source_bill_no = excluded.source_bill_no,
                material_list_no = excluded.material_list_no,
                updated_at = excluded.updated_at
            """,
            [
                (
                    row["production_order_no"],
                    row["material_code"],
                    row["material_name"],
                    row.get("material_specification"),
                    row["production_qty"],
                    row["status"],
                    row.get("planned_start_date"),
                    row.get("planned_end_date"),
                    row.get("source_bill_no"),
                    row.get("material_list_no"),
                    row["updated_at"],
                )
                for row in rows
            ],
        )
