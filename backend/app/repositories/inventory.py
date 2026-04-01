from __future__ import annotations

import sqlite3

from ..db import fetch_all


class InventoryRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get_map(self, material_codes: list[str]) -> dict[str, dict[str, object]]:
        if not material_codes:
            return {}
        placeholders = ",".join("?" for _ in material_codes)
        rows = fetch_all(
            self.connection,
            f"""
            SELECT material_code, inventory_qty, inventory_status, snapshot_time, updated_at
            FROM inventory_cache
            WHERE material_code IN ({placeholders})
            """,
            tuple(material_codes),
        )
        return {str(row["material_code"]): row for row in rows}

    def upsert_many(self, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        self.connection.executemany(
            """
            INSERT INTO inventory_cache (
                material_code,
                inventory_qty,
                inventory_status,
                snapshot_time,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(material_code) DO UPDATE SET
                inventory_qty = excluded.inventory_qty,
                inventory_status = excluded.inventory_status,
                snapshot_time = excluded.snapshot_time,
                updated_at = excluded.updated_at
            """,
            [
                (
                    row["material_code"],
                    row.get("inventory_qty"),
                    row["inventory_status"],
                    row["snapshot_time"],
                    row["updated_at"],
                )
                for row in rows
            ],
        )
