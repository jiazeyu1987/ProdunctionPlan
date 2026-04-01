from __future__ import annotations

import sqlite3

from ..db import fetch_all


class CapacityRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_by_order(self, order_no: str) -> list[dict[str, object]]:
        return fetch_all(
            self.connection,
            """
            SELECT
                process_code,
                process_name,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                capacity_qty
            FROM capacity_bindings
            WHERE production_order_no = ?
            ORDER BY process_code, workshop_code, line_code
            """,
            (order_no,),
        )
