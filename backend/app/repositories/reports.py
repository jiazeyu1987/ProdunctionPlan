from __future__ import annotations

import sqlite3

from ..db import fetch_all


class WorkReportRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_by_order(self, order_no: str) -> list[dict[str, object]]:
        return fetch_all(
            self.connection,
            """
            SELECT
                report_id,
                production_order_no,
                process_code,
                process_name,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                report_qty,
                report_time,
                operator_name
            FROM work_reports
            WHERE production_order_no = ?
            ORDER BY report_time DESC, report_id DESC
            """,
            (order_no,),
        )
