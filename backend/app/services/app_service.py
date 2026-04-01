from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import sqlite3
from typing import Any
from uuid import uuid4

from ..db import fetch_all, fetch_one, transaction, utc_now
from ..errors import bad_request, not_found
from ..gateway.inventory import ERPInventoryGateway
from ..gateway.supply import ERPSupplyGateway
from ..json_utils import dumps, loads
from .job_dispatcher import ServiceFactory


RULES_SINGLETON_KEY = "default"
SHIFT_SEQUENCE = ("DAY", "NIGHT")
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
            "weekend_rest_mode": str(
                payload.get("weekend_rest_mode") or current["weekend_rest_mode"] or "DOUBLE"
            ).strip().upper()
            or "DOUBLE",
            "date_shift_mode_by_date_json": dumps(
                payload.get("date_shift_mode_by_date")
                if "date_shift_mode_by_date" in payload
                else (loads(current["date_shift_mode_by_date_json"]) or {})
            ),
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
        self._ensure_masterdata_seeded()
        strategy_code = str(payload.get("strategy_code") or "KEY_ORDER_FIRST").strip().upper() or "KEY_ORDER_FIRST"
        version_no = self._next_schedule_version_no()
        order_rows = self._list_order_rows()
        route_rows = self._group_routes_by_product(self._list_route_rows())
        capacity_map = self._get_capacity_map(
            [str(row["production_order_no"]) for row in order_rows]
        )
        states = self._get_order_state_map(
            [str(row["production_order_no"]) for row in order_rows]
        )
        topology_by_process = self._first_topology_by_process(self._list_line_topology_rows())
        tasks: list[tuple[Any, ...]] = []
        task_no = 1
        for order_row in order_rows:
            order_no = str(order_row["production_order_no"])
            state_row = states.get(order_no)
            status = str(
                (state_row or {}).get("order_status")
                or (state_row or {}).get("status")
                or order_row.get("status")
                or ""
            ).strip().upper()
            if status == "DONE":
                continue
            process_contexts = self._build_process_contexts(
                order_no=order_no,
                product_code=str(order_row["material_code"]),
                capacity_rows=capacity_map.get(order_no, []),
                route_rows=route_rows.get(str(order_row["material_code"]), []),
                topology_by_process=topology_by_process,
            )
            if len(process_contexts) == 0:
                continue
            start_date = _parse_date_or_today(
                (state_row or {}).get("expected_start_date")
                or order_row.get("planned_start_date")
                or self._get_simulation_state()["current_date"]
            )
            production_qty = _to_number(order_row.get("production_qty"), 0)
            per_task_qty = production_qty / max(len(process_contexts), 1) if production_qty > 0 else 0
            for index, context in enumerate(process_contexts):
                calendar_date = (start_date + timedelta(days=index)).isoformat()
                shift_code = SHIFT_SEQUENCE[index % len(SHIFT_SEQUENCE)]
                tasks.append(
                    (
                        version_no,
                        task_no,
                        order_no,
                        str(context["process_code"]),
                        str(context["process_name_cn"]),
                        calendar_date,
                        shift_code,
                        per_task_qty,
                        _iso_at(calendar_date, "08:00:00"),
                    )
                )
                task_no += 1
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
        if normalized_mode == "real":
            self.factory.build_material_refresh_service().refresh_order_materials(order_no)
        return self.list_order_pool_materials(order_no, refresh=False)

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
                order_qty = (
                    datetime.now().microsecond % 4001 + 1000
                    if random_guidewire
                    else 100
                )
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
        if capacity_rows:
            return [
                {
                    "sequence_no": index + 1,
                    "process_code": row["process_code"],
                    "process_name_cn": row.get("process_name") or row["process_code"],
                    "workshop_code": row.get("workshop_code") or "-",
                    "line_code": row.get("line_code") or "-",
                    "dependency_type": "FS",
                }
                for index, row in enumerate(capacity_rows)
            ]
        contexts: list[dict[str, Any]] = []
        for index, row in enumerate(route_rows):
            process_code = str(row.get("process_code") or "").strip().upper()
            topology_row = topology_by_process.get(process_code, {})
            contexts.append(
                {
                    "sequence_no": index + 1,
                    "process_code": process_code,
                    "process_name_cn": row.get("process_name_cn") or process_code,
                    "workshop_code": topology_row.get("workshop_code") or "-",
                    "line_code": topology_row.get("line_code") or "-",
                    "dependency_type": row.get("dependency_type") or "FS",
                }
            )
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
        topology_rows = self._derive_line_topology_rows() if int(topology_count["total"]) == 0 else []
        route_rows = self._derive_route_rows() if int(route_count["total"]) == 0 else []
        if len(topology_rows) == 0 and len(route_rows) == 0:
            return
        updated_at = utc_now()
        with transaction(self.connection):
            if len(topology_rows) > 0 and int(topology_count["total"]) == 0:
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
            if len(route_rows) > 0 and int(route_count["total"]) == 0:
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
