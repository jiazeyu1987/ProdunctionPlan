from __future__ import annotations

import sqlite3
from typing import Any

from ..db import fetch_all, fetch_one


CURRENT_SCHEDULE_VERSION_NO = "CURRENT"


def _schedule_result_status_label(status: object) -> str:
    normalized = str(status or "").strip().upper()
    if normalized == "FEASIBLE":
        return "可执行建议计划"
    if normalized == "RISKY":
        return "有风险建议计划"
    if normalized == "BLOCKED":
        return "阻断"
    return normalized or "-"


class SchedulesQueryService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get_current_schedule(self) -> dict[str, Any]:
        row = fetch_one(
            self.connection,
            """
            SELECT singleton_key, strategy_code, result_status, result_summary, updated_at
            FROM current_schedule_meta
            WHERE singleton_key = 'CURRENT'
            """,
        )
        if row is None:
            return {
                "has_schedule": False,
                "schedule_id": CURRENT_SCHEDULE_VERSION_NO,
                "result_status": None,
                "result_status_label": None,
                "result_summary": "",
                "updated_at": None,
            }
        return {
            "has_schedule": True,
            "schedule_id": CURRENT_SCHEDULE_VERSION_NO,
            "result_status": row.get("result_status"),
            "result_status_label": _schedule_result_status_label(row.get("result_status")),
            "result_summary": row.get("result_summary"),
            "updated_at": row.get("updated_at"),
            "strategy_code": row.get("strategy_code"),
        }

    def list_current_schedule_tasks(self) -> dict[str, Any]:
        rows = fetch_all(
            self.connection,
            """
            SELECT
                production_order_no,
                process_code,
                process_name_cn,
                workshop_code,
                line_code,
                calendar_date,
                shift_code,
                plan_qty,
                plan_start_time
            FROM current_schedule_tasks
            ORDER BY task_no ASC
            """,
        )
        return {
            "items": [
                {
                    "order_no": row["production_order_no"],
                    "process_code": row["process_code"],
                    "process_name_cn": row.get("process_name_cn") or row["process_code"],
                    "workshop_code": row.get("workshop_code"),
                    "line_code": row.get("line_code"),
                    "calendar_date": row["calendar_date"],
                    "shift_code": row["shift_code"],
                    "plan_qty": row["plan_qty"],
                    "plan_start_time": row.get("plan_start_time"),
                }
                for row in rows
            ]
        }

    def list_schedule_snapshots(self) -> dict[str, Any]:
        rows = fetch_all(
            self.connection,
            """
            SELECT snapshot_id, snapshot_name, strategy_code, created_at, result_status, result_summary
            FROM schedule_snapshots
            ORDER BY created_at DESC, snapshot_id DESC
            """,
        )
        return {
            "items": [
                {
                    "snapshot_id": str(row.get("snapshot_id") or "").strip(),
                    "snapshot_name": str(row.get("snapshot_name") or "").strip(),
                    "created_at": row.get("created_at"),
                    "result_status": row.get("result_status"),
                    "result_status_label": _schedule_result_status_label(row.get("result_status")),
                    "result_summary": row.get("result_summary"),
                    "strategy_code": row.get("strategy_code"),
                }
                for row in rows
                if str(row.get("snapshot_id") or "").strip()
            ]
        }
