from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import math
import random
import sqlite3
from typing import Any
from uuid import uuid4

from ..db import fetch_all, fetch_one, transaction, utc_now
from ..errors import bad_request, not_found, server_error
from ..gateway.inventory import ERPInventoryGateway
from ..gateway.masterdata import UpstreamMasterdataGateway
from ..gateway.orders import ERPOrderGateway
from ..gateway.supply import ERPSupplyGateway
from ..json_utils import dumps, loads
from .job_dispatcher import ServiceFactory


RULES_SINGLETON_KEY = "default"
SHIFT_SEQUENCE = ("DAY", "NIGHT")
SHIFT_INDEX_BY_CODE = {"DAY": 0, "NIGHT": 1}
SHIFT_CODE_BY_INDEX = {0: "DAY", 1: "NIGHT"}
WEEKEND_REST_MODES = {"NONE", "SINGLE", "DOUBLE"}
DATE_SHIFT_MODES = {"REST", "DAY", "NIGHT", "BOTH"}
SUPPORTED_STRATEGY_CODES = {
    "KEY_ORDER_FIRST",
    "MAX_CAPACITY_FIRST",
    "MIN_DELAY_FIRST",
}
SUPPORTED_CN_HOLIDAY_YEARS = {2024, 2025, 2026, 2027, 2028}
CN_STATUTORY_HOLIDAY_DATE_SET = frozenset(
    {
        # 2024
        "2024-01-01",
        "2024-02-10",
        "2024-02-11",
        "2024-02-12",
        "2024-02-13",
        "2024-02-14",
        "2024-02-15",
        "2024-02-16",
        "2024-02-17",
        "2024-04-04",
        "2024-04-05",
        "2024-04-06",
        "2024-05-01",
        "2024-05-02",
        "2024-05-03",
        "2024-05-04",
        "2024-05-05",
        "2024-06-08",
        "2024-06-09",
        "2024-06-10",
        "2024-09-15",
        "2024-09-16",
        "2024-09-17",
        "2024-10-01",
        "2024-10-02",
        "2024-10-03",
        "2024-10-04",
        "2024-10-05",
        "2024-10-06",
        "2024-10-07",
        # 2025
        "2025-01-01",
        "2025-01-28",
        "2025-01-29",
        "2025-01-30",
        "2025-01-31",
        "2025-02-01",
        "2025-02-02",
        "2025-02-03",
        "2025-02-04",
        "2025-04-04",
        "2025-04-05",
        "2025-04-06",
        "2025-05-01",
        "2025-05-02",
        "2025-05-03",
        "2025-05-04",
        "2025-05-05",
        "2025-05-31",
        "2025-06-01",
        "2025-06-02",
        "2025-10-01",
        "2025-10-02",
        "2025-10-03",
        "2025-10-04",
        "2025-10-05",
        "2025-10-06",
        "2025-10-07",
        "2025-10-08",
        # 2026
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
        "2026-02-15",
        "2026-02-16",
        "2026-02-17",
        "2026-02-18",
        "2026-02-19",
        "2026-02-20",
        "2026-02-21",
        "2026-02-22",
        "2026-02-23",
        "2026-04-04",
        "2026-04-05",
        "2026-04-06",
        "2026-05-01",
        "2026-05-02",
        "2026-05-03",
        "2026-05-04",
        "2026-05-05",
        "2026-06-19",
        "2026-06-20",
        "2026-06-21",
        "2026-09-25",
        "2026-09-26",
        "2026-09-27",
        "2026-10-01",
        "2026-10-02",
        "2026-10-03",
        "2026-10-04",
        "2026-10-05",
        "2026-10-06",
        "2026-10-07",
    }
)
SCHEDULE_SLOT_SEARCH_GUARD = 20000
SCHEDULE_EPOCH_DAY = date(1970, 1, 1)
SCHEDULE_NUMBER_EPSILON = 1e-9
STATUS_NAME_BY_CODE = {
    "DRAFT": "Draft",
    "PUBLISHED": "Published",
    "ARCHIVED": "Archived",
}


def _today_text() -> str:
    return date.today().isoformat()


def _normalize_date_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _parse_date_or_today(value: object) -> date:
    normalized = _normalize_date_text(value)
    if normalized is None:
        return date.today()
    return date.fromisoformat(normalized)


def _iso_at(date_text: str | None, clock_text: str) -> str | None:
    if not date_text:
        return None
    return f"{date_text}T{clock_text}+08:00"


def _days_between(start_text: object, end_text: object) -> int:
    start = _normalize_date_text(start_text)
    end = _normalize_date_text(end_text)
    if not start or not end:
        return 0
    return max(0, (date.fromisoformat(end) - date.fromisoformat(start)).days)


def _to_number(value: object, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def _route_row_id(product_code: str, sequence_no: int) -> str:
    return f"route-{product_code}-{sequence_no}"


def _status_name(status: str) -> str:
    normalized = str(status or "").strip().upper()
    return STATUS_NAME_BY_CODE.get(normalized, normalized or "-")


def _normalize_shift_code(value: object) -> str:
    normalized = str(value or "").strip().upper()
    if normalized == "D":
        return "DAY"
    if normalized == "N":
        return "NIGHT"
    if normalized in SHIFT_INDEX_BY_CODE:
        return normalized
    return "DAY"


def _slot_index_for(date_value: date, shift_code: str) -> int:
    shift_index = SHIFT_INDEX_BY_CODE[_normalize_shift_code(shift_code)]
    day_index = (date_value - SCHEDULE_EPOCH_DAY).days
    return day_index * 2 + shift_index


def _slot_index_from_text(date_text: str, shift_code: str) -> int:
    return _slot_index_for(date.fromisoformat(date_text), shift_code)


def _slot_to_date_shift(slot_index: int) -> tuple[date, str]:
    if slot_index < 0:
        raise ValueError("slot_index must be >= 0")
    day_index = slot_index // 2
    shift_index = slot_index % 2
    return (
        SCHEDULE_EPOCH_DAY + timedelta(days=day_index),
        SHIFT_CODE_BY_INDEX[shift_index],
    )


def _material_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_no": row.get("production_order_no"),
        "child_material_code": row["child_material_code"],
        "child_material_name_cn": row["child_material_name"],
        "spec_model": row.get("spec_model"),
        "issue_qty": row.get("issue_qty"),
        "required_qty": row.get("issue_qty"),
        "usage_numerator": row.get("usage_numerator"),
        "usage_denominator": row.get("usage_denominator"),
        "child_unit": row.get("child_unit"),
        "child_material_supply_type": row["supply_type_code"],
        "child_material_supply_type_name_cn": row["supply_type_name"],
        "child_material_inventory_qty": row.get("inventory_qty"),
        "child_material_inventory_status": row["inventory_status"],
    }


class AppService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.factory = ServiceFactory(connection)
        self.masterdata_gateway = UpstreamMasterdataGateway()
        self.order_gateway = ERPOrderGateway()
        self.inventory_gateway = ERPInventoryGateway()
        self.supply_gateway = ERPSupplyGateway()

    def list_order_pool(self) -> dict[str, Any]:
        rows = self._list_order_rows()
        order_nos = [str(row["production_order_no"]) for row in rows]
        states = self._get_order_state_map(order_nos)
        capacity_map = self._get_capacity_map(order_nos)
        self._ensure_masterdata_seeded()
        route_rows = self._list_route_rows()
        route_map = self._group_routes_by_product(route_rows)
        topology_by_process = self._first_topology_by_process(self._list_line_topology_rows())
        items = [
            self._build_order_pool_row(
                base_row=row,
                state_row=states.get(str(row["production_order_no"])),
                capacity_rows=capacity_map.get(str(row["production_order_no"]), []),
                route_rows=route_map.get(str(row["material_code"]), []),
                topology_by_process=topology_by_process,
            )
            for row in rows
        ]
        return {"items": items}

    def get_order_pool_item(self, order_no: str) -> dict[str, Any]:
        base_row = self._require_order(order_no)
        state_row = self._get_order_state(order_no)
        self._ensure_masterdata_seeded()
        route_rows = self._group_routes_by_product(self._list_route_rows()).get(
            str(base_row["material_code"]),
            [],
        )
        topology_by_process = self._first_topology_by_process(self._list_line_topology_rows())
        capacity_rows = self._get_capacity_rows(order_no)
        return self._build_order_pool_row(
            base_row=base_row,
            state_row=state_row,
            capacity_rows=capacity_rows,
            route_rows=route_rows,
            topology_by_process=topology_by_process,
        )

    def list_order_pool_materials(
        self,
        order_no: str,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        if refresh:
            self.factory.build_material_refresh_service().refresh_order_materials(order_no)
        items = self.factory.build_material_query_service().list_order_materials(order_no)
        return {"items": [_material_row(item) for item in items]}

    def list_material_children(
        self,
        parent_material_code: str,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        if refresh:
            self._refresh_bom_children(parent_material_code)
        items = self.factory.build_material_query_service().list_bom_children(
            parent_material_code
        )
        return {"items": [_material_row(item) for item in items]}

    def patch_order_pool_order(
        self,
        order_no: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        base_row = self._require_order(order_no)
        current = self._get_order_state(order_no) or {}
        next_row = {
            "production_order_no": order_no,
            "promised_due_date": current.get("promised_due_date"),
            "expected_start_date": current.get("expected_start_date"),
            "expected_start_time": current.get("expected_start_time"),
            "expected_finish_time": current.get("expected_finish_time"),
            "urgent_flag": int(current.get("urgent_flag") or 0),
            "lock_flag": int(current.get("lock_flag") or 0),
            "frozen_flag": int(current.get("frozen_flag") or 0),
            "status": current.get("status") or base_row.get("status"),
            "order_status": current.get("order_status") or current.get("status") or base_row.get("status"),
            "completed_qty": current.get("completed_qty"),
            "remaining_qty": current.get("remaining_qty"),
            "progress_rate": current.get("progress_rate"),
            "production_batch_no": current.get("production_batch_no"),
        }

        expected_start_date = _normalize_date_text(payload.get("expected_start_date"))
        if expected_start_date:
            duration_days = _days_between(
                base_row.get("planned_start_date"),
                base_row.get("planned_end_date"),
            )
            finish_date = (
                date.fromisoformat(expected_start_date) + timedelta(days=duration_days)
            ).isoformat()
            next_row["expected_start_date"] = expected_start_date
            next_row["expected_start_time"] = _iso_at(expected_start_date, "08:00:00")
            next_row["expected_finish_time"] = _iso_at(finish_date, "18:00:00")
            next_row["promised_due_date"] = finish_date

        for field in ("urgent_flag", "lock_flag", "frozen_flag"):
            if field in payload:
                next_row[field] = int(payload[field] or 0)

        status_value = str(payload.get("status") or "").strip().upper()
        order_status_value = str(payload.get("order_status") or "").strip().upper()
        if status_value:
            next_row["status"] = status_value
        if order_status_value:
            next_row["order_status"] = order_status_value

        production_qty = _to_number(base_row.get("production_qty"), 0)
        normalized_status = str(
            next_row.get("order_status") or next_row.get("status") or ""
        ).strip().upper()
        if normalized_status == "DONE":
            next_row["status"] = "DONE"
            next_row["order_status"] = "DONE"
            next_row["completed_qty"] = production_qty
            next_row["remaining_qty"] = 0
            next_row["progress_rate"] = 100

        if "production_batch_no" in payload:
            next_row["production_batch_no"] = str(payload.get("production_batch_no") or "").strip() or None

        with transaction(self.connection):
            self._upsert_order_state(next_row)
        return self.get_order_pool_item(order_no)

    def delete_order_pool_order(self, order_no: str) -> dict[str, Any]:
        self._require_order(order_no)
        with transaction(self.connection):
            self.connection.execute(
                "DELETE FROM production_orders WHERE production_order_no = ?",
                (order_no,),
            )
        return {"ok": True}

    def list_mes_reportings(
        self,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, Any]:
        where_clauses: list[str] = []
        parameters: list[Any] = []
        if start_time:
            where_clauses.append("report_time >= ?")
            parameters.append(start_time)
        if end_time:
            where_clauses.append("report_time <= ?")
            parameters.append(end_time)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        rows = fetch_all(
            self.connection,
            f"""
            SELECT
                report_id,
                production_order_no,
                process_code,
                process_name,
                report_qty,
                report_time,
                operator_name
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
                    "report_qty": row.get("report_qty"),
                    "report_time": row.get("report_time"),
                    "operator_name_cn": row.get("operator_name") or "系统填报",
                }
                for row in rows
            ]
        }

    def create_reporting(self, payload: dict[str, Any]) -> dict[str, Any]:
        order_no = str(payload.get("order_no") or "").strip()
        process_code = str(payload.get("process_code") or "").strip().upper()
        report_qty = _to_number(payload.get("report_qty"), -1)
        if not order_no:
            raise bad_request(
                code="ORDER_NO_REQUIRED",
                message="order_no is required.",
            )
        if not process_code:
            raise bad_request(
                code="PROCESS_CODE_REQUIRED",
                message="process_code is required.",
            )
        if report_qty <= 0:
            raise bad_request(
                code="REPORT_QTY_INVALID",
                message="report_qty must be greater than 0.",
            )
        self._require_order(order_no)
        process_name_by_code = self._process_name_by_code()
        report_id = f"RPT-{uuid4().hex[:10].upper()}"
        report_time = utc_now()
        operator_name = (
            str(
                payload.get("operator_name_cn")
                or payload.get("operator_name")
                or "系统填报"
            ).strip()
            or "系统填报"
        )
        with transaction(self.connection):
            self.connection.execute(
                """
                INSERT INTO work_reports (
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
                    operator_name,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    order_no,
                    process_code,
                    process_name_by_code.get(process_code, process_code),
                    None,
                    None,
                    None,
                    None,
                    report_qty,
                    report_time,
                    operator_name,
                    report_time,
                ),
            )
        return {
            "report_id": report_id,
            "order_no": order_no,
            "process_code": process_code,
            "process_name_cn": process_name_by_code.get(process_code, process_code),
            "report_qty": report_qty,
            "report_time": report_time,
            "operator_name_cn": operator_name,
        }

    def delete_reporting(self, report_id: str) -> dict[str, Any]:
        existing = fetch_one(
            self.connection,
            "SELECT report_id FROM work_reports WHERE report_id = ?",
            (report_id,),
        )
        if existing is None:
            raise not_found(
                code="REPORT_NOT_FOUND",
                message="Report does not exist.",
                details={"report_id": report_id},
            )
        with transaction(self.connection):
            self.connection.execute(
                "DELETE FROM work_reports WHERE report_id = ?",
                (report_id,),
            )
        return {"ok": True}

    def list_schedule_versions(self) -> dict[str, Any]:
        rows = fetch_all(
            self.connection,
            """
            SELECT version_no, status, status_name_cn, strategy_code, created_at, published_at
            FROM schedule_versions
            ORDER BY created_at ASC, version_no ASC
            """,
        )
        return {"items": rows}

    def get_schedule_version(self, version_no: str) -> dict[str, Any]:
        row = fetch_one(
            self.connection,
            """
            SELECT version_no, status, status_name_cn, strategy_code, created_at, published_at
            FROM schedule_versions
            WHERE version_no = ?
            """,
            (version_no,),
        )
        if row is None:
            raise not_found(
                code="SCHEDULE_VERSION_NOT_FOUND",
                message="Schedule version does not exist.",
                details={"version_no": version_no},
            )
        return row

    def list_schedule_tasks(self, version_no: str) -> dict[str, Any]:
        self.get_schedule_version(version_no)
        rows = fetch_all(
            self.connection,
            """
            SELECT
                production_order_no,
                process_code,
                process_name_cn,
                calendar_date,
                shift_code,
                plan_qty,
                plan_start_time
            FROM schedule_tasks
            WHERE version_no = ?
            ORDER BY task_no ASC
            """,
            (version_no,),
        )
        return {
            "items": [
                {
                    "order_no": row["production_order_no"],
                    "process_code": row["process_code"],
                    "process_name_cn": row.get("process_name_cn") or row["process_code"],
                    "calendar_date": row["calendar_date"],
                    "shift_code": row["shift_code"],
                    "plan_qty": row["plan_qty"],
                    "plan_start_time": row.get("plan_start_time"),
                }
                for row in rows
            ]
        }

    def get_schedule_algorithm(self, version_no: str) -> dict[str, Any]:
        row = self.get_schedule_version(version_no)
        return {
            "version_no": row["version_no"],
            "strategy_code": row["strategy_code"],
            "algorithm_name_cn": "MVP Schedule",
        }

    def get_schedule_diff(
        self,
        version_no: str,
        compare_with: str | None,
    ) -> dict[str, Any]:
        self.get_schedule_version(version_no)
        if compare_with:
            self.get_schedule_version(compare_with)
        return {"items": []}

    def get_schedule_daily_process_load(self, version_no: str) -> dict[str, Any]:
        self.get_schedule_version(version_no)
        rows = fetch_all(
            self.connection,
            """
            SELECT
                calendar_date,
                process_code,
                COALESCE(MAX(process_name_cn), process_code) AS process_name_cn,
                COUNT(1) AS task_count,
                SUM(plan_qty) AS plan_qty
            FROM schedule_tasks
            WHERE version_no = ?
            GROUP BY calendar_date, process_code
            ORDER BY calendar_date ASC, process_code ASC
            """,
            (version_no,),
        )
        return {"items": rows}

    def get_masterdata_config(self) -> dict[str, Any]:
        self._ensure_masterdata_seeded()
        rules = self.get_schedule_calendar_rules()["data"]
        line_topology = self._list_line_topology_rows()
        route_rows = self._list_route_rows()
        process_seen: dict[str, str] = {}
        for row in route_rows:
            process_code = str(row.get("process_code") or "").strip().upper()
            if process_code and process_code not in process_seen:
                process_seen[process_code] = str(
                    row.get("process_name_cn") or process_code
                )
        for row in line_topology:
            process_code = str(row.get("process_code") or "").strip().upper()
            if process_code and process_code not in process_seen:
                process_seen[process_code] = process_code
        process_configs = [
            {"process_code": code, "process_name_cn": name}
            for code, name in sorted(process_seen.items())
        ]
        return {
            "data": {
                "horizon_start_date": rules["horizon_start_date"],
                "horizon_days": rules["horizon_days"],
                "skip_statutory_holidays": rules["skip_statutory_holidays"],
                "weekend_rest_mode": rules["weekend_rest_mode"],
                "date_shift_mode_by_date": rules["date_shift_mode_by_date"],
                "process_configs": process_configs,
                "line_topology": line_topology,
                "resource_pool": [],
                "material_availability": [],
            }
        }

    def save_masterdata_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        line_topology = payload.get("line_topology")
        if not isinstance(line_topology, list) or len(line_topology) == 0:
            raise bad_request(
                code="LINE_TOPOLOGY_REQUIRED",
                message="line_topology must be a non-empty array.",
            )
        updated_at = utc_now()
        rows = []
        for item in line_topology:
            company_code = str(item.get("company_code") or "COMPANY-MAIN").strip().upper() or "COMPANY-MAIN"
            workshop_code = str(item.get("workshop_code") or "").strip().upper()
            line_code = str(item.get("line_code") or "").strip().upper()
            process_code = str(item.get("process_code") or "").strip().upper()
            if not workshop_code or not line_code or not process_code:
                raise bad_request(
                    code="LINE_TOPOLOGY_ROW_INVALID",
                    message="workshop_code, line_code and process_code are required.",
                )
            rows.append(
                (
                    company_code,
                    workshop_code,
                    str(item.get("workshop_name") or workshop_code).strip() or workshop_code,
                    line_code,
                    str(item.get("line_name") or line_code).strip() or line_code,
                    process_code,
                    _to_number(item.get("capacity_per_shift"), 0),
                    int(_to_number(item.get("required_workers"), 0)),
                    int(_to_number(item.get("required_machines"), 0)),
                    int(item.get("enabled_flag") or 0),
                    updated_at,
                )
            )
        with transaction(self.connection):
            self.connection.execute("DELETE FROM masterdata_line_topology")
            self.connection.executemany(
                """
                INSERT INTO masterdata_line_topology (
                    company_code,
                    workshop_code,
                    workshop_name,
                    line_code,
                    line_name,
                    process_code,
                    capacity_per_shift,
                    required_workers,
                    required_machines,
                    enabled_flag,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return self.get_masterdata_config()

    def list_process_routes(self) -> dict[str, Any]:
        self._ensure_masterdata_seeded()
        return {"items": self._list_route_rows()}

    def create_process_routes(self, payload: dict[str, Any]) -> dict[str, Any]:
        product_code = str(payload.get("product_code") or "").strip().upper()
        if not product_code:
            raise bad_request(
                code="PRODUCT_CODE_REQUIRED",
                message="product_code is required.",
            )
        existing = fetch_one(
            self.connection,
            """
            SELECT 1
            FROM masterdata_process_routes
            WHERE product_code = ?
            LIMIT 1
            """,
            (product_code,),
        )
        if existing is not None:
            raise bad_request(
                code="ROUTE_ALREADY_EXISTS",
                message="Route already exists for product.",
                details={"product_code": product_code},
            )
        self._replace_process_routes(product_code, payload.get("steps"), source_product_code=None)
        return {"ok": True}

    def update_process_routes(self, payload: dict[str, Any]) -> dict[str, Any]:
        product_code = str(payload.get("product_code") or "").strip().upper()
        if not product_code:
            raise bad_request(
                code="PRODUCT_CODE_REQUIRED",
                message="product_code is required.",
            )
        self._replace_process_routes(product_code, payload.get("steps"), source_product_code=product_code)
        return {"ok": True}

    def copy_process_routes(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_product_code = str(payload.get("source_product_code") or "").strip().upper()
        target_product_code = str(payload.get("target_product_code") or "").strip().upper()
        if not source_product_code or not target_product_code:
            raise bad_request(
                code="PRODUCT_CODE_REQUIRED",
                message="source_product_code and target_product_code are required.",
            )
        self._replace_process_routes(
            target_product_code,
            payload.get("steps"),
            source_product_code=source_product_code,
        )
        return {"ok": True}

    def delete_process_routes(self, payload: dict[str, Any]) -> dict[str, Any]:
        product_code = str(payload.get("product_code") or "").strip().upper()
        if not product_code:
            raise bad_request(
                code="PRODUCT_CODE_REQUIRED",
                message="product_code is required.",
            )
        with transaction(self.connection):
            self.connection.execute(
                "DELETE FROM masterdata_process_routes WHERE product_code = ?",
                (product_code,),
            )
        return {"ok": True}

    def get_schedule_calendar_rules(self) -> dict[str, Any]:
        row = self._get_rules_row()
        return {
            "data": {
                "horizon_start_date": row["horizon_start_date"],
                "horizon_days": row["horizon_days"],
                "skip_statutory_holidays": bool(row["skip_statutory_holidays"]),
                "weekend_rest_mode": row["weekend_rest_mode"],
                "date_shift_mode_by_date": loads(row["date_shift_mode_by_date_json"]) or {},
            }
        }

    def save_schedule_calendar_rules(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._get_rules_row()
        weekend_rest_mode = self._normalize_weekend_rest_mode(
            payload.get("weekend_rest_mode")
            if "weekend_rest_mode" in payload
            else current["weekend_rest_mode"]
        )
        date_shift_mode_by_date = self._normalize_date_shift_mode_by_date(
            payload.get("date_shift_mode_by_date")
            if "date_shift_mode_by_date" in payload
            else (loads(current["date_shift_mode_by_date_json"]) or {})
        )
        next_row = {
            "singleton_key": RULES_SINGLETON_KEY,
            "horizon_start_date": _normalize_date_text(
                payload.get("horizon_start_date") or current["horizon_start_date"]
            )
            or _today_text(),
            "horizon_days": int(
                _to_number(payload.get("horizon_days"), current["horizon_days"])
            )
            or 31,
            "skip_statutory_holidays": 1
            if payload.get("skip_statutory_holidays") is True
            else (
                current["skip_statutory_holidays"]
                if "skip_statutory_holidays" not in payload
                else 0
            ),
            "weekend_rest_mode": weekend_rest_mode,
            "date_shift_mode_by_date_json": dumps(date_shift_mode_by_date),
            "updated_at": utc_now(),
        }
        with transaction(self.connection):
            self.connection.execute(
                """
                INSERT INTO schedule_calendar_rules (
                    singleton_key,
                    horizon_start_date,
                    horizon_days,
                    skip_statutory_holidays,
                    weekend_rest_mode,
                    date_shift_mode_by_date_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(singleton_key) DO UPDATE SET
                    horizon_start_date = excluded.horizon_start_date,
                    horizon_days = excluded.horizon_days,
                    skip_statutory_holidays = excluded.skip_statutory_holidays,
                    weekend_rest_mode = excluded.weekend_rest_mode,
                    date_shift_mode_by_date_json = excluded.date_shift_mode_by_date_json,
                    updated_at = excluded.updated_at
                """,
                (
                    next_row["singleton_key"],
                    next_row["horizon_start_date"],
                    next_row["horizon_days"],
                    next_row["skip_statutory_holidays"],
                    next_row["weekend_rest_mode"],
                    next_row["date_shift_mode_by_date_json"],
                    next_row["updated_at"],
                ),
            )
        return self.get_schedule_calendar_rules()

    def generate_schedule(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.factory.build_inventory_refresh_service().refresh_inventory([])
        self._ensure_masterdata_seeded()
        strategy_code = self._normalize_strategy_code(payload.get("strategy_code"))
        base_version_no = str(payload.get("base_version_no") or "").strip()
        base_schedule_hints: dict[str, dict[str, Any]] = {}
        if base_version_no:
            self.get_schedule_version(base_version_no)
            base_schedule_hints = self._build_base_schedule_hints(base_version_no)
        planning_rules = self._build_planning_rules_from_current_config()
        version_no = self._next_schedule_version_no()
        order_rows = self._list_order_rows()
        route_rows_by_product = self._group_routes_by_product(self._list_route_rows())
        capacity_map = self._get_capacity_map(
            [str(row["production_order_no"]) for row in order_rows]
        )
        states = self._get_order_state_map(
            [str(row["production_order_no"]) for row in order_rows]
        )
        topology_by_process = self._enabled_topology_by_process(
            self._list_line_topology_rows()
        )

        schedule_candidates: list[dict[str, Any]] = []
        simulation_state = self._get_simulation_state()
        simulation_start = _parse_date_or_today(simulation_state.get("current_date"))
        for order_row in order_rows:
            order_no = str(order_row["production_order_no"])
            state_row = states.get(order_no) or {}
            status = str(
                state_row.get("order_status")
                or state_row.get("status")
                or order_row.get("status")
                or ""
            ).strip().upper()
            if status == "DONE":
                continue

            remaining_qty = state_row.get("remaining_qty")
            if remaining_qty is None:
                production_qty = _to_number(order_row.get("production_qty"), 0)
                completed_qty = _to_number(state_row.get("completed_qty"), 0)
                remaining_qty = max(0.0, production_qty - completed_qty)
            remaining_qty_value = max(0.0, _to_number(remaining_qty, 0))
            if remaining_qty_value <= SCHEDULE_NUMBER_EPSILON:
                continue

            process_contexts = self._build_schedule_process_contexts(
                order_no=order_no,
                product_code=str(order_row["material_code"]),
                capacity_rows=capacity_map.get(order_no, []),
                route_rows=route_rows_by_product.get(str(order_row["material_code"]), []),
                topology_by_process=topology_by_process,
            )
            if len(process_contexts) == 0:
                raise server_error(
                    code="SCHEDULE_PROCESS_CONTEXTS_EMPTY",
                    message="No process contexts available for schedule generation.",
                    details={"order_no": order_no},
                )

            start_date = _parse_date_or_today(
                state_row.get("expected_start_date")
                or order_row.get("planned_start_date")
                or simulation_start.isoformat()
            )
            due_date = _parse_date_or_today(
                state_row.get("promised_due_date")
                or order_row.get("planned_end_date")
                or start_date.isoformat()
            )
            if due_date < start_date:
                due_date = start_date

            urgent_flag = int(_to_number(state_row.get("urgent_flag"), 0))
            lock_flag = int(_to_number(state_row.get("lock_flag"), 0))
            frozen_flag = int(_to_number(state_row.get("frozen_flag"), 0))

            base_hint = base_schedule_hints.get(order_no) or {}
            if base_version_no and (lock_flag == 1 or frozen_flag == 1) and not base_hint:
                raise bad_request(
                    code="BASE_VERSION_LOCKED_ORDER_MISSING",
                    message="Locked or frozen order is missing in base schedule version.",
                    details={"order_no": order_no, "base_version_no": base_version_no},
                )
            base_first_slot = base_hint.get("first_slot")
            start_slot = _slot_index_for(start_date, "DAY")
            if (lock_flag == 1 or frozen_flag == 1) and base_first_slot is not None:
                start_slot = max(start_slot, int(base_first_slot))

            required_shifts = 0
            min_capacity = None
            total_capacity = 0.0
            for context in process_contexts:
                capacity_per_shift = _to_number(context.get("capacity_per_shift"), 0)
                required_shifts += int(math.ceil(remaining_qty_value / capacity_per_shift))
                min_capacity = (
                    capacity_per_shift
                    if min_capacity is None
                    else min(min_capacity, capacity_per_shift)
                )
                total_capacity += capacity_per_shift
            slack_days = (due_date - start_date).days - required_shifts

            schedule_candidates.append(
                {
                    "order_no": order_no,
                    "product_code": str(order_row["material_code"]),
                    "remaining_qty": remaining_qty_value,
                    "start_date": start_date,
                    "due_date": due_date,
                    "start_slot": start_slot,
                    "urgent_flag": urgent_flag,
                    "lock_flag": lock_flag,
                    "frozen_flag": frozen_flag,
                    "updated_at": str(order_row.get("updated_at") or ""),
                    "process_contexts": process_contexts,
                    "required_shifts": required_shifts,
                    "slack_days": slack_days,
                    "min_capacity_per_shift": _to_number(min_capacity, 0),
                    "total_capacity_per_shift": total_capacity,
                    "base_first_task_no": int(base_hint.get("first_task_no") or 10**9),
                    "base_process_first_slot": base_hint.get("process_first_slot", {}),
                }
            )

        pending_candidates = self._sort_schedule_candidates(
            strategy_code=strategy_code,
            candidates=schedule_candidates,
        )

        tasks: list[tuple[Any, ...]] = []
        used_capacity_by_slot: dict[tuple[int, str, str, str], float] = {}
        day_mode_cache: dict[str, str] = {}
        task_no = 1
        while pending_candidates:
            selected_index = self._select_next_candidate_index(
                strategy_code=strategy_code,
                candidates=pending_candidates,
                planning_rules=planning_rules,
                day_mode_cache=day_mode_cache,
                used_capacity_by_slot=used_capacity_by_slot,
            )
            candidate = pending_candidates.pop(selected_index)
            order_no = str(candidate["order_no"])
            next_start_slot = int(candidate["start_slot"])
            process_base_first_slot = candidate.get("base_process_first_slot", {})
            for context in candidate["process_contexts"]:
                context_start_slot = next_start_slot
                process_code = str(context["process_code"])
                base_process_slot = process_base_first_slot.get(process_code)
                if (
                    (int(candidate["lock_flag"]) == 1 or int(candidate["frozen_flag"]) == 1)
                    and base_process_slot is not None
                ):
                    context_start_slot = max(context_start_slot, int(base_process_slot))

                allocations, last_slot = self._allocate_process_tasks(
                    order_no=order_no,
                    process_context=context,
                    required_qty=_to_number(candidate["remaining_qty"], 0),
                    first_slot=context_start_slot,
                    planning_rules=planning_rules,
                    day_mode_cache=day_mode_cache,
                    used_capacity_by_slot=used_capacity_by_slot,
                )
                for allocation in allocations:
                    calendar_date = allocation["calendar_date"]
                    shift_code = allocation["shift_code"]
                    tasks.append(
                        (
                            version_no,
                            task_no,
                            order_no,
                            process_code,
                            str(context["process_name_cn"]),
                            calendar_date,
                            shift_code,
                            allocation["plan_qty"],
                            _iso_at(
                                calendar_date,
                                "08:00:00" if shift_code == "DAY" else "20:00:00",
                            ),
                        )
                    )
                    task_no += 1
                next_start_slot = last_slot + 1

        created_at = utc_now()
        with transaction(self.connection):
            self.connection.execute(
                """
                INSERT INTO schedule_versions (
                    version_no,
                    status,
                    status_name_cn,
                    strategy_code,
                    created_at,
                    published_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    version_no,
                    "DRAFT",
                    _status_name("DRAFT"),
                    strategy_code,
                    created_at,
                    None,
                ),
            )
            if tasks:
                self.connection.executemany(
                    """
                    INSERT INTO schedule_tasks (
                        version_no,
                        task_no,
                        production_order_no,
                        process_code,
                        process_name_cn,
                        calendar_date,
                        shift_code,
                        plan_qty,
                        plan_start_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tasks,
                )
        return {"version_no": version_no}

    def publish_schedule_version(self, version_no: str) -> dict[str, Any]:
        self.get_schedule_version(version_no)
        published_at = utc_now()
        with transaction(self.connection):
            self.connection.execute(
                """
                UPDATE schedule_versions
                SET status = 'ARCHIVED',
                    status_name_cn = ?,
                    published_at = COALESCE(published_at, ?)
                WHERE status = 'PUBLISHED'
                  AND version_no <> ?
                """,
                (_status_name("ARCHIVED"), published_at, version_no),
            )
            self.connection.execute(
                """
                UPDATE schedule_versions
                SET status = 'PUBLISHED',
                    status_name_cn = ?,
                    published_at = ?
                WHERE version_no = ?
                """,
                (_status_name("PUBLISHED"), published_at, version_no),
            )
        return {"ok": True}

    def create_dispatch_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        order_no = str(payload.get("target_order_no") or "").strip()
        command_type = str(payload.get("command_type") or "").strip().upper()
        if not order_no or not command_type:
            raise bad_request(
                code="DISPATCH_COMMAND_INVALID",
                message="target_order_no and command_type are required.",
            )
        self._require_order(order_no)
        command_id = f"CMD-{uuid4().hex[:10].upper()}"
        now = utc_now()
        with transaction(self.connection):
            self.connection.execute(
                """
                INSERT INTO dispatch_commands (
                    command_id,
                    target_order_no,
                    command_type,
                    status,
                    effective_time,
                    reason,
                    created_by,
                    approver,
                    decision,
                    decision_reason,
                    decision_time,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command_id,
                    order_no,
                    command_type,
                    "PENDING",
                    payload.get("effective_time"),
                    payload.get("reason"),
                    payload.get("created_by"),
                    None,
                    None,
                    None,
                    None,
                    now,
                    now,
                ),
            )
        return {"command_id": command_id}

    def approve_dispatch_command(
        self,
        command_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = fetch_one(
            self.connection,
            """
            SELECT command_id, target_order_no, command_type, status
            FROM dispatch_commands
            WHERE command_id = ?
            """,
            (command_id,),
        )
        if row is None:
            raise not_found(
                code="DISPATCH_COMMAND_NOT_FOUND",
                message="Dispatch command does not exist.",
                details={"command_id": command_id},
            )
        decision = str(payload.get("decision") or "").strip().upper() or "APPROVED"
        now = utc_now()
        with transaction(self.connection):
            self.connection.execute(
                """
                UPDATE dispatch_commands
                SET status = ?,
                    approver = ?,
                    decision = ?,
                    decision_reason = ?,
                    decision_time = ?,
                    updated_at = ?
                WHERE command_id = ?
                """,
                (
                    decision,
                    payload.get("approver"),
                    decision,
                    payload.get("decision_reason"),
                    payload.get("decision_time") or now,
                    now,
                    command_id,
                ),
            )
            if decision == "APPROVED" and row["status"] != "APPROVED":
                self._apply_dispatch_command(
                    target_order_no=str(row["target_order_no"]),
                    command_type=str(row["command_type"]),
                )
        return {"ok": True}

    def advance_simulation_one_day(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._get_simulation_state()
        baseline = current["current_date"] or payload.get("client_date") or _today_text()
        next_date = (
            date.fromisoformat(_normalize_date_text(baseline) or _today_text())
            + timedelta(days=1)
        ).isoformat()
        with transaction(self.connection):
            self.connection.execute(
                """
                INSERT INTO simulation_state (
                    singleton_key,
                    current_date,
                    updated_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(singleton_key) DO UPDATE SET
                    current_date = excluded.current_date,
                    updated_at = excluded.updated_at
                """,
                (RULES_SINGLETON_KEY, next_date, utc_now()),
            )
        return {
            "current_date": next_date,
            "message": f"Simulation advanced to {next_date}.",
        }

    def reset_manual_simulation(self) -> dict[str, Any]:
        current_date = _today_text()
        with transaction(self.connection):
            self.connection.execute(
                """
                INSERT INTO simulation_state (
                    singleton_key,
                    current_date,
                    updated_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(singleton_key) DO UPDATE SET
                    current_date = excluded.current_date,
                    updated_at = excluded.updated_at
                """,
                (RULES_SINGLETON_KEY, current_date, utc_now()),
            )
        return {
            "current_date": current_date,
            "message": "Simulation reset.",
        }

    def test_material_issues(self, order_no: str, mode: str) -> dict[str, Any]:
        normalized_mode = str(mode or "fast").strip().lower()
        items = self.factory.material_gateway.fetch_order_materials(
            order_no,
            mode=normalized_mode,
        )
        return {
            "items": [
                {
                    "order_no": item.get("production_order_no") or order_no,
                    "child_material_code": item.get("child_material_code"),
                    "child_material_name_cn": item.get("child_material_name"),
                    "spec_model": item.get("spec_model"),
                }
                for item in items
            ]
        }

    def test_material_supply(self, material_code: str) -> dict[str, Any]:
        code = str(material_code or "").strip()
        if not code:
            raise bad_request(
                code="MATERIAL_CODE_REQUIRED",
                message="material_code is required.",
            )
        rows = self.supply_gateway.fetch_material_supply([code])
        if len(rows) == 0:
            raise not_found(
                code="MATERIAL_SUPPLY_NOT_FOUND",
                message="Material supply does not exist in ERP.",
                details={"material_code": code},
            )
        updated_at = utc_now()
        with transaction(self.connection):
            self.factory.supply_repository.upsert_many(
                [
                    {
                        "material_code": str(row["material_code"]),
                        "supply_type_code": row["supply_type_code"],
                        "supply_type_name": row["supply_type_name"],
                        "snapshot_time": updated_at,
                        "updated_at": updated_at,
                    }
                    for row in rows
                ]
            )
        row = rows[0]
        return {
            "material_code": row["material_code"],
            "supply_type": row["supply_type_code"],
            "supply_type_name_cn": row["supply_type_name"],
            "is_self_made": str(row["supply_type_code"]).strip().upper() == "SELF_MADE",
        }

    def test_material_inventory(self, material_code: str) -> dict[str, Any]:
        code = str(material_code or "").strip()
        if not code:
            raise bad_request(
                code="MATERIAL_CODE_REQUIRED",
                message="material_code is required.",
            )
        snapshots = self.inventory_gateway.fetch_inventory([code])
        snapshot = snapshots[0] if snapshots else {
            "material_code": code,
            "inventory_qty": None,
            "inventory_status": "UNKNOWN",
        }
        updated_at = utc_now()
        with transaction(self.connection):
            self.factory.inventory_repository.upsert_many(
                [
                    {
                        "material_code": code,
                        "inventory_qty": snapshot.get("inventory_qty"),
                        "inventory_status": snapshot["inventory_status"],
                        "snapshot_time": updated_at,
                        "updated_at": updated_at,
                    }
                ]
            )
        reference = self._find_material_reference(code)
        inventory_qty = snapshot.get("inventory_qty")
        items = []
        if inventory_qty is not None:
            items.append(
                {
                    "material_code": code,
                    "material_name_cn": reference.get("material_name_cn") or code,
                    "spec_model": reference.get("spec_model"),
                    "warehouse_name": None,
                    "batch_no": None,
                    "base_unit_name": reference.get("child_unit"),
                    "stock_qty": inventory_qty,
                    "stock_org_name": None,
                }
            )
        return {
            "material_code": code,
            "items": items,
            "total_stock_qty": _to_number(inventory_qty, 0),
        }

    def import_production_orders(self, payload: dict[str, Any]) -> dict[str, Any]:
        random_guidewire = payload.get("random_guidewire_protection_order") is True
        count = 1 if random_guidewire else max(1, int(_to_number(payload.get("n"), 1)))
        material_code = (
            "YXN.044.02.1020"
            if random_guidewire
            else str(payload.get("material_code") or "").strip().upper()
        )
        if not material_code:
            raise bad_request(
                code="MATERIAL_CODE_REQUIRED",
                message="material_code is required.",
            )
        completed = payload.get("completed") is True
        product_name = "导丝保护组件" if random_guidewire else material_code
        updated_at = utc_now()
        next_number = self._next_import_order_sequence()
        order_nos: list[str] = []
        order_qty_list: list[int] = []
        with transaction(self.connection):
            for _ in range(count):
                order_no = f"{next_number:04d}MO-TEST"
                next_number += 1
                order_qty = random.randint(1000, 5000) if random_guidewire else 100
                start_date = _today_text()
                end_date = (date.today() + timedelta(days=3)).isoformat()
                source_bill_no = f"TEST-{order_no}"
                self.connection.execute(
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
                    (
                        order_no,
                        material_code,
                        product_name,
                        None,
                        order_qty,
                        "DONE" if completed else "OPEN",
                        start_date,
                        end_date,
                        source_bill_no,
                        f"ML-{material_code}",
                        updated_at,
                    ),
                )
                self._upsert_order_state(
                    {
                        "production_order_no": order_no,
                        "promised_due_date": end_date,
                        "expected_start_date": start_date,
                        "expected_start_time": _iso_at(start_date, "08:00:00"),
                        "expected_finish_time": _iso_at(end_date, "18:00:00"),
                        "urgent_flag": 0,
                        "lock_flag": 0,
                        "frozen_flag": 0,
                        "status": "DONE" if completed else "OPEN",
                        "order_status": "DONE" if completed else "OPEN",
                        "completed_qty": order_qty if completed else 0,
                        "remaining_qty": 0 if completed else order_qty,
                        "progress_rate": 100 if completed else 0,
                        "production_batch_no": f"{source_bill_no}-B1",
                    }
                )
                order_nos.append(order_no)
                order_qty_list.append(order_qty)
        return {
            "imported_count": count,
            "material_code": material_code,
            "product_name_cn": product_name,
            "completed": completed,
            "order_nos": order_nos,
            "order_qty_list": order_qty_list,
        }

    def import_production_orders_from_erp(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("random_guidewire_protection_order") is True:
            return self.import_production_orders(payload)
        material_code = str(payload.get("material_code") or "").strip().upper()
        keyword = str(payload.get("keyword") or "").strip()
        if not material_code and not keyword:
            raise bad_request(
                code="IMPORT_FILTER_REQUIRED",
                message="material_code or keyword is required.",
            )
        requested_count = max(1, min(200, int(_to_number(payload.get("n"), 1))))
        completed = payload.get("completed") is True
        erp_orders = self.order_gateway.fetch_orders(
            material_code=material_code or None,
            keyword=keyword or None,
            limit=requested_count,
        )
        if len(erp_orders) == 0:
            raise bad_request(
                code="ERP_PRODUCTION_ORDERS_EMPTY",
                message="ERP production order list is empty.",
            )

        normalized_keyword = keyword.lower()
        matched_orders: list[dict[str, Any]] = []
        for row in erp_orders:
            row_material_code = str(row.get("material_code") or "").strip().upper()
            row_material_name = str(row.get("material_name") or "").strip()
            if material_code and row_material_code != material_code:
                continue
            if normalized_keyword and normalized_keyword not in row_material_name.lower():
                continue
            matched_orders.append(row)

        selected_orders = matched_orders[:requested_count]
        updated_at = utc_now()
        imported_order_nos: list[str] = []
        order_qty_list: list[float] = []
        with transaction(self.connection):
            for row in selected_orders:
                order_no = str(row.get("production_order_no") or "").strip()
                if not order_no:
                    continue
                row_material_code = str(row.get("material_code") or "").strip().upper()
                row_material_name = str(row.get("material_name") or row_material_code).strip() or row_material_code
                order_qty = _to_number(row.get("production_qty"), 0)
                if order_qty <= 0:
                    continue
                start_date = _normalize_date_text(row.get("planned_start_date")) or _today_text()
                end_date = _normalize_date_text(row.get("planned_end_date")) or start_date
                source_bill_no = str(row.get("source_bill_no") or "").strip() or None
                material_list_no = str(row.get("material_list_no") or "").strip() or None
                normalized_status = "DONE" if completed else "OPEN"
                self.connection.execute(
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
                    (
                        order_no,
                        row_material_code,
                        row_material_name,
                        row.get("material_specification"),
                        order_qty,
                        normalized_status,
                        start_date,
                        end_date,
                        source_bill_no,
                        material_list_no,
                        updated_at,
                    ),
                )
                self._upsert_order_state(
                    {
                        "production_order_no": order_no,
                        "promised_due_date": end_date,
                        "expected_start_date": start_date,
                        "expected_start_time": _iso_at(start_date, "08:00:00"),
                        "expected_finish_time": _iso_at(end_date, "18:00:00"),
                        "urgent_flag": 0,
                        "lock_flag": 0,
                        "frozen_flag": 0,
                        "status": normalized_status,
                        "order_status": normalized_status,
                        "completed_qty": order_qty if completed else 0,
                        "remaining_qty": 0 if completed else order_qty,
                        "progress_rate": 100 if completed else 0,
                        "production_batch_no": f"{source_bill_no}-B1" if source_bill_no else None,
                    }
                )
                imported_order_nos.append(order_no)
                order_qty_list.append(order_qty)
        return {
            "material_code": material_code,
            "keyword": keyword,
            "requested_count": requested_count,
            "matched_count": len(matched_orders),
            "imported_count": len(imported_order_nos),
            "completed": completed,
            "imported_order_nos": imported_order_nos,
            "order_nos": imported_order_nos,
            "order_qty_list": order_qty_list,
        }

    def _require_order(self, order_no: str) -> dict[str, Any]:
        row = fetch_one(
            self.connection,
            """
            SELECT
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
            FROM production_orders
            WHERE production_order_no = ?
            """,
            (order_no,),
        )
        if row is None:
            raise not_found(
                code="ORDER_NOT_FOUND",
                message="Order does not exist.",
                details={"order_no": order_no},
            )
        return row

    def _list_order_rows(self) -> list[dict[str, Any]]:
        return fetch_all(
            self.connection,
            """
            SELECT
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
            FROM production_orders
            ORDER BY updated_at DESC, production_order_no DESC
            """,
        )

    def _get_order_state(self, order_no: str) -> dict[str, Any] | None:
        return fetch_one(
            self.connection,
            """
            SELECT
                production_order_no,
                promised_due_date,
                expected_start_date,
                expected_start_time,
                expected_finish_time,
                urgent_flag,
                lock_flag,
                frozen_flag,
                status,
                order_status,
                completed_qty,
                remaining_qty,
                progress_rate,
                production_batch_no,
                updated_at
            FROM order_pool_state
            WHERE production_order_no = ?
            """,
            (order_no,),
        )

    def _get_order_state_map(self, order_nos: list[str]) -> dict[str, dict[str, Any]]:
        if len(order_nos) == 0:
            return {}
        placeholders = ",".join("?" for _ in order_nos)
        rows = fetch_all(
            self.connection,
            f"""
            SELECT
                production_order_no,
                promised_due_date,
                expected_start_date,
                expected_start_time,
                expected_finish_time,
                urgent_flag,
                lock_flag,
                frozen_flag,
                status,
                order_status,
                completed_qty,
                remaining_qty,
                progress_rate,
                production_batch_no,
                updated_at
            FROM order_pool_state
            WHERE production_order_no IN ({placeholders})
            """,
            tuple(order_nos),
        )
        return {str(row["production_order_no"]): row for row in rows}

    def _upsert_order_state(self, row: dict[str, Any]) -> None:
        updated_at = utc_now()
        self.connection.execute(
            """
            INSERT INTO order_pool_state (
                production_order_no,
                promised_due_date,
                expected_start_date,
                expected_start_time,
                expected_finish_time,
                urgent_flag,
                lock_flag,
                frozen_flag,
                status,
                order_status,
                completed_qty,
                remaining_qty,
                progress_rate,
                production_batch_no,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(production_order_no) DO UPDATE SET
                promised_due_date = excluded.promised_due_date,
                expected_start_date = excluded.expected_start_date,
                expected_start_time = excluded.expected_start_time,
                expected_finish_time = excluded.expected_finish_time,
                urgent_flag = excluded.urgent_flag,
                lock_flag = excluded.lock_flag,
                frozen_flag = excluded.frozen_flag,
                status = excluded.status,
                order_status = excluded.order_status,
                completed_qty = excluded.completed_qty,
                remaining_qty = excluded.remaining_qty,
                progress_rate = excluded.progress_rate,
                production_batch_no = excluded.production_batch_no,
                updated_at = excluded.updated_at
            """,
            (
                row["production_order_no"],
                row.get("promised_due_date"),
                row.get("expected_start_date"),
                row.get("expected_start_time"),
                row.get("expected_finish_time"),
                int(row.get("urgent_flag") or 0),
                int(row.get("lock_flag") or 0),
                int(row.get("frozen_flag") or 0),
                row.get("status"),
                row.get("order_status"),
                row.get("completed_qty"),
                row.get("remaining_qty"),
                row.get("progress_rate"),
                row.get("production_batch_no"),
                updated_at,
            ),
        )

    def _get_capacity_rows(self, order_no: str) -> list[dict[str, Any]]:
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
            ORDER BY process_code ASC, workshop_code ASC, line_code ASC
            """,
            (order_no,),
        )

    def _get_capacity_map(self, order_nos: list[str]) -> dict[str, list[dict[str, Any]]]:
        if len(order_nos) == 0:
            return {}
        placeholders = ",".join("?" for _ in order_nos)
        rows = fetch_all(
            self.connection,
            f"""
            SELECT
                production_order_no,
                process_code,
                process_name,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                capacity_qty
            FROM capacity_bindings
            WHERE production_order_no IN ({placeholders})
            ORDER BY production_order_no ASC, process_code ASC, workshop_code ASC, line_code ASC
            """,
            tuple(order_nos),
        )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row["production_order_no"])].append(row)
        return grouped

    def _build_order_pool_row(
        self,
        *,
        base_row: dict[str, Any],
        state_row: dict[str, Any] | None,
        capacity_rows: list[dict[str, Any]],
        route_rows: list[dict[str, Any]],
        topology_by_process: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        production_qty = _to_number(base_row.get("production_qty"), 0)
        completed_qty = (
            _to_number((state_row or {}).get("completed_qty"), 0)
            if (state_row or {}).get("completed_qty") is not None
            else 0
        )
        remaining_qty = (state_row or {}).get("remaining_qty")
        if remaining_qty is None:
            remaining_qty = max(0, production_qty - completed_qty)
        progress_rate = (state_row or {}).get("progress_rate")
        if progress_rate is None:
            progress_rate = (completed_qty / production_qty * 100) if production_qty > 0 else 0
        promised_due_date = (
            (state_row or {}).get("promised_due_date") or base_row.get("planned_end_date")
        )
        expected_start_date = (
            (state_row or {}).get("expected_start_date") or base_row.get("planned_start_date")
        )
        expected_start_time = (
            (state_row or {}).get("expected_start_time")
            or _iso_at(expected_start_date, "08:00:00")
        )
        expected_finish_time = (
            (state_row or {}).get("expected_finish_time")
            or _iso_at(promised_due_date, "18:00:00")
        )
        status = str(
            (state_row or {}).get("status")
            or (state_row or {}).get("order_status")
            or base_row.get("status")
            or "OPEN"
        ).strip().upper()
        order_status = str(
            (state_row or {}).get("order_status") or status
        ).strip().upper()
        source_bill_no = str(base_row.get("source_bill_no") or "").strip()
        return {
            "order_no": base_row["production_order_no"],
            "product_code": base_row["material_code"],
            "product_name_cn": base_row["material_name"],
            "product_name": base_row["material_name"],
            "order_qty": production_qty,
            "completed_qty": completed_qty,
            "remaining_qty": remaining_qty,
            "progress_rate": progress_rate,
            "promised_due_date": promised_due_date,
            "expected_start_time": expected_start_time,
            "expected_finish_time": expected_finish_time,
            "expected_start_date": expected_start_date,
            "urgent_flag": int((state_row or {}).get("urgent_flag") or 0),
            "lock_flag": int((state_row or {}).get("lock_flag") or 0),
            "frozen_flag": int((state_row or {}).get("frozen_flag") or 0),
            "status": status,
            "order_status": order_status,
            "production_batch_no": (state_row or {}).get("production_batch_no")
            or (f"{source_bill_no}-B1" if source_bill_no else "-"),
            "process_contexts": self._build_process_contexts(
                order_no=str(base_row["production_order_no"]),
                product_code=str(base_row["material_code"]),
                capacity_rows=capacity_rows,
                route_rows=route_rows,
                topology_by_process=topology_by_process,
            ),
        }

    def _build_process_contexts(
        self,
        *,
        order_no: str,
        product_code: str,
        capacity_rows: list[dict[str, Any]],
        route_rows: list[dict[str, Any]],
        topology_by_process: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        capacity_row_by_process = self._best_capacity_row_by_process(capacity_rows)

        if route_rows:
            contexts: list[dict[str, Any]] = []
            for index, row in enumerate(route_rows):
                process_code = str(row.get("process_code") or "").strip().upper()
                if not process_code:
                    continue
                topology_row = topology_by_process.get(process_code, {})
                capacity_row = capacity_row_by_process.get(process_code, {})
                capacity_per_shift = _to_number(
                    capacity_row.get("capacity_qty"),
                    _to_number(topology_row.get("capacity_per_shift"), 0),
                )
                contexts.append(
                    {
                        "sequence_no": index + 1,
                        "process_code": process_code,
                        "process_name_cn": (
                            str(
                                row.get("process_name_cn")
                                or capacity_row.get("process_name")
                                or process_code
                            ).strip()
                            or process_code
                        ),
                        "workshop_code": str(
                            capacity_row.get("workshop_code")
                            or topology_row.get("workshop_code")
                            or "-"
                        ).strip()
                        or "-",
                        "line_code": str(
                            capacity_row.get("line_code")
                            or topology_row.get("line_code")
                            or "-"
                        ).strip()
                        or "-",
                        "dependency_type": str(row.get("dependency_type") or "FS").strip().upper() or "FS",
                        "capacity_per_shift": capacity_per_shift,
                    }
                )
            return contexts

        contexts = []
        deduplicated_rows = sorted(
            capacity_row_by_process.values(),
            key=lambda item: str(item.get("process_code") or ""),
        )
        for index, row in enumerate(deduplicated_rows):
            process_code = str(row.get("process_code") or "").strip().upper()
            if not process_code:
                continue
            contexts.append(
                {
                    "sequence_no": index + 1,
                    "process_code": process_code,
                    "process_name_cn": str(row.get("process_name") or process_code).strip() or process_code,
                    "workshop_code": str(row.get("workshop_code") or "-").strip() or "-",
                    "line_code": str(row.get("line_code") or "-").strip() or "-",
                    "dependency_type": "FS",
                    "capacity_per_shift": _to_number(row.get("capacity_qty"), 0),
                }
            )
        return contexts

    def _build_schedule_process_contexts(
        self,
        *,
        order_no: str,
        product_code: str,
        capacity_rows: list[dict[str, Any]],
        route_rows: list[dict[str, Any]],
        topology_by_process: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(route_rows) == 0:
            raise server_error(
                code="SCHEDULE_ROUTE_REQUIRED",
                message="Process route is required for schedule generation.",
                details={"order_no": order_no, "product_code": product_code},
            )

        contexts = self._build_process_contexts(
            order_no=order_no,
            product_code=product_code,
            capacity_rows=capacity_rows,
            route_rows=route_rows,
            topology_by_process=topology_by_process,
        )
        if len(contexts) == 0:
            raise server_error(
                code="SCHEDULE_PROCESS_CONTEXTS_EMPTY",
                message="No process contexts available for schedule generation.",
                details={"order_no": order_no, "product_code": product_code},
            )

        for context in contexts:
            process_code = str(context.get("process_code") or "").strip().upper()
            workshop_code = str(context.get("workshop_code") or "").strip().upper()
            line_code = str(context.get("line_code") or "").strip().upper()
            capacity_per_shift = _to_number(context.get("capacity_per_shift"), 0)
            if not process_code:
                raise server_error(
                    code="SCHEDULE_PROCESS_CODE_REQUIRED",
                    message="Process code is missing in schedule process context.",
                    details={"order_no": order_no, "product_code": product_code},
                )
            if not workshop_code or workshop_code == "-":
                raise server_error(
                    code="SCHEDULE_WORKSHOP_CODE_REQUIRED",
                    message="Workshop code is missing in schedule process context.",
                    details={
                        "order_no": order_no,
                        "product_code": product_code,
                        "process_code": process_code,
                    },
                )
            if not line_code or line_code == "-":
                raise server_error(
                    code="SCHEDULE_LINE_CODE_REQUIRED",
                    message="Line code is missing in schedule process context.",
                    details={
                        "order_no": order_no,
                        "product_code": product_code,
                        "process_code": process_code,
                    },
                )
            if capacity_per_shift <= SCHEDULE_NUMBER_EPSILON:
                raise server_error(
                    code="SCHEDULE_CAPACITY_PER_SHIFT_INVALID",
                    message="capacity_per_shift must be greater than 0 for all scheduled processes.",
                    details={
                        "order_no": order_no,
                        "product_code": product_code,
                        "process_code": process_code,
                        "capacity_per_shift": capacity_per_shift,
                    },
                )
            context["workshop_code"] = workshop_code
            context["line_code"] = line_code
            context["process_code"] = process_code
            context["capacity_per_shift"] = capacity_per_shift
        return contexts

    def _refresh_bom_children(self, parent_material_code: str) -> None:
        children = self.factory.material_gateway.fetch_bom_children(parent_material_code)
        child_codes = [str(item["child_material_code"]) for item in children]
        supply_rows = self.factory.supply_gateway.fetch_material_supply(child_codes)
        supply_map = {str(row["material_code"]): row for row in supply_rows}
        updated_at = utc_now()
        rows_to_store: list[dict[str, Any]] = []
        normalized_supply_rows: list[dict[str, Any]] = []
        for row in supply_rows:
            normalized_supply_rows.append(
                {
                    "material_code": str(row["material_code"]),
                    "supply_type_code": row["supply_type_code"],
                    "supply_type_name": row["supply_type_name"],
                    "snapshot_time": updated_at,
                    "updated_at": updated_at,
                }
            )
        for index, item in enumerate(children):
            material_code = str(item["child_material_code"])
            supply_row = supply_map.get(material_code, {})
            supply_type_code = item.get("supply_type_code") or supply_row.get("supply_type_code")
            supply_type_name = item.get("supply_type_name") or supply_row.get("supply_type_name")
            if not supply_type_code or not supply_type_name:
                raise bad_request(
                    code="SUPPLY_TYPE_MISSING",
                    message="Supply type is missing in ERP BOM refresh result.",
                    details={"material_code": material_code},
                )
            rows_to_store.append(
                {
                    "parent_material_code": parent_material_code,
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
        with transaction(self.connection):
            self.factory.supply_repository.upsert_many(normalized_supply_rows)
            self.factory.bom_children_repository.replace_for_parent(
                parent_material_code,
                rows_to_store,
            )

    def _process_name_by_code(self) -> dict[str, str]:
        names: dict[str, str] = {}
        for row in self._list_route_rows():
            process_code = str(row.get("process_code") or "").strip().upper()
            if process_code and process_code not in names:
                names[process_code] = str(row.get("process_name_cn") or process_code)
        for row in fetch_all(
            self.connection,
            """
            SELECT DISTINCT process_code, process_name
            FROM capacity_bindings
            WHERE process_code IS NOT NULL
            """,
        ):
            process_code = str(row.get("process_code") or "").strip().upper()
            if process_code and process_code not in names:
                names[process_code] = str(row.get("process_name") or process_code)
        return names

    def _normalize_strategy_code(self, value: object) -> str:
        normalized = str(value or "KEY_ORDER_FIRST").strip().upper() or "KEY_ORDER_FIRST"
        if normalized not in SUPPORTED_STRATEGY_CODES:
            raise bad_request(
                code="SCHEDULE_STRATEGY_INVALID",
                message="strategy_code is invalid.",
                details={
                    "strategy_code": normalized,
                    "supported": sorted(SUPPORTED_STRATEGY_CODES),
                },
            )
        return normalized

    def _normalize_weekend_rest_mode(self, value: object) -> str:
        normalized = str(value or "DOUBLE").strip().upper() or "DOUBLE"
        if normalized not in WEEKEND_REST_MODES:
            raise bad_request(
                code="WEEKEND_REST_MODE_INVALID",
                message="weekend_rest_mode is invalid.",
                details={
                    "weekend_rest_mode": normalized,
                    "supported": sorted(WEEKEND_REST_MODES),
                },
            )
        return normalized

    def _normalize_date_shift_mode(self, value: object) -> str:
        normalized = str(value or "").strip().upper()
        if normalized not in DATE_SHIFT_MODES:
            raise bad_request(
                code="DATE_SHIFT_MODE_INVALID",
                message="date_shift_mode is invalid.",
                details={
                    "date_shift_mode": normalized,
                    "supported": sorted(DATE_SHIFT_MODES),
                },
            )
        return normalized

    def _normalize_date_shift_mode_by_date(self, value: object) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise bad_request(
                code="DATE_SHIFT_MODE_BY_DATE_INVALID",
                message="date_shift_mode_by_date must be an object.",
            )
        out: dict[str, str] = {}
        for key, mode_value in value.items():
            date_text = _normalize_date_text(key)
            if not date_text:
                raise bad_request(
                    code="DATE_SHIFT_MODE_DATE_INVALID",
                    message="date_shift_mode_by_date contains invalid date key.",
                    details={"date": str(key)},
                )
            out[date_text] = self._normalize_date_shift_mode(mode_value)
        return out

    def _build_planning_rules_from_current_config(self) -> dict[str, Any]:
        row = self._get_rules_row()
        return {
            "skip_statutory_holidays": bool(row.get("skip_statutory_holidays")),
            "weekend_rest_mode": self._normalize_weekend_rest_mode(
                row.get("weekend_rest_mode")
            ),
            "date_shift_mode_by_date": self._normalize_date_shift_mode_by_date(
                loads(row.get("date_shift_mode_by_date_json") or "{}")
            ),
        }

    def _best_capacity_row_by_process(
        self,
        capacity_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in capacity_rows:
            process_code = str(row.get("process_code") or "").strip().upper()
            if not process_code:
                continue
            current = out.get(process_code)
            next_capacity = _to_number(row.get("capacity_qty"), 0)
            if current is None:
                out[process_code] = row
                continue
            current_capacity = _to_number(current.get("capacity_qty"), 0)
            if next_capacity > current_capacity:
                out[process_code] = row
        return out

    def _enabled_topology_by_process(
        self,
        topology_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in topology_rows:
            if int(_to_number(row.get("enabled_flag"), 0)) != 1:
                continue
            process_code = str(row.get("process_code") or "").strip().upper()
            if not process_code:
                continue
            current = out.get(process_code)
            next_capacity = _to_number(row.get("capacity_per_shift"), 0)
            if current is None:
                out[process_code] = row
                continue
            current_capacity = _to_number(current.get("capacity_per_shift"), 0)
            if next_capacity > current_capacity:
                out[process_code] = row
        return out

    def _build_base_schedule_hints(self, version_no: str) -> dict[str, dict[str, Any]]:
        rows = fetch_all(
            self.connection,
            """
            SELECT
                task_no,
                production_order_no,
                process_code,
                calendar_date,
                shift_code
            FROM schedule_tasks
            WHERE version_no = ?
            ORDER BY task_no ASC
            """,
            (version_no,),
        )
        hints: dict[str, dict[str, Any]] = {}
        for row in rows:
            order_no = str(row.get("production_order_no") or "").strip()
            process_code = str(row.get("process_code") or "").strip().upper()
            calendar_date = _normalize_date_text(row.get("calendar_date"))
            if not order_no or not process_code or not calendar_date:
                raise server_error(
                    code="BASE_SCHEDULE_TASK_INVALID",
                    message="Base schedule task is invalid.",
                    details={"version_no": version_no, "task_no": row.get("task_no")},
                )
            shift_code = _normalize_shift_code(row.get("shift_code"))
            slot_index = _slot_index_from_text(calendar_date, shift_code)
            task_no = int(_to_number(row.get("task_no"), 0))
            hint = hints.setdefault(
                order_no,
                {
                    "first_task_no": task_no,
                    "first_slot": slot_index,
                    "process_first_slot": {},
                },
            )
            if task_no < int(hint["first_task_no"]):
                hint["first_task_no"] = task_no
            if slot_index < int(hint["first_slot"]):
                hint["first_slot"] = slot_index
            process_first_slot = hint["process_first_slot"]
            existing_process_slot = process_first_slot.get(process_code)
            if existing_process_slot is None or slot_index < int(existing_process_slot):
                process_first_slot[process_code] = slot_index
        return hints

    def _resolve_day_shift_mode(
        self,
        *,
        date_text: str,
        planning_rules: dict[str, Any],
        day_mode_cache: dict[str, str],
    ) -> str:
        cached = day_mode_cache.get(date_text)
        if cached:
            return cached

        date_shift_mode_by_date = planning_rules["date_shift_mode_by_date"]
        manual_mode = date_shift_mode_by_date.get(date_text)
        if manual_mode:
            day_mode_cache[date_text] = manual_mode
            return manual_mode

        mode = "DAY"
        if planning_rules["skip_statutory_holidays"] is True:
            year_value = int(date_text[:4])
            if year_value not in SUPPORTED_CN_HOLIDAY_YEARS:
                raise bad_request(
                    code="HOLIDAY_YEAR_UNSUPPORTED",
                    message="Statutory holiday data is unsupported for schedule date.",
                    details={"year": year_value, "date": date_text},
                )
            if self._is_cn_statutory_holiday(date_text):
                mode = "REST"
            else:
                weekday = date.fromisoformat(date_text).weekday()
                weekend_mode = planning_rules["weekend_rest_mode"]
                if weekend_mode == "DOUBLE" and weekday in (5, 6):
                    mode = "REST"
                elif weekend_mode == "SINGLE" and weekday == 6:
                    mode = "REST"

        day_mode_cache[date_text] = mode
        return mode

    def _allowed_shifts_for_day_mode(self, mode: str) -> tuple[str, ...]:
        if mode == "REST":
            return ()
        if mode == "BOTH":
            return ("DAY", "NIGHT")
        if mode == "NIGHT":
            return ("NIGHT",)
        return ("DAY",)

    def _next_working_slot(
        self,
        *,
        start_slot: int,
        planning_rules: dict[str, Any],
        day_mode_cache: dict[str, str],
    ) -> tuple[int, str, str]:
        slot_cursor = max(0, int(start_slot))
        for _ in range(SCHEDULE_SLOT_SEARCH_GUARD):
            day_value, shift_code = _slot_to_date_shift(slot_cursor)
            date_text = day_value.isoformat()
            day_mode = self._resolve_day_shift_mode(
                date_text=date_text,
                planning_rules=planning_rules,
                day_mode_cache=day_mode_cache,
            )
            if shift_code in self._allowed_shifts_for_day_mode(day_mode):
                return slot_cursor, date_text, shift_code
            slot_cursor += 1
        raise server_error(
            code="SCHEDULE_WORKING_SLOT_NOT_FOUND",
            message="Cannot find working slot under current calendar rules.",
            details={"start_slot": start_slot},
        )

    def _allocate_process_tasks(
        self,
        *,
        order_no: str,
        process_context: dict[str, Any],
        required_qty: float,
        first_slot: int,
        planning_rules: dict[str, Any],
        day_mode_cache: dict[str, str],
        used_capacity_by_slot: dict[tuple[int, str, str, str], float],
    ) -> tuple[list[dict[str, Any]], int]:
        remaining_qty = max(0.0, _to_number(required_qty, 0))
        if remaining_qty <= SCHEDULE_NUMBER_EPSILON:
            return [], int(first_slot)

        process_code = str(process_context.get("process_code") or "").strip().upper()
        workshop_code = str(process_context.get("workshop_code") or "").strip().upper()
        line_code = str(process_context.get("line_code") or "").strip().upper()
        capacity_per_shift = _to_number(process_context.get("capacity_per_shift"), 0)
        if capacity_per_shift <= SCHEDULE_NUMBER_EPSILON:
            raise server_error(
                code="SCHEDULE_CAPACITY_PER_SHIFT_INVALID",
                message="capacity_per_shift must be greater than 0 for all scheduled processes.",
                details={"order_no": order_no, "process_code": process_code},
            )

        allocations: list[dict[str, Any]] = []
        slot_cursor = max(0, int(first_slot))
        last_slot = slot_cursor
        loop_guard = 0
        while remaining_qty > SCHEDULE_NUMBER_EPSILON:
            if loop_guard >= SCHEDULE_SLOT_SEARCH_GUARD:
                raise server_error(
                    code="SCHEDULE_ALLOCATION_GUARD_EXCEEDED",
                    message="Unable to allocate process workload within slot guard limit.",
                    details={
                        "order_no": order_no,
                        "process_code": process_code,
                        "remaining_qty": remaining_qty,
                    },
                )
            slot_index, calendar_date, shift_code = self._next_working_slot(
                start_slot=slot_cursor,
                planning_rules=planning_rules,
                day_mode_cache=day_mode_cache,
            )
            key = (slot_index, workshop_code, line_code, process_code)
            used_capacity = _to_number(used_capacity_by_slot.get(key), 0)
            available_capacity = max(0.0, capacity_per_shift - used_capacity)
            if available_capacity <= SCHEDULE_NUMBER_EPSILON:
                slot_cursor = slot_index + 1
                loop_guard += 1
                continue

            planned_qty = min(remaining_qty, available_capacity)
            used_capacity_by_slot[key] = used_capacity + planned_qty
            allocations.append(
                {
                    "calendar_date": calendar_date,
                    "shift_code": shift_code,
                    "plan_qty": planned_qty,
                }
            )
            remaining_qty -= planned_qty
            last_slot = slot_index
            slot_cursor = slot_index + 1
            loop_guard += 1

        return allocations, last_slot

    def _sort_schedule_candidates(
        self,
        *,
        strategy_code: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        def updated_rank(text: str) -> float:
            safe_text = str(text or "").strip()
            if not safe_text:
                return 0.0
            try:
                return datetime.fromisoformat(safe_text.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return 0.0

        if strategy_code == "KEY_ORDER_FIRST":
            return sorted(
                candidates,
                key=lambda item: (
                    -int(item.get("frozen_flag") or 0),
                    -int(item.get("lock_flag") or 0),
                    -int(item.get("urgent_flag") or 0),
                    int(item.get("base_first_task_no") or 10**9),
                    item.get("start_date"),
                    item.get("due_date"),
                    -updated_rank(str(item.get("updated_at") or "")),
                    str(item.get("order_no") or ""),
                ),
            )
        if strategy_code == "MAX_CAPACITY_FIRST":
            return sorted(
                candidates,
                key=lambda item: (
                    -int(item.get("frozen_flag") or 0),
                    -int(item.get("lock_flag") or 0),
                    -int(item.get("urgent_flag") or 0),
                    -_to_number(item.get("total_capacity_per_shift"), 0),
                    -_to_number(item.get("min_capacity_per_shift"), 0),
                    int(item.get("base_first_task_no") or 10**9),
                    item.get("start_date"),
                    item.get("due_date"),
                    str(item.get("order_no") or ""),
                ),
            )
        if strategy_code == "MIN_DELAY_FIRST":
            return sorted(
                candidates,
                key=lambda item: (
                    -int(item.get("frozen_flag") or 0),
                    -int(item.get("lock_flag") or 0),
                    -int(item.get("urgent_flag") or 0),
                    int(_to_number(item.get("slack_days"), 0)),
                    item.get("due_date"),
                    item.get("start_date"),
                    int(item.get("base_first_task_no") or 10**9),
                    str(item.get("order_no") or ""),
                ),
            )
        raise bad_request(
            code="SCHEDULE_STRATEGY_INVALID",
            message="strategy_code is invalid.",
            details={"strategy_code": strategy_code},
        )

    def _first_available_slot_for_process(
        self,
        *,
        process_context: dict[str, Any],
        start_slot: int,
        planning_rules: dict[str, Any],
        day_mode_cache: dict[str, str],
        used_capacity_by_slot: dict[tuple[int, str, str, str], float],
    ) -> int:
        process_code = str(process_context.get("process_code") or "").strip().upper()
        workshop_code = str(process_context.get("workshop_code") or "").strip().upper()
        line_code = str(process_context.get("line_code") or "").strip().upper()
        capacity_per_shift = _to_number(process_context.get("capacity_per_shift"), 0)
        if capacity_per_shift <= SCHEDULE_NUMBER_EPSILON:
            raise server_error(
                code="SCHEDULE_CAPACITY_PER_SHIFT_INVALID",
                message="capacity_per_shift must be greater than 0 for all scheduled processes.",
                details={"process_code": process_code},
            )

        slot_cursor = max(0, int(start_slot))
        for _ in range(SCHEDULE_SLOT_SEARCH_GUARD):
            slot_index, _, shift_code = self._next_working_slot(
                start_slot=slot_cursor,
                planning_rules=planning_rules,
                day_mode_cache=day_mode_cache,
            )
            key = (slot_index, workshop_code, line_code, process_code)
            used_capacity = _to_number(used_capacity_by_slot.get(key), 0)
            available_capacity = max(0.0, capacity_per_shift - used_capacity)
            if available_capacity > SCHEDULE_NUMBER_EPSILON:
                return slot_index
            slot_cursor = slot_index + 1
        raise server_error(
            code="SCHEDULE_WORKING_SLOT_NOT_FOUND",
            message="Cannot find available slot for process.",
            details={"process_code": process_code, "start_slot": start_slot},
        )

    def _candidate_runtime_metrics(
        self,
        *,
        candidate: dict[str, Any],
        planning_rules: dict[str, Any],
        day_mode_cache: dict[str, str],
        used_capacity_by_slot: dict[tuple[int, str, str, str], float],
    ) -> dict[str, int]:
        process_contexts = candidate["process_contexts"]
        if len(process_contexts) == 0:
            raise server_error(
                code="SCHEDULE_PROCESS_CONTEXTS_EMPTY",
                message="No process contexts available for schedule candidate.",
                details={"order_no": candidate.get("order_no")},
            )

        first_context = process_contexts[0]
        first_process_code = str(first_context.get("process_code") or "").strip().upper()
        first_slot = int(candidate.get("start_slot") or 0)
        base_process_first_slot = candidate.get("base_process_first_slot", {})
        first_process_base_slot = base_process_first_slot.get(first_process_code)
        if (
            (int(candidate.get("lock_flag") or 0) == 1 or int(candidate.get("frozen_flag") or 0) == 1)
            and first_process_base_slot is not None
        ):
            first_slot = max(first_slot, int(first_process_base_slot))

        first_ready_slot = self._first_available_slot_for_process(
            process_context=first_context,
            start_slot=first_slot,
            planning_rules=planning_rules,
            day_mode_cache=day_mode_cache,
            used_capacity_by_slot=used_capacity_by_slot,
        )
        required_shifts = max(1, int(_to_number(candidate.get("required_shifts"), 1)))
        projected_finish_slot = first_ready_slot + required_shifts - 1
        due_date = candidate.get("due_date")
        if not isinstance(due_date, date):
            due_date = _parse_date_or_today(due_date)
        due_slot = _slot_index_for(due_date, "NIGHT")
        projected_lateness_slots = projected_finish_slot - due_slot
        projected_slack_slots = due_slot - projected_finish_slot
        return {
            "first_ready_slot": first_ready_slot,
            "projected_finish_slot": projected_finish_slot,
            "due_slot": due_slot,
            "projected_lateness_slots": projected_lateness_slots,
            "projected_slack_slots": projected_slack_slots,
        }

    def _select_next_candidate_index(
        self,
        *,
        strategy_code: str,
        candidates: list[dict[str, Any]],
        planning_rules: dict[str, Any],
        day_mode_cache: dict[str, str],
        used_capacity_by_slot: dict[tuple[int, str, str, str], float],
    ) -> int:
        if len(candidates) == 0:
            raise server_error(
                code="SCHEDULE_CANDIDATE_EMPTY",
                message="No schedule candidates available.",
            )

        best_index = 0
        best_key: tuple[Any, ...] | None = None
        for index, candidate in enumerate(candidates):
            metrics = self._candidate_runtime_metrics(
                candidate=candidate,
                planning_rules=planning_rules,
                day_mode_cache=day_mode_cache,
                used_capacity_by_slot=used_capacity_by_slot,
            )
            late_slots = int(metrics["projected_lateness_slots"])
            late_rank = 0 if late_slots > 0 else 1
            late_severity = -max(late_slots, 0)
            business_head = (
                -int(candidate.get("frozen_flag") or 0),
                -int(candidate.get("lock_flag") or 0),
                -int(candidate.get("urgent_flag") or 0),
            )
            base_tail = (
                int(candidate.get("base_first_task_no") or 10**9),
                str(candidate.get("order_no") or ""),
            )

            if strategy_code == "KEY_ORDER_FIRST":
                key = (
                    *business_head,
                    late_rank,
                    late_severity,
                    int(metrics["due_slot"]),
                    int(metrics["first_ready_slot"]),
                    *base_tail,
                )
            elif strategy_code == "MAX_CAPACITY_FIRST":
                key = (
                    *business_head,
                    late_rank,
                    late_severity,
                    -_to_number(candidate.get("total_capacity_per_shift"), 0),
                    int(_to_number(candidate.get("required_shifts"), 0)),
                    int(metrics["due_slot"]),
                    int(metrics["first_ready_slot"]),
                    *base_tail,
                )
            elif strategy_code == "MIN_DELAY_FIRST":
                key = (
                    *business_head,
                    late_rank,
                    late_severity,
                    int(metrics["projected_slack_slots"]),
                    int(metrics["due_slot"]),
                    int(metrics["first_ready_slot"]),
                    *base_tail,
                )
            else:
                raise bad_request(
                    code="SCHEDULE_STRATEGY_INVALID",
                    message="strategy_code is invalid.",
                    details={"strategy_code": strategy_code},
                )

            if best_key is None or key < best_key:
                best_key = key
                best_index = index

        return best_index

    def _is_cn_statutory_holiday(self, date_text: str) -> bool:
        return date_text in CN_STATUTORY_HOLIDAY_DATE_SET

    def _get_rules_row(self) -> dict[str, Any]:
        row = fetch_one(
            self.connection,
            """
            SELECT
                singleton_key,
                horizon_start_date,
                horizon_days,
                skip_statutory_holidays,
                weekend_rest_mode,
                date_shift_mode_by_date_json,
                updated_at
            FROM schedule_calendar_rules
            WHERE singleton_key = ?
            """,
            (RULES_SINGLETON_KEY,),
        )
        if row is not None:
            return row
        with transaction(self.connection):
            self.connection.execute(
                """
                INSERT INTO schedule_calendar_rules (
                    singleton_key,
                    horizon_start_date,
                    horizon_days,
                    skip_statutory_holidays,
                    weekend_rest_mode,
                    date_shift_mode_by_date_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    RULES_SINGLETON_KEY,
                    _today_text(),
                    31,
                    0,
                    "DOUBLE",
                    "{}",
                    utc_now(),
                ),
            )
        return self._get_rules_row()

    def _get_simulation_state(self) -> dict[str, Any]:
        row = fetch_one(
            self.connection,
            """
            SELECT singleton_key, current_date, updated_at
            FROM simulation_state
            WHERE singleton_key = ?
            """,
            (RULES_SINGLETON_KEY,),
        )
        if row is not None:
            return row
        with transaction(self.connection):
            self.connection.execute(
                """
                INSERT INTO simulation_state (
                    singleton_key,
                    current_date,
                    updated_at
                ) VALUES (?, ?, ?)
                """,
                (RULES_SINGLETON_KEY, _today_text(), utc_now()),
            )
        return self._get_simulation_state()

    def _ensure_masterdata_seeded(self) -> None:
        topology_count = fetch_one(
            self.connection,
            "SELECT COUNT(1) AS total FROM masterdata_line_topology",
        )
        route_count = fetch_one(
            self.connection,
            "SELECT COUNT(1) AS total FROM masterdata_process_routes",
        )
        need_topology_seed = int(topology_count["total"]) == 0
        need_route_seed = int(route_count["total"]) == 0
        if not need_topology_seed and not need_route_seed:
            return

        upstream_route_rows = (
            self.masterdata_gateway.fetch_process_routes()
            if need_topology_seed or need_route_seed
            else []
        )
        upstream_capability_rows = (
            self.masterdata_gateway.fetch_equipment_process_capabilities()
            if need_topology_seed
            else []
        )
        topology_rows = (
            self._build_line_topology_seed_rows(
                upstream_route_rows,
                upstream_capability_rows,
            )
            if need_topology_seed
            else []
        )
        route_rows = (
            self._build_route_seed_rows(upstream_route_rows)
            if need_route_seed
            else []
        )
        if need_topology_seed and len(topology_rows) == 0:
            raise server_error(
                code="MASTERDATA_LINE_TOPOLOGY_EMPTY",
                message="Upstream line topology seed returned no rows.",
            )
        if need_route_seed and len(route_rows) == 0:
            raise server_error(
                code="MASTERDATA_PROCESS_ROUTES_EMPTY",
                message="Upstream process route seed returned no rows.",
            )
        if len(topology_rows) == 0 and len(route_rows) == 0:
            return
        updated_at = utc_now()
        with transaction(self.connection):
            if len(topology_rows) > 0 and need_topology_seed:
                self.connection.executemany(
                    """
                    INSERT INTO masterdata_line_topology (
                        company_code,
                        workshop_code,
                        workshop_name,
                        line_code,
                        line_name,
                        process_code,
                        capacity_per_shift,
                        required_workers,
                        required_machines,
                        enabled_flag,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            row["company_code"],
                            row["workshop_code"],
                            row["workshop_name"],
                            row["line_code"],
                            row["line_name"],
                            row["process_code"],
                            row["capacity_per_shift"],
                            row["required_workers"],
                            row["required_machines"],
                            row["enabled_flag"],
                            updated_at,
                        )
                        for row in topology_rows
                    ],
                )
            if len(route_rows) > 0 and need_route_seed:
                self.connection.executemany(
                    """
                    INSERT INTO masterdata_process_routes (
                        product_code,
                        sequence_no,
                        process_code,
                        process_name_cn,
                        dependency_type,
                        route_no,
                        route_name_cn,
                        product_name_cn,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            row["product_code"],
                            row["sequence_no"],
                            row["process_code"],
                            row["process_name_cn"],
                            row["dependency_type"],
                            row["route_no"],
                            row["route_name_cn"],
                            row["product_name_cn"],
                            updated_at,
                        )
                        for row in route_rows
                    ],
                )

    def _build_route_seed_rows(
        self,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, int, str]] = set()
        for row in rows:
            product_code = str(row.get("product_code") or "").strip().upper()
            process_code = str(row.get("process_code") or "").strip().upper()
            sequence_no = int(_to_number(row.get("sequence_no"), 0))
            if not product_code or not process_code or sequence_no <= 0:
                continue
            key = (product_code, sequence_no, process_code)
            if key in seen:
                continue
            seen.add(key)
            product_name_cn = str(row.get("product_name_cn") or product_code).strip() or product_code
            route_no = str(row.get("route_no") or f"ROUTE-{product_code}").strip() or f"ROUTE-{product_code}"
            route_name_cn = str(row.get("route_name_cn") or product_name_cn).strip() or product_name_cn
            out.append(
                {
                    "product_code": product_code,
                    "sequence_no": sequence_no,
                    "process_code": process_code,
                    "process_name_cn": str(row.get("process_name_cn") or process_code).strip() or process_code,
                    "dependency_type": str(row.get("dependency_type") or "FS").strip().upper() or "FS",
                    "route_no": route_no,
                    "route_name_cn": route_name_cn,
                    "product_name_cn": product_name_cn,
                }
            )
        out.sort(key=lambda item: (str(item["product_code"]), int(item["sequence_no"])))
        return out

    def _build_line_topology_seed_rows(
        self,
        route_rows: list[dict[str, Any]],
        capability_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        route_meta_by_process: dict[str, dict[str, Any]] = {}
        for row in route_rows:
            process_code = str(row.get("process_code") or "").strip().upper()
            if not process_code:
                continue
            current = route_meta_by_process.get(process_code)
            next_meta = {
                "process_name_cn": str(row.get("process_name_cn") or process_code).strip() or process_code,
                "capacity_per_shift": _to_number(row.get("capacity_per_shift"), 0),
                "required_workers": int(_to_number(row.get("required_manpower_per_group"), 0)),
                "required_machines": int(_to_number(row.get("required_equipment_count"), 0)),
            }
            if current is None:
                route_meta_by_process[process_code] = next_meta
                continue
            current["capacity_per_shift"] = max(
                _to_number(current.get("capacity_per_shift"), 0),
                next_meta["capacity_per_shift"],
            )
            current["required_workers"] = max(
                int(_to_number(current.get("required_workers"), 0)),
                next_meta["required_workers"],
            )
            current["required_machines"] = max(
                int(_to_number(current.get("required_machines"), 0)),
                next_meta["required_machines"],
            )
            if not current.get("process_name_cn"):
                current["process_name_cn"] = next_meta["process_name_cn"]

        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for row in capability_rows:
            company_code = str(row.get("company_code") or "COMPANY-MAIN").strip().upper() or "COMPANY-MAIN"
            workshop_code = str(row.get("workshop_code") or "").strip().upper()
            line_code = str(row.get("line_code") or "").strip().upper()
            process_code = str(row.get("process_code") or "").strip().upper()
            if not workshop_code or not line_code or not process_code:
                continue
            meta = route_meta_by_process.get(process_code)
            if meta is None:
                raise server_error(
                    code="MASTERDATA_TOPOLOGY_PROCESS_META_MISSING",
                    message="Missing route metadata for process in line topology seed.",
                    details={"process_code": process_code},
                )
            key = (company_code, workshop_code, line_code, process_code)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "company_code": company_code,
                    "workshop_code": workshop_code,
                    "workshop_name": workshop_code,
                    "line_code": line_code,
                    "line_name": str(row.get("line_name") or line_code).strip() or line_code,
                    "process_code": process_code,
                    "capacity_per_shift": _to_number(meta.get("capacity_per_shift"), 0),
                    "required_workers": int(_to_number(meta.get("required_workers"), 0)),
                    "required_machines": int(_to_number(meta.get("required_machines"), 0)),
                    "enabled_flag": int(_to_number(row.get("enabled_flag"), 0)),
                }
            )
        out.sort(
            key=lambda item: (
                str(item["workshop_code"]),
                str(item["line_code"]),
                str(item["process_code"]),
            )
        )
        return out

    def _list_line_topology_rows(self) -> list[dict[str, Any]]:
        return fetch_all(
            self.connection,
            """
            SELECT
                company_code,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                process_code,
                capacity_per_shift,
                required_workers,
                required_machines,
                enabled_flag
            FROM masterdata_line_topology
            ORDER BY workshop_code ASC, line_code ASC, process_code ASC
            """,
        )

    def _derive_line_topology_rows(self) -> list[dict[str, Any]]:
        rows = fetch_all(
            self.connection,
            """
            SELECT
                workshop_code,
                COALESCE(workshop_name, workshop_code) AS workshop_name,
                line_code,
                COALESCE(line_name, line_code) AS line_name,
                process_code,
                MAX(capacity_qty) AS capacity_per_shift
            FROM capacity_bindings
            WHERE TRIM(COALESCE(workshop_code, '')) <> ''
              AND TRIM(COALESCE(line_code, '')) <> ''
              AND TRIM(COALESCE(process_code, '')) <> ''
            GROUP BY workshop_code, workshop_name, line_code, line_name, process_code
            ORDER BY workshop_code ASC, line_code ASC, process_code ASC
            """,
        )
        return [
            {
                "company_code": "COMPANY-MAIN",
                "workshop_code": str(row["workshop_code"]).strip().upper(),
                "workshop_name": str(row.get("workshop_name") or row["workshop_code"]).strip()
                or str(row["workshop_code"]).strip().upper(),
                "line_code": str(row["line_code"]).strip().upper(),
                "line_name": str(row.get("line_name") or row["line_code"]).strip()
                or str(row["line_code"]).strip().upper(),
                "process_code": str(row["process_code"]).strip().upper(),
                "capacity_per_shift": _to_number(row.get("capacity_per_shift"), 800),
                "required_workers": 4,
                "required_machines": 1,
                "enabled_flag": 1,
            }
            for row in rows
        ]

    def _first_topology_by_process(
        self,
        rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            process_code = str(row.get("process_code") or "").strip().upper()
            if process_code and process_code not in out:
                out[process_code] = row
        return out

    def _list_route_rows(self) -> list[dict[str, Any]]:
        rows = fetch_all(
            self.connection,
            """
            SELECT
                product_code,
                sequence_no,
                process_code,
                process_name_cn,
                dependency_type,
                route_no,
                route_name_cn,
                product_name_cn
            FROM masterdata_process_routes
            ORDER BY product_code ASC, sequence_no ASC
            """,
        )
        return [
            {
                "id": _route_row_id(str(row["product_code"]), int(row["sequence_no"])),
                **row,
            }
            for row in rows
        ]

    def _derive_route_rows(self) -> list[dict[str, Any]]:
        rows = fetch_all(
            self.connection,
            """
            SELECT
                po.material_code AS product_code,
                COALESCE(po.material_name, po.material_code) AS product_name_cn,
                cb.process_code,
                COALESCE(cb.process_name, cb.process_code) AS process_name_cn,
                cb.workshop_code,
                cb.line_code
            FROM production_orders po
            JOIN capacity_bindings cb
              ON cb.production_order_no = po.production_order_no
            WHERE TRIM(COALESCE(po.material_code, '')) <> ''
              AND TRIM(COALESCE(cb.process_code, '')) <> ''
            ORDER BY po.material_code ASC, cb.process_code ASC, cb.workshop_code ASC, cb.line_code ASC
            """,
        )
        seen: set[tuple[str, str]] = set()
        sequence_by_product: dict[str, int] = defaultdict(int)
        out: list[dict[str, Any]] = []
        for row in rows:
            product_code = str(row["product_code"]).strip().upper()
            process_code = str(row["process_code"]).strip().upper()
            key = (product_code, process_code)
            if key in seen:
                continue
            seen.add(key)
            sequence_by_product[product_code] += 1
            product_name = str(row.get("product_name_cn") or product_code).strip() or product_code
            out.append(
                {
                    "id": _route_row_id(product_code, sequence_by_product[product_code]),
                    "product_code": product_code,
                    "sequence_no": sequence_by_product[product_code],
                    "process_code": process_code,
                    "process_name_cn": str(row.get("process_name_cn") or process_code).strip()
                    or process_code,
                    "dependency_type": "FS",
                    "route_no": f"ROUTE-{product_code}",
                    "route_name_cn": product_name,
                    "product_name_cn": product_name,
                }
            )
        return out

    def _group_routes_by_product(
        self,
        rows: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row["product_code"])].append(row)
        for product_code in grouped:
            grouped[product_code].sort(key=lambda item: int(item.get("sequence_no") or 0))
        return grouped

    def _replace_process_routes(
        self,
        product_code: str,
        steps: Any,
        *,
        source_product_code: str | None,
    ) -> None:
        normalized_steps = steps if isinstance(steps, list) else []
        if len(normalized_steps) == 0:
            raise bad_request(
                code="ROUTE_STEPS_REQUIRED",
                message="steps must be a non-empty array.",
            )
        product_name = (
            self._lookup_product_name(product_code)
            or self._lookup_product_name(source_product_code)
            or product_code
        )
        process_name_by_code = self._process_name_by_code()
        updated_at = utc_now()
        rows_to_insert: list[tuple[Any, ...]] = []
        for index, step in enumerate(normalized_steps):
            process_code = str(step.get("process_code") or "").strip().upper()
            if not process_code:
                raise bad_request(
                    code="ROUTE_STEP_INVALID",
                    message="Each route step requires process_code.",
                )
            dependency_type = str(step.get("dependency_type") or "FS").strip().upper() or "FS"
            rows_to_insert.append(
                (
                    product_code,
                    index + 1,
                    process_code,
                    process_name_by_code.get(process_code, process_code),
                    dependency_type,
                    f"ROUTE-{product_code}",
                    product_name,
                    product_name,
                    updated_at,
                )
            )
        with transaction(self.connection):
            self.connection.execute(
                "DELETE FROM masterdata_process_routes WHERE product_code = ?",
                (product_code,),
            )
            self.connection.executemany(
                """
                INSERT INTO masterdata_process_routes (
                    product_code,
                    sequence_no,
                    process_code,
                    process_name_cn,
                    dependency_type,
                    route_no,
                    route_name_cn,
                    product_name_cn,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )

    def _lookup_product_name(self, product_code: str | None) -> str | None:
        if not product_code:
            return None
        row = fetch_one(
            self.connection,
            """
            SELECT material_name
            FROM production_orders
            WHERE material_code = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (product_code,),
        )
        if row is None:
            return None
        return str(row.get("material_name") or "").strip() or None

    def _next_schedule_version_no(self) -> str:
        today = datetime.now().strftime("%Y.%m.%d")
        prefix = f"V{today}-D"
        row = fetch_one(
            self.connection,
            """
            SELECT COUNT(1) AS total
            FROM schedule_versions
            WHERE version_no LIKE ?
            """,
            (f"{prefix}%",),
        )
        next_index = int(row["total"]) + 1 if row else 1
        return f"{prefix}{next_index}"

    def _apply_dispatch_command(self, *, target_order_no: str, command_type: str) -> None:
        current = self._get_order_state(target_order_no) or {
            "production_order_no": target_order_no,
        }
        next_row = {
            "production_order_no": target_order_no,
            "promised_due_date": current.get("promised_due_date"),
            "expected_start_date": current.get("expected_start_date"),
            "expected_start_time": current.get("expected_start_time"),
            "expected_finish_time": current.get("expected_finish_time"),
            "urgent_flag": int(current.get("urgent_flag") or 0),
            "lock_flag": int(current.get("lock_flag") or 0),
            "frozen_flag": int(current.get("frozen_flag") or 0),
            "status": current.get("status"),
            "order_status": current.get("order_status"),
            "completed_qty": current.get("completed_qty"),
            "remaining_qty": current.get("remaining_qty"),
            "progress_rate": current.get("progress_rate"),
            "production_batch_no": current.get("production_batch_no"),
        }
        normalized = str(command_type or "").strip().upper()
        if normalized == "LOCK":
            next_row["lock_flag"] = 1
        elif normalized == "UNLOCK":
            next_row["lock_flag"] = 0
        elif normalized == "PRIORITY":
            next_row["urgent_flag"] = 1
        elif normalized == "UNPRIORITY":
            next_row["urgent_flag"] = 0
        self._upsert_order_state(next_row)

    def _find_material_reference(self, material_code: str) -> dict[str, Any]:
        row = fetch_one(
            self.connection,
            """
            SELECT
                child_material_name AS material_name_cn,
                spec_model,
                child_unit
            FROM material_issue_items
            WHERE child_material_code = ?
            LIMIT 1
            """,
            (material_code,),
        )
        if row is not None:
            return row
        row = fetch_one(
            self.connection,
            """
            SELECT
                child_material_name AS material_name_cn,
                child_specification AS spec_model,
                child_unit
            FROM bom_children
            WHERE child_material_code = ?
            LIMIT 1
            """,
            (material_code,),
        )
        return row or {}

    def _next_import_order_sequence(self) -> int:
        rows = fetch_all(
            self.connection,
            """
            SELECT production_order_no
            FROM production_orders
            WHERE production_order_no LIKE '%MO-TEST'
            """
        )
        numbers = []
        for row in rows:
            text = str(row["production_order_no"])
            digits = "".join(ch for ch in text.split("MO-TEST")[0] if ch.isdigit())
            if digits:
                numbers.append(int(digits))
        return max(numbers, default=9000) + 1
