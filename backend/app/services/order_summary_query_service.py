from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..db import fetch_all
from ..errors import bad_request, forbidden
from .user_scope_support import (
    ROLE_SCHEDULER,
    current_user_role_code,
    resolve_order_summary_scope_manager_user_id,
)
SCHEDULE_NUMBER_EPSILON = 1e-9


def _normalize_date_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        from datetime import date

        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _to_number(value: object, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


class OrderSummaryQueryService:
    def __init__(self, host: Any) -> None:
        self.host = host
        self.connection = host.connection

    def get_order_summary(
        self,
        *,
        start_date: str,
        end_date: str,
        workshop_manager_user_id: str | None = None,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_start_date = _normalize_date_text(start_date)
        if normalized_start_date is None:
            raise bad_request(
                code="ORDER_SUMMARY_START_DATE_REQUIRED",
                message="start_date must be a valid YYYY-MM-DD date.",
            )
        normalized_end_date = _normalize_date_text(end_date)
        if normalized_end_date is None:
            raise bad_request(
                code="ORDER_SUMMARY_END_DATE_REQUIRED",
                message="end_date must be a valid YYYY-MM-DD date.",
            )
        if normalized_end_date < normalized_start_date:
            raise bad_request(
                code="ORDER_SUMMARY_DATE_RANGE_INVALID",
                message="end_date must be greater than or equal to start_date.",
                details={
                    "start_date": normalized_start_date,
                    "end_date": normalized_end_date,
                },
            )

        filters: list[str] = [
            "date(work_reports.report_time, '+8 hours') >= ?",
            "date(work_reports.report_time, '+8 hours') <= ?",
        ]
        parameters: list[Any] = [normalized_start_date, normalized_end_date]
        manager_user_id = resolve_order_summary_scope_manager_user_id(
            self.connection,
            current_user=current_user,
            workshop_manager_user_id=workshop_manager_user_id,
        )
        if manager_user_id is not None:
            filters.append(
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

        where_sql = " AND ".join(filters)
        grouped_report_rows = fetch_all(
            self.connection,
            f"""
            SELECT
                production_order_no,
                process_code,
                process_name,
                SUM(report_qty) AS report_qty,
                MAX(date(report_time, '+8 hours')) AS last_report_local_date
            FROM work_reports
            WHERE {where_sql}
            GROUP BY production_order_no, process_code
            ORDER BY production_order_no ASC, process_code ASC
            """,
            tuple(parameters),
        )

        process_name_by_code = self.host._process_name_by_code()
        order_process_qty_map: dict[str, dict[str, float]] = defaultdict(dict)
        order_process_last_date_map: dict[str, dict[str, str | None]] = defaultdict(dict)
        process_agg_map: dict[str, dict[str, Any]] = {}
        order_nos: set[str] = set()
        for row in grouped_report_rows:
            process_code = str(row.get("process_code") or "").strip().upper()
            if not process_code:
                continue
            process_name = (
                str(row.get("process_name") or process_name_by_code.get(process_code) or process_code).strip()
                or process_code
            )
            report_qty = _to_number(row.get("report_qty"), 0)
            last_report_local_date = _normalize_date_text(row.get("last_report_local_date"))
            order_no = str(row.get("production_order_no") or "").strip()

            process_agg = process_agg_map.get(process_code)
            if process_agg is None:
                process_agg = {
                    "process_code": process_code,
                    "process_name_cn": process_name,
                    "report_qty_total": 0.0,
                    "order_nos": set(),
                    "last_report_date": None,
                }
                process_agg_map[process_code] = process_agg
            process_agg["report_qty_total"] = _to_number(process_agg.get("report_qty_total"), 0) + report_qty
            if last_report_local_date and (
                process_agg["last_report_date"] is None or last_report_local_date > process_agg["last_report_date"]
            ):
                process_agg["last_report_date"] = last_report_local_date

            if not order_no:
                continue
            order_nos.add(order_no)
            process_agg["order_nos"].add(order_no)
            order_process_qty_map[order_no][process_code] = report_qty
            order_process_last_date_map[order_no][process_code] = last_report_local_date

        if not order_nos and not process_agg_map:
            return {
                "range": {
                    "start_date": normalized_start_date,
                    "end_date": normalized_end_date,
                },
                "summary": {
                    "order_count": 0,
                    "completed_order_count": 0,
                    "completion_rate": 0,
                    "order_qty_total": 0,
                    "final_process_completed_qty_total": 0,
                    "process_count": 0,
                    "process_report_qty_total": 0,
                },
                "order_items": [],
                "process_items": [],
            }

        order_meta_by_no: dict[str, dict[str, Any]] = {}
        if order_nos:
            placeholders = ",".join("?" for _ in order_nos)
            order_rows = fetch_all(
                self.connection,
                f"""
                SELECT
                    production_order_no,
                    material_code,
                    material_name,
                    production_qty
                FROM production_orders
                WHERE production_order_no IN ({placeholders})
                """,
                tuple(sorted(order_nos)),
            )
            for row in order_rows:
                order_no = str(row.get("production_order_no") or "").strip()
                if order_no:
                    order_meta_by_no[order_no] = row

        product_codes = {
            str((order_meta_by_no.get(order_no) or {}).get("material_code") or "").strip().upper()
            for order_no in order_nos
        }
        product_codes.discard("")
        final_process_by_product = self.host._resolve_final_process_meta_by_product(product_codes)

        order_items: list[dict[str, Any]] = []
        for order_no in sorted(order_nos):
            order_meta = order_meta_by_no.get(order_no) or {}
            product_code = str(order_meta.get("material_code") or "").strip().upper()
            product_name = str(order_meta.get("material_name") or product_code or "-").strip() or "-"
            order_qty = _to_number(order_meta.get("production_qty"), 0)
            final_meta = final_process_by_product.get(product_code) or {}
            final_process_code = str(final_meta.get("process_code") or "").strip().upper() or None
            final_process_name_cn = str(final_meta.get("process_name_cn") or final_process_code or "-").strip() or "-"
            process_qty_by_code = order_process_qty_map.get(order_no) or {}
            process_last_date_by_code = order_process_last_date_map.get(order_no) or {}
            final_process_completed_qty = (
                _to_number(process_qty_by_code.get(final_process_code), 0) if final_process_code else 0.0
            )
            final_process_last_report_date = (
                _normalize_date_text(process_last_date_by_code.get(final_process_code))
                if final_process_code
                else None
            )
            completed_flag = (
                bool(final_process_code)
                and order_qty > 0
                and (final_process_completed_qty + SCHEDULE_NUMBER_EPSILON) >= order_qty
            )
            order_items.append(
                {
                    "order_no": order_no,
                    "product_code": product_code or "-",
                    "product_name_cn": product_name,
                    "order_qty": order_qty,
                    "reported_process_count": len(process_qty_by_code),
                    "final_process_code": final_process_code,
                    "final_process_name_cn": final_process_name_cn,
                    "final_process_completed_qty": final_process_completed_qty,
                    "final_process_last_report_date": final_process_last_report_date,
                    "completed_flag": 1 if completed_flag else 0,
                }
            )

        process_items: list[dict[str, Any]] = []
        for process_code in sorted(process_agg_map):
            process_agg = process_agg_map[process_code]
            order_no_set = set(process_agg.get("order_nos") or set())
            involved_order_count = len(order_no_set)
            completed_order_count = 0
            if involved_order_count > 0:
                for order_no in order_no_set:
                    order_meta = order_meta_by_no.get(order_no) or {}
                    order_qty = _to_number(order_meta.get("production_qty"), 0)
                    process_report_qty = _to_number(
                        (order_process_qty_map.get(order_no) or {}).get(process_code),
                        0,
                    )
                    if order_qty > 0 and (process_report_qty + SCHEDULE_NUMBER_EPSILON) >= order_qty:
                        completed_order_count += 1
            completion_rate = (
                round(completed_order_count / involved_order_count * 100, 2)
                if involved_order_count > 0
                else 0
            )
            process_items.append(
                {
                    "process_code": process_code,
                    "process_name_cn": str(process_agg.get("process_name_cn") or process_code).strip()
                    or process_code,
                    "report_qty_total": _to_number(process_agg.get("report_qty_total"), 0),
                    "involved_order_count": involved_order_count,
                    "completed_order_count": completed_order_count,
                    "completion_rate": completion_rate,
                    "last_report_date": _normalize_date_text(process_agg.get("last_report_date")),
                }
            )

        order_count = len(order_items)
        completed_order_count = sum(1 for item in order_items if int(item.get("completed_flag") or 0) == 1)
        order_completion_rate = round(completed_order_count / order_count * 100, 2) if order_count > 0 else 0
        order_qty_total = round(sum(_to_number(item.get("order_qty"), 0) for item in order_items), 4)
        final_process_completed_qty_total = round(
            sum(_to_number(item.get("final_process_completed_qty"), 0) for item in order_items),
            4,
        )
        process_report_qty_total = round(
            sum(_to_number(item.get("report_qty_total"), 0) for item in process_items),
            4,
        )

        return {
            "range": {
                "start_date": normalized_start_date,
                "end_date": normalized_end_date,
            },
            "summary": {
                "order_count": order_count,
                "completed_order_count": completed_order_count,
                "completion_rate": order_completion_rate,
                "order_qty_total": order_qty_total,
                "final_process_completed_qty_total": final_process_completed_qty_total,
                "process_count": len(process_items),
                "process_report_qty_total": process_report_qty_total,
            },
            "order_items": order_items,
            "process_items": process_items,
        }

    def list_order_summary_workshop_managers(
        self,
        *,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if current_user_role_code(current_user) != ROLE_SCHEDULER:
            raise forbidden(
                code="ORDER_SUMMARY_WORKSHOP_MANAGER_FILTER_FORBIDDEN",
                message="Only scheduler can list order summary workshop manager filters.",
            )
        rows = fetch_all(
            self.connection,
            """
            SELECT
                users.user_id,
                users.username,
                users.display_name,
                COUNT(scope.line_code) AS line_scope_count
            FROM app_users users
            LEFT JOIN masterdata_workshop_manager_visibility visibility
              ON visibility.user_id = users.user_id
            JOIN app_user_line_scopes scope
              ON scope.user_id = users.user_id
            WHERE users.role_code = ?
              AND users.enabled_flag = 1
              AND COALESCE(visibility.visible_flag, 1) = 1
            GROUP BY users.user_id, users.username, users.display_name
            HAVING COUNT(scope.line_code) > 0
            ORDER BY
                LOWER(COALESCE(NULLIF(TRIM(users.display_name), ''), NULLIF(TRIM(users.username), ''), users.user_id)) ASC,
                LOWER(COALESCE(users.username, '')) ASC,
                users.user_id ASC
            """,
            (ROLE_WORKSHOP_MANAGER,),
        )
        return {
            "items": [
                {
                    "user_id": str(row.get("user_id") or "").strip(),
                    "username": str(row.get("username") or "").strip(),
                    "display_name": str(row.get("display_name") or "").strip(),
                    "line_scope_count": int(_to_number(row.get("line_scope_count"), 0)),
                }
                for row in rows
            ]
        }
