from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from ..db import fetch_all, fetch_one
from ..errors import bad_request, server_error
from .order_summary_query_service import (
    SCHEDULE_NUMBER_EPSILON,
    _normalize_date_text,
    _to_number,
)


def _normalize_dashboard_code(value: object) -> str:
    return str(value or "").strip().upper()


def _normalize_dashboard_name(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _build_dashboard_options(
    meta_by_code: dict[str, dict[str, str]],
    *,
    code_key: str,
    name_key: str,
) -> list[dict[str, str]]:
    def option_sort_key(item: tuple[str, dict[str, str]]) -> tuple[str, str]:
        code, meta = item
        name = str(meta.get(name_key) or code).strip() or code
        return (name.lower(), code)

    return [
        {
            code_key: code,
            name_key: str(meta.get(name_key) or code).strip() or code,
        }
        for code, meta in sorted(meta_by_code.items(), key=option_sort_key)
    ]


def _build_dashboard_change_items(
    calendar_dates: list[str],
    totals_by_code: dict[str, dict[str, float]],
    meta_by_code: dict[str, dict[str, str]],
    *,
    code_key: str,
    name_key: str,
    actual_totals_by_code: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for option in _build_dashboard_options(
        meta_by_code,
        code_key=code_key,
        name_key=name_key,
    ):
        code = str(option.get(code_key) or "").strip().upper()
        if not code:
            continue
        previous_planned_capacity_qty: float | None = None
        planned_by_date = totals_by_code.get(code) or {}
        actual_by_date = actual_totals_by_code.get(code) if actual_totals_by_code else {}
        for calendar_date in calendar_dates:
            planned_capacity_qty = round(
                _to_number(planned_by_date.get(calendar_date), 0),
                4,
            )
            actual_capacity_qty = round(
                _to_number((actual_by_date or {}).get(calendar_date), 0),
                4,
            )
            planned_capacity_change_qty = (
                0
                if previous_planned_capacity_qty is None
                else round(planned_capacity_qty - previous_planned_capacity_qty, 4)
            )
            items.append(
                {
                    "calendar_date": calendar_date,
                    code_key: code,
                    name_key: str(option.get(name_key) or code).strip() or code,
                    "planned_capacity_qty": planned_capacity_qty,
                    "actual_capacity_qty": actual_capacity_qty,
                    "planned_capacity_change_qty": planned_capacity_change_qty,
                }
            )
            previous_planned_capacity_qty = planned_capacity_qty
    return items


class DashboardQueryService:
    def __init__(self, host: Any, order_summary_service: Any) -> None:
        self.host = host
        self.connection = host.connection
        self.order_summary_service = order_summary_service

    def get_scheduler_dashboard(
        self,
        *,
        start_date: str,
        end_date: str,
        top_n: int = 8,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_start_date = _normalize_date_text(start_date)
        if normalized_start_date is None:
            raise bad_request(
                code="DASHBOARD_START_DATE_REQUIRED",
                message="start_date must be a valid YYYY-MM-DD date.",
            )
        normalized_end_date = _normalize_date_text(end_date)
        if normalized_end_date is None:
            raise bad_request(
                code="DASHBOARD_END_DATE_REQUIRED",
                message="end_date must be a valid YYYY-MM-DD date.",
            )
        if normalized_end_date < normalized_start_date:
            raise bad_request(
                code="DASHBOARD_DATE_RANGE_INVALID",
                message="end_date must be greater than or equal to start_date.",
                details={
                    "start_date": normalized_start_date,
                    "end_date": normalized_end_date,
                },
            )

        normalized_top_n = int(_to_number(top_n, 0))
        if normalized_top_n < 1 or normalized_top_n > 50:
            raise bad_request(
                code="DASHBOARD_TOP_N_INVALID",
                message="top_n must be between 1 and 50.",
            )

        topology_count_row = fetch_one(
            self.connection,
            """
            SELECT COUNT(1) AS total
            FROM masterdata_line_topology
            """,
        )
        topology_count = int(_to_number((topology_count_row or {}).get("total"), 0))
        if topology_count <= 0:
            raise server_error(
                code="DASHBOARD_TOPOLOGY_EMPTY",
                message="masterdata_line_topology contains no rows.",
            )

        order_summary = self.order_summary_service.get_order_summary(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
            current_user=current_user,
        )
        order_items = (
            order_summary.get("order_items")
            if isinstance(order_summary.get("order_items"), list)
            else []
        )
        if len(order_items) == 0:
            raise bad_request(
                code="DASHBOARD_ORDER_DATA_EMPTY",
                message="No order summary rows exist for the requested date range.",
                details={
                    "start_date": normalized_start_date,
                    "end_date": normalized_end_date,
                },
            )

        start_date_value = date.fromisoformat(normalized_start_date)
        end_date_value = date.fromisoformat(normalized_end_date)
        current_date_value = start_date_value
        calendar_dates: list[str] = []
        previous_planned_capacity_qty: float | None = None
        daily_capacity_items: list[dict[str, Any]] = []
        total_default_capacity_qty = 0.0
        total_planned_capacity_qty = 0.0
        total_actual_capacity_qty = 0.0
        failure_row_count = 0
        evaluated_row_count = 0
        line_meta_by_code: dict[str, dict[str, str]] = {}
        process_meta_by_code: dict[str, dict[str, str]] = {}
        line_planned_capacity_by_code: dict[str, dict[str, float]] = defaultdict(dict)
        process_planned_capacity_by_code: dict[str, dict[str, float]] = defaultdict(dict)
        line_actual_capacity_by_code: dict[str, dict[str, float]] = defaultdict(dict)
        process_actual_capacity_by_code: dict[str, dict[str, float]] = defaultdict(dict)
        line_daily_stats_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        process_daily_stats_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        daily_pressure_items: list[dict[str, Any]] = []
        process_name_by_code = self.host._process_name_by_code()

        while current_date_value <= end_date_value:
            calendar_date = current_date_value.isoformat()
            calendar_dates.append(calendar_date)
            capacity_payload = self.host.list_line_daily_capacity(calendar_date)
            capacity_rows = (
                capacity_payload.get("items")
                if isinstance(capacity_payload.get("items"), list)
                else []
            )
            if len(capacity_rows) == 0:
                raise bad_request(
                    code="DASHBOARD_CAPACITY_DATA_EMPTY",
                    message="No daily capacity rows exist for the requested date.",
                    details={"calendar_date": calendar_date},
                )

            day_default_capacity_qty = 0.0
            day_planned_capacity_qty = 0.0
            day_actual_capacity_qty = 0.0
            day_failure_row_count = 0
            day_line_planned_capacity: dict[str, float] = defaultdict(float)
            day_process_planned_capacity: dict[str, float] = defaultdict(float)
            day_line_default_capacity: dict[str, float] = defaultdict(float)
            day_line_actual_capacity: dict[str, float] = defaultdict(float)
            day_process_default_capacity: dict[str, float] = defaultdict(float)
            day_process_actual_capacity: dict[str, float] = defaultdict(float)
            for row in capacity_rows:
                default_capacity_qty = _to_number(row.get("default_capacity_qty"), 0)
                planned_capacity_qty = _to_number(row.get("planned_capacity_qty"), 0)
                actual_capacity_qty = _to_number(row.get("actual_capacity_qty"), 0)
                machine_count = int(_to_number(row.get("machine_count"), 0))
                required_machines = int(_to_number(row.get("required_machines"), 0))
                line_code = _normalize_dashboard_code(row.get("line_code"))
                if line_code:
                    line_name = _normalize_dashboard_name(row.get("line_name"), line_code)
                    line_meta_by_code.setdefault(
                        line_code,
                        {
                            "line_code": line_code,
                            "line_name": line_name,
                        },
                    )
                    day_line_planned_capacity[line_code] += planned_capacity_qty
                    day_line_default_capacity[line_code] += default_capacity_qty
                    day_line_actual_capacity[line_code] += actual_capacity_qty
                process_code = _normalize_dashboard_code(row.get("process_code"))
                if process_code:
                    process_name_cn = _normalize_dashboard_name(
                        process_name_by_code.get(process_code),
                        process_code,
                    )
                    process_meta_by_code.setdefault(
                        process_code,
                        {
                            "process_code": process_code,
                            "process_name_cn": process_name_cn,
                        },
                    )
                    day_process_planned_capacity[process_code] += planned_capacity_qty
                    day_process_default_capacity[process_code] += default_capacity_qty
                    day_process_actual_capacity[process_code] += actual_capacity_qty
                day_default_capacity_qty += default_capacity_qty
                day_planned_capacity_qty += planned_capacity_qty
                day_actual_capacity_qty += actual_capacity_qty
                if required_machines > 0:
                    evaluated_row_count += 1
                    if machine_count < required_machines:
                        day_failure_row_count += 1
                        failure_row_count += 1

            planned_capacity_change_qty = (
                0
                if previous_planned_capacity_qty is None
                else round(day_planned_capacity_qty - previous_planned_capacity_qty, 4)
            )
            previous_planned_capacity_qty = day_planned_capacity_qty

            day_failure_rate = (
                round(day_failure_row_count / len(capacity_rows) * 100, 2)
                if len(capacity_rows) > 0
                else 0
            )
            daily_capacity_items.append(
                {
                    "calendar_date": calendar_date,
                    "default_capacity_qty": round(day_default_capacity_qty, 4),
                    "planned_capacity_qty": round(day_planned_capacity_qty, 4),
                    "actual_capacity_qty": round(day_actual_capacity_qty, 4),
                    "planned_capacity_change_qty": planned_capacity_change_qty,
                    "failure_row_count": day_failure_row_count,
                    "row_count": len(capacity_rows),
                    "failure_rate": day_failure_rate,
                }
            )
            for line_code, planned_capacity in day_line_planned_capacity.items():
                line_planned_capacity_by_code[line_code][calendar_date] = planned_capacity
                line_actual_capacity_by_code[line_code][calendar_date] = round(
                    day_line_actual_capacity.get(line_code, 0),
                    4,
                )
                line_daily_stats_by_key[(calendar_date, line_code)] = {
                    "calendar_date": calendar_date,
                    "line_code": line_code,
                    "line_name": str(
                        (line_meta_by_code.get(line_code) or {}).get("line_name") or line_code
                    ).strip()
                    or line_code,
                    "default_capacity_qty": round(day_line_default_capacity.get(line_code, 0), 4),
                    "planned_capacity_qty": round(planned_capacity, 4),
                    "actual_capacity_qty": round(day_line_actual_capacity.get(line_code, 0), 4),
                }
            for process_code, planned_capacity in day_process_planned_capacity.items():
                process_planned_capacity_by_code[process_code][calendar_date] = planned_capacity
                process_actual_capacity_by_code[process_code][calendar_date] = round(
                    day_process_actual_capacity.get(process_code, 0),
                    4,
                )
                process_daily_stats_by_key[(calendar_date, process_code)] = {
                    "calendar_date": calendar_date,
                    "process_code": process_code,
                    "process_name_cn": str(
                        (process_meta_by_code.get(process_code) or {}).get("process_name_cn")
                        or process_code
                    ).strip()
                    or process_code,
                    "default_capacity_qty": round(day_process_default_capacity.get(process_code, 0), 4),
                    "planned_capacity_qty": round(planned_capacity, 4),
                    "actual_capacity_qty": round(day_process_actual_capacity.get(process_code, 0), 4),
                }
            day_line_stats = [line_daily_stats_by_key[(calendar_date, code)] for code in day_line_planned_capacity]
            overload_line_count = sum(
                1
                for item in day_line_stats
                if _to_number(item.get("actual_capacity_qty"), 0)
                > _to_number(item.get("default_capacity_qty"), 0) + SCHEDULE_NUMBER_EPSILON
            )
            idle_line_count = sum(
                1
                for item in day_line_stats
                if _to_number(item.get("actual_capacity_qty"), 0)
                + SCHEDULE_NUMBER_EPSILON
                < _to_number(item.get("default_capacity_qty"), 0)
            )
            utilization_rate = (
                round(day_actual_capacity_qty / day_default_capacity_qty * 100, 2)
                if day_default_capacity_qty > SCHEDULE_NUMBER_EPSILON
                else 0
            )
            daily_pressure_items.append(
                {
                    "calendar_date": calendar_date,
                    "default_capacity_qty": round(day_default_capacity_qty, 4),
                    "planned_capacity_qty": round(day_planned_capacity_qty, 4),
                    "actual_capacity_qty": round(day_actual_capacity_qty, 4),
                    "utilization_rate": utilization_rate,
                    "overload_qty": round(max(0.0, day_actual_capacity_qty - day_default_capacity_qty), 4),
                    "idle_qty": round(max(0.0, day_default_capacity_qty - day_actual_capacity_qty), 4),
                    "overload_line_count": overload_line_count,
                    "idle_line_count": idle_line_count,
                }
            )
            total_default_capacity_qty += day_default_capacity_qty
            total_planned_capacity_qty += day_planned_capacity_qty
            total_actual_capacity_qty += day_actual_capacity_qty
            current_date_value = current_date_value + timedelta(days=1)

        if evaluated_row_count <= 0:
            raise server_error(
                code="DASHBOARD_MACHINE_REQUIREMENT_EMPTY",
                message="No machine-driven capacity rows exist in the requested range.",
            )
        if len(line_meta_by_code) == 0:
            raise server_error(
                code="DASHBOARD_LINE_SERIES_EMPTY",
                message="No line capacity series can be built for the requested range.",
            )
        if len(process_meta_by_code) == 0:
            raise server_error(
                code="DASHBOARD_PROCESS_SERIES_EMPTY",
                message="No process capacity series can be built for the requested range.",
            )

        equipment_failure_rate = round(failure_row_count / evaluated_row_count * 100, 2)
        summary_row = (
            order_summary.get("summary")
            if isinstance(order_summary.get("summary"), dict)
            else {}
        )
        order_count = int(_to_number(summary_row.get("order_count"), 0))
        completed_order_count = int(_to_number(summary_row.get("completed_order_count"), 0))
        order_completion_rate = _to_number(summary_row.get("completion_rate"), 0)

        order_no_set: set[str] = set()
        for item in order_items:
            order_no = str(item.get("order_no") or "").strip()
            if not order_no:
                continue
            order_no_set.add(order_no)

        material_rows: list[dict[str, Any]] = []
        if order_no_set:
            placeholders = ",".join("?" for _ in order_no_set)
            material_rows = fetch_all(
                self.connection,
                f"""
                SELECT
                    production_order_no,
                    child_material_code,
                    child_material_name,
                    child_unit,
                    issue_qty
                FROM material_issue_items
                WHERE production_order_no IN ({placeholders})
                """,
                tuple(sorted(order_no_set)),
            )

        material_aggregate_map: dict[str, dict[str, Any]] = {}
        for row in material_rows:
            order_no = str(row.get("production_order_no") or "").strip()
            material_code = str(row.get("child_material_code") or "").strip().upper()
            if not order_no or not material_code:
                continue
            if order_no not in order_no_set:
                continue
            issue_qty = _to_number(row.get("issue_qty"), 0)
            estimated_issue_qty = issue_qty
            if estimated_issue_qty <= SCHEDULE_NUMBER_EPSILON:
                continue
            aggregate_row = material_aggregate_map.get(material_code)
            if aggregate_row is None:
                aggregate_row = {
                    "material_code": material_code,
                    "material_name_cn": str(row.get("child_material_name") or material_code).strip()
                    or material_code,
                    "unit": str(row.get("child_unit") or "").strip(),
                    "estimated_issue_qty": 0.0,
                    "order_no_set": set(),
                }
                material_aggregate_map[material_code] = aggregate_row
            aggregate_row["estimated_issue_qty"] = (
                _to_number(aggregate_row.get("estimated_issue_qty"), 0) + estimated_issue_qty
            )
            cast_order_set = aggregate_row.get("order_no_set")
            if isinstance(cast_order_set, set):
                cast_order_set.add(order_no)

        ranked_material_items = sorted(
            material_aggregate_map.values(),
            key=lambda item: (
                -_to_number(item.get("estimated_issue_qty"), 0),
                str(item.get("material_code") or ""),
            ),
        )
        material_ranking = ranked_material_items[:normalized_top_n]
        material_consumption_items = [
            {
                "rank": index + 1,
                "material_code": str(item.get("material_code") or ""),
                "material_name_cn": str(item.get("material_name_cn") or ""),
                "unit": str(item.get("unit") or ""),
                "estimated_issue_qty": round(_to_number(item.get("estimated_issue_qty"), 0), 4),
                "order_count": len(item.get("order_no_set") or set()),
            }
            for index, item in enumerate(material_ranking)
        ]

        line_overload_items = []
        for item in line_daily_stats_by_key.values():
            default_capacity_qty = _to_number(item.get("default_capacity_qty"), 0)
            actual_capacity_qty = _to_number(item.get("actual_capacity_qty"), 0)
            utilization_rate = (
                round(actual_capacity_qty / default_capacity_qty * 100, 2)
                if default_capacity_qty > SCHEDULE_NUMBER_EPSILON
                else 0
            )
            overload_qty = max(0.0, actual_capacity_qty - default_capacity_qty)
            idle_qty = max(0.0, default_capacity_qty - actual_capacity_qty)
            line_overload_items.append(
                {
                    **item,
                    "utilization_rate": utilization_rate,
                    "overload_qty": round(overload_qty, 4),
                    "idle_qty": round(idle_qty, 4),
                    "actual_capacity_qty": round(actual_capacity_qty, 4),
                }
            )
        line_overload_items.sort(
            key=lambda item: (
                -_to_number(item.get("overload_qty"), 0),
                -_to_number(item.get("utilization_rate"), 0),
                str(item.get("calendar_date") or ""),
                str(item.get("line_code") or ""),
            )
        )

        process_bottleneck_items = []
        process_grouped_daily: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in process_daily_stats_by_key.values():
            process_grouped_daily[str(item.get("process_code") or "")].append(item)
        for process_code, grouped_items in process_grouped_daily.items():
            peak_item = None
            utilization_rates: list[float] = []
            peak_utilization_rate = 0.0
            for item in grouped_items:
                default_capacity_qty = _to_number(item.get("default_capacity_qty"), 0)
                actual_capacity_qty = _to_number(item.get("actual_capacity_qty"), 0)
                utilization_rate = (
                    round(actual_capacity_qty / default_capacity_qty * 100, 2)
                    if default_capacity_qty > SCHEDULE_NUMBER_EPSILON
                    else 0
                )
                utilization_rates.append(utilization_rate)
                if peak_item is None or utilization_rate > peak_utilization_rate:
                    peak_item = item
                    peak_utilization_rate = utilization_rate
            average_utilization_rate = (
                round(sum(utilization_rates) / len(utilization_rates), 2)
                if utilization_rates
                else 0
            )
            process_bottleneck_items.append(
                {
                    "process_code": process_code,
                    "process_name_cn": str(
                        (peak_item or {}).get("process_name_cn") or process_code
                    ).strip()
                    or process_code,
                    "peak_utilization_rate": peak_utilization_rate,
                    "average_utilization_rate": average_utilization_rate,
                    "peak_date": (peak_item or {}).get("calendar_date"),
                    "peak_actual_capacity_qty": round(
                        _to_number((peak_item or {}).get("actual_capacity_qty"), 0),
                        4,
                    ),
                    "peak_planned_capacity_qty": round(
                        _to_number((peak_item or {}).get("planned_capacity_qty"), 0),
                        4,
                    ),
                    "peak_default_capacity_qty": round(
                        _to_number((peak_item or {}).get("default_capacity_qty"), 0),
                        4,
                    ),
                }
            )
        process_bottleneck_items.sort(
            key=lambda item: (
                -_to_number(item.get("peak_utilization_rate"), 0),
                -_to_number(item.get("average_utilization_rate"), 0),
                str(item.get("process_code") or ""),
            )
        )

        peak_overload_day = max(
            daily_pressure_items,
            key=lambda item: (
                _to_number(item.get("overload_qty"), 0),
                _to_number(item.get("utilization_rate"), 0),
            ),
            default={},
        )
        peak_idle_day = max(
            daily_pressure_items,
            key=lambda item: (
                _to_number(item.get("idle_qty"), 0),
                -_to_number(item.get("utilization_rate"), 0),
            ),
            default={},
        )
        top_overload_line = line_overload_items[0] if line_overload_items else {}
        top_bottleneck_process = process_bottleneck_items[0] if process_bottleneck_items else {}

        total_days = (end_date_value - start_date_value).days + 1
        return {
            "range": {
                "start_date": normalized_start_date,
                "end_date": normalized_end_date,
                "total_days": total_days,
            },
            "summary": {
                "order_count": order_count,
                "completed_order_count": completed_order_count,
                "order_completion_rate": round(order_completion_rate, 2),
                "evaluated_machine_row_count": evaluated_row_count,
                "failure_row_count": failure_row_count,
                "equipment_failure_rate": equipment_failure_rate,
                "total_capacity_qty": round(total_planned_capacity_qty, 4),
                "total_default_capacity_qty": round(total_default_capacity_qty, 4),
                "total_planned_capacity_qty": round(total_planned_capacity_qty, 4),
                "total_actual_capacity_qty": round(total_actual_capacity_qty, 4),
            },
            "daily_capacity": {
                "items": daily_capacity_items,
            },
            "capacity_change_by_line": {
                "options": _build_dashboard_options(
                    line_meta_by_code,
                    code_key="line_code",
                    name_key="line_name",
                ),
                "items": _build_dashboard_change_items(
                    calendar_dates,
                    line_planned_capacity_by_code,
                    line_meta_by_code,
                    code_key="line_code",
                    name_key="line_name",
                    actual_totals_by_code=line_actual_capacity_by_code,
                ),
            },
            "capacity_change_by_process": {
                "options": _build_dashboard_options(
                    process_meta_by_code,
                    code_key="process_code",
                    name_key="process_name_cn",
                ),
                "items": _build_dashboard_change_items(
                    calendar_dates,
                    process_planned_capacity_by_code,
                    process_meta_by_code,
                    code_key="process_code",
                    name_key="process_name_cn",
                    actual_totals_by_code=process_actual_capacity_by_code,
                ),
            },
            "material_consumption": {
                "top_n": normalized_top_n,
                "items": material_consumption_items,
            },
            "cockpit": {
                "summary": {
                    "peak_overload_date": peak_overload_day.get("calendar_date"),
                    "peak_overload_qty": round(
                        _to_number(peak_overload_day.get("overload_qty"), 0),
                        4,
                    ),
                    "peak_idle_date": peak_idle_day.get("calendar_date"),
                    "peak_idle_qty": round(_to_number(peak_idle_day.get("idle_qty"), 0), 4),
                    "top_overload_line_code": top_overload_line.get("line_code"),
                    "top_overload_line_name": top_overload_line.get("line_name"),
                    "top_overload_line_date": top_overload_line.get("calendar_date"),
                    "top_overload_line_utilization_rate": _to_number(
                        top_overload_line.get("utilization_rate"),
                        0,
                    ),
                    "top_bottleneck_process_code": top_bottleneck_process.get("process_code"),
                    "top_bottleneck_process_name_cn": top_bottleneck_process.get(
                        "process_name_cn"
                    ),
                    "top_bottleneck_process_peak_date": top_bottleneck_process.get("peak_date"),
                    "top_bottleneck_process_peak_utilization_rate": _to_number(
                        top_bottleneck_process.get("peak_utilization_rate"),
                        0,
                    ),
                },
                "line_overload_items": line_overload_items[:8],
                "process_bottleneck_items": process_bottleneck_items[:8],
                "daily_pressure_items": daily_pressure_items,
            },
        }
