from __future__ import annotations

import sqlite3
from typing import Any

from ..db import fetch_all
from ..json_utils import loads
from .user_scope_support import resolve_manager_user_id


def _normalize_date_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        from datetime import date

        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


class ReportingQueryService:
    def __init__(self, host: Any) -> None:
        self.host = host
        self.connection = host.connection

    def list_mes_reportings(
        self,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        where_clauses: list[str] = []
        parameters: list[Any] = []
        if start_time:
            where_clauses.append("report_time >= ?")
            parameters.append(start_time)
        if end_time:
            where_clauses.append("report_time <= ?")
            parameters.append(end_time)
        manager_user_id = resolve_manager_user_id(current_user)
        if manager_user_id is not None:
            where_clauses.append(
                """
                EXISTS (
                    SELECT 1
                    FROM app_user_line_scopes scope
                    WHERE scope.user_id = ?
                      AND scope.workshop_code = work_reports.workshop_code
                      AND scope.line_code = work_reports.line_code
                )
                """
            )
            parameters.append(manager_user_id)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        rows = fetch_all(
            self.connection,
            f"""
            SELECT
                report_id,
                production_order_no,
                report_scope,
                process_code,
                process_name,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                report_qty,
                report_time,
                operator_code,
                operator_name,
                section_leader_name,
                updated_at,
                date(report_time, '+8 hours') AS report_local_date,
                daily_capacity_compare_audit_id,
                daily_capacity_compare_qty
            FROM work_reports
            {where_sql}
            ORDER BY report_time DESC, report_id DESC
            """,
            tuple(parameters),
        )
        return {
            "items": [
                {
                    "report_id": row["report_id"],
                    "order_no": row["production_order_no"],
                    "process_code": row.get("process_code"),
                    "process_name_cn": row.get("process_name") or row.get("process_code"),
                    "workshop_code": row.get("workshop_code"),
                    "workshop_name": row.get("workshop_name") or row.get("workshop_code"),
                    "line_code": row.get("line_code"),
                    "line_name": row.get("line_name") or row.get("line_code"),
                    "report_qty": row.get("report_qty"),
                    "report_time": row.get("report_time"),
                    "report_local_date": _normalize_date_text(row.get("report_local_date")),
                    "operator_code": row.get("operator_code"),
                    "operator_name_cn": row.get("operator_name") or "系统填报",
                    "section_leader_name": row.get("section_leader_name"),
                    "updated_at": row.get("updated_at"),
                    "daily_capacity_compare_audit_id": row.get("daily_capacity_compare_audit_id"),
                    "daily_capacity_compare_qty": row.get("daily_capacity_compare_qty"),
                }
                for row in rows
            ]
        }

    def list_reporting_import_files(self, *, limit: int = 50) -> dict[str, Any]:
        normalized_limit = max(1, min(200, int(limit or 50)))
        rows = fetch_all(
            self.connection,
            """
            SELECT
                file_sha256,
                source_file_name,
                file_path,
                original_file_name,
                file_size_bytes,
                sheet_names_json,
                imported_by_user_id,
                imported_by_username,
                imported_by_display_name,
                total_row_count,
                imported_count,
                skipped_existing_count,
                failed_count,
                created_missing_order_count,
                created_at,
                last_imported_at
            FROM reporting_import_files
            ORDER BY last_imported_at DESC, file_sha256 DESC
            LIMIT ?
            """,
            (normalized_limit,),
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            sheet_names = row.get("sheet_names_json")
            parsed_sheet_names = (
                loads(sheet_names)
                if isinstance(sheet_names, str) and sheet_names.strip()
                else []
            )
            items.append({**row, "sheet_names": parsed_sheet_names})
        return {"items": items, "total": len(items)}
