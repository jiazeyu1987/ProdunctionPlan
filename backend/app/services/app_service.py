from __future__ import annotations

import base64
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import math
import random
import sqlite3
from typing import Any
from uuid import uuid4

from ..db import fetch_all, fetch_one, transaction, utc_now
from ..errors import bad_request, forbidden, not_found, server_error
from ..json_utils import loads
from ..repositories.backups import BackupRepository
from .dashboard_query_service import DashboardQueryService
from .dispatch_command_service import DispatchCommandService
from .final_process_metrics import build_order_final_process_metrics
from .legacy_runtime import LegacyAppRuntime, build_legacy_app_runtime
from .masterdata_query_service import MasterdataQueryService
from .masterdata_command_service import MasterdataCommandService
from .order_summary_query_service import OrderSummaryQueryService
from .reporting_command_service import ReportingCommandService
from .reporting_query_service import ReportingQueryService
from .schedules_query_service import SchedulesQueryService


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
SUPPORTED_CAPACITY_SOURCE_MODES = {"DEFAULT", "PLANNED", "ACTUAL"}
SUPPORTED_CN_HOLIDAY_YEARS = {2024, 2025, 2026, 2027, 2028}
PRIORITY_LEVEL_MIN = 1
PRIORITY_LEVEL_MAX = 5
ROLE_SCHEDULER = "SCHEDULER"
ROLE_WORKSHOP_MANAGER = "WORKSHOP_MANAGER"
DEFAULT_COMPANY_CODE = "COMPANY-MAIN"
ANGIO_CATHETER_PRODUCT_CODES = frozenset(
    {
        "A006.034.10191",
        "YXN.009.020.1047",
        "YXN.044.02.1028",
        "YXN.067.005.1006",
        "A006.034.6104",
        "YXN.044.02.1020",
    }
)
DEFAULT_ANGIO_WORKSHOP_CODE = "1杞﹂棿"
DEFAULT_ANGIO_WORKSHOP_NAME = "1杞﹂棿"
DEFAULT_ANGIO_LINE_CODE = "1浜х嚎"
DEFAULT_ANGIO_LINE_NAME = "1浜х嚎"
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
CURRENT_SCHEDULE_VERSION_NO = "CURRENT"
STATUS_NAME_BY_CODE = {
    "CURRENT": "褰撳墠鏂规",
    "SAVED": "已保存",
    "ARCHIVED": "已归档",
}
LOCAL_ORDER_STATUS_CODES = frozenset(
    {
        "OPEN",
        "IN_PROGRESS",
        "DONE",
        "COMPLETED",
        "CLOSED",
        "DELAY",
    }
)
LOCAL_TIMEZONE = timezone(timedelta(hours=8))


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


def _local_date_from_iso_datetime(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(LOCAL_TIMEZONE).date().isoformat()


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


def _signed_days_between(start_text: object, end_text: object) -> int | None:
    start = _normalize_date_text(start_text)
    end = _normalize_date_text(end_text)
    if not start or not end:
        return None
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _parse_local_iso_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(LOCAL_TIMEZONE)


def _due_deadline_datetime(date_text: object, clock_text: str = "18:00:00") -> datetime | None:
    normalized = _normalize_date_text(date_text)
    if not normalized:
        return None
    return _parse_local_iso_datetime(_iso_at(normalized, clock_text))


def _event_datetime(value: object, default_clock_text: str = "18:00:00") -> datetime | None:
    parsed = _parse_local_iso_datetime(value)
    if parsed is not None:
        return parsed
    normalized_date = _normalize_date_text(value)
    if not normalized_date:
        return None
    return _parse_local_iso_datetime(_iso_at(normalized_date, default_clock_text))


def _signed_due_gap_days(
    due_date_text: object,
    event_value: object,
    *,
    event_default_clock_text: str = "18:00:00",
) -> int | None:
    due_deadline = _due_deadline_datetime(due_date_text)
    event_time = _event_datetime(event_value, event_default_clock_text)
    if due_deadline is None or event_time is None:
        return None
    day_gap = (event_time.date() - due_deadline.date()).days
    if day_gap == 0 and event_time > due_deadline:
        return 1
    return day_gap


def _days_from_today(date_text: object) -> int | None:
    normalized = _normalize_date_text(date_text)
    if normalized is None:
        return None
    today = datetime.now(LOCAL_TIMEZONE).date()
    return (date.fromisoformat(normalized) - today).days


def _to_number(value: object, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


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
        for calendar_date in calendar_dates:
            planned_capacity_qty = round(
                _to_number(planned_by_date.get(calendar_date), 0),
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
                    "planned_capacity_change_qty": planned_capacity_change_qty,
                }
            )
            previous_planned_capacity_qty = planned_capacity_qty
    return items


def _normalize_priority_level(value: object, default: int = PRIORITY_LEVEL_MAX) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return default
    return max(PRIORITY_LEVEL_MIN, min(PRIORITY_LEVEL_MAX, level))


def _parse_enabled_flag(value: object) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        if value in (0, 1):
            return value
        raise ValueError("enabled_flag must be 0 or 1.")
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return 1
    if text in {"0", "false", "no", "off"}:
        return 0
    raise ValueError("enabled_flag must be 0/1 or a boolean-like value.")


def _parse_int_in_range(
    value: object,
    *,
    field_name: str,
    min_value: int,
    max_value: int,
) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{field_name} must be an integer.")
        parsed = int(value)
    else:
        text = str(value or "").strip()
        if not text or any(ch not in "0123456789" for ch in text):
            raise ValueError(f"{field_name} must be an integer.")
        parsed = int(text)

    if parsed < min_value or parsed > max_value:
        raise ValueError(
            f"{field_name} must be between {min_value} and {max_value} (inclusive)."
        )
    return parsed


def _urgent_flag_from_priority_level(priority_level: object) -> int:
    return 1 if _normalize_priority_level(priority_level) == PRIORITY_LEVEL_MIN else 0


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


def _expected_start_shift_from_datetime_text(value: object) -> str:
    timestamp_text = str(value or "").strip().upper()
    if not timestamp_text:
        return "DAY"
    if "T" in timestamp_text:
        time_text = timestamp_text.split("T", 1)[1][:8]
        try:
            hour = int(time_text.split(":", 1)[0])
        except (TypeError, ValueError):
            hour = None
        if hour is not None and (hour >= 20 or hour < 8):
            return "NIGHT"
    return "DAY"


def _schedule_version_status_label(status: object) -> str:
    normalized = str(status or "").strip().upper()
    if normalized == "CURRENT":
        return "褰撳墠鏂规"
    if normalized in {"SAVED", "PUBLISHED", "DRAFT", "ARCHIVED"}:
        return "已保存"
    return normalized or "-"

def _schedule_result_status_label(status: object) -> str:
    normalized = str(status or "").strip().upper()
    if normalized == "FEASIBLE":
        return "可执行建议计划"
    if normalized == "RISKY":
        return "有风险建议计划"
    if normalized == "BLOCKED":
        return "闃绘柇"
    return normalized or "-"


class AppService:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        runtime: LegacyAppRuntime | None = None,
    ) -> None:
        self.connection = connection
        runtime = runtime or build_legacy_app_runtime(connection)
        self.runtime = runtime
        self.factory = runtime.factory
        self.line_daily_capacity_service = runtime.line_daily_capacity_service
        self.masterdata_gateway = runtime.masterdata_gateway
        self.order_gateway = runtime.order_gateway
        self.inventory_gateway = runtime.inventory_gateway
        self.supply_gateway = runtime.supply_gateway
        self.schedules_query_service = SchedulesQueryService(connection)
        self.order_summary_query_service = OrderSummaryQueryService(self)
        self.dashboard_query_service = DashboardQueryService(
            self,
            self.order_summary_query_service,
        )
        self.reporting_query_service = ReportingQueryService(self)
        self.reporting_command_service = ReportingCommandService(self)
        self.dispatch_command_service = DispatchCommandService(self)
        self.masterdata_query_service = MasterdataQueryService(self)
        self.masterdata_command_service = MasterdataCommandService(self)

    def list_order_pool(self, *, version_no: str | None = None) -> dict[str, Any]:
        rows = self._list_order_rows()
        order_nos = [str(row["production_order_no"]) for row in rows]
        states = self._get_order_state_map(order_nos)
        capacity_map = self._get_capacity_map(order_nos)
        self._ensure_masterdata_seeded()
        reference_version_no = self._resolve_order_pool_version_no(version_no)
        reference_schedule_context = self._build_reference_schedule_context(reference_version_no)
        published_schedule_context = reference_schedule_context
        shortage_analysis = self._build_schedule_shortage_analysis(reference_version_no)
        published_shortage_analysis = shortage_analysis
        final_process_metrics_by_order = build_order_final_process_metrics(
            self.connection,
            rows,
        )
        route_rows = self._list_route_rows()
        route_map = self._group_routes_by_product(route_rows)
        topology_by_process = self._first_topology_by_process(self._list_line_topology_rows())
        items: list[dict[str, Any]] = []
        for row in rows:
            order_no = str(row["production_order_no"])
            items.append(
                self._build_order_pool_row(
                base_row=row,
                state_row=states.get(order_no),
                capacity_rows=capacity_map.get(order_no, []),
                route_rows=route_map.get(str(row["material_code"]), []),
                topology_by_process=topology_by_process,
                reference_version=reference_schedule_context.get("version"),
                schedule_fact=reference_schedule_context["order_map"].get(order_no),
                    published_version=None,
                    published_schedule_fact=None,
                shortage_summary=published_shortage_analysis["order_map"].get(order_no),
                final_process_metrics=final_process_metrics_by_order.get(order_no),
            )
            )
        return {"items": items}
        reference_version = reference_schedule_context.get("version")
        reference_version_status = str((reference_version or {}).get("status") or "").strip().upper() or None
        reference_version_status_label = _schedule_version_status_label(reference_version_status)
        published_version = published_schedule_context.get("version")
        published_version_status = str((published_version or {}).get("status") or "").strip().upper() or None
        return {
            "reference_version_no": reference_version_no,
            "current_view_version_no": reference_version_no,
            "current_view_version_status": reference_version_status,
            "current_view_version_status_label": reference_version_status_label,
            "current_view_version_label": (
                f"当前方案 {reference_version_no}（{reference_version_status_label}）"
                if reference_version_no
                else "暂无当前方案"
            ),
            "published_version_no": published_version_no,
            "published_version_status": published_version_status,
            "published_version_status_label": _schedule_version_status_label(published_version_status),
            "published_version_label": (
                f"当前方案 {published_version_no}"
                if published_version_no
                else "暂无当前方案"
            ),
            "draft_version_no": draft_version_no,
            "draft_version_status": str((draft_version or {}).get("status") or "").strip().upper() or None,
            "draft_version_status_label": _schedule_version_status_label((draft_version or {}).get("status")),
            "draft_version_label": (
                f"最近存档 {draft_version_no}"
                if draft_version_no
                else "暂无已保存存档"
            ),
            "items": items,
        }

    def get_order_pool_item(self, order_no: str, *, version_no: str | None = None) -> dict[str, Any]:
        base_row = self._require_order(order_no)
        state_row = self._get_order_state(order_no)
        self._ensure_masterdata_seeded()
        normalized_order_no = str(base_row["production_order_no"])
        reference_version_no = self._resolve_order_pool_version_no(version_no)
        reference_schedule_context = self._build_reference_schedule_context(reference_version_no)
        published_schedule_context = reference_schedule_context
        shortage_analysis = self._build_schedule_shortage_analysis(reference_version_no)
        published_shortage_analysis = shortage_analysis
        final_process_metrics = build_order_final_process_metrics(
            self.connection,
            [base_row],
        ).get(normalized_order_no)
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
            reference_version=reference_schedule_context.get("version"),
            schedule_fact=reference_schedule_context["order_map"].get(normalized_order_no),
            published_version=None,
            published_schedule_fact=None,
            shortage_summary=published_shortage_analysis["order_map"].get(normalized_order_no),
            final_process_metrics=final_process_metrics,
        )

    def get_order_pool_process_timeline(
        self,
        order_no: str,
        *,
        process_code: str | None = None,
        version_no: str | None = None,
    ) -> dict[str, Any]:
        base_row = self._require_order(order_no)
        normalized_order_no = str(base_row["production_order_no"]).strip()
        normalized_product_code = str(base_row.get("material_code") or "").strip().upper()
        normalized_process_code = str(process_code or "").strip().upper() or None
        if process_code is not None and not normalized_process_code:
            raise bad_request(
                code="PROCESS_CODE_REQUIRED",
                message="process_code must be non-empty when provided.",
            )

        reference_version_no = self._resolve_order_pool_version_no(version_no)
        if reference_version_no is None:
            return {
                "summary": {
                    "reference_version_no": None,
                    "bottleneck_process_code": None,
                    "bottleneck_process_name_cn": None,
                    "message": "鏆傛棤鎺掍骇浠诲姟鏁版嵁",
                },
                "process_items": [],
                "selected_process_detail": self._build_empty_selected_process_detail(
                    process_code=normalized_process_code,
                ),
            }

        order_task_rows = self._list_schedule_task_rows_by_version_order(
            version_no=reference_version_no,
            order_no=normalized_order_no,
        )
        if len(order_task_rows) == 0:
            return {
                "summary": {
                    "reference_version_no": reference_version_no,
                    "bottleneck_process_code": None,
                    "bottleneck_process_name_cn": None,
                    "message": "鏆傛棤鎺掍骇浠诲姟鏁版嵁",
                },
                "process_items": [],
                "selected_process_detail": self._build_empty_selected_process_detail(
                    process_code=normalized_process_code,
                ),
            }

        route_rows = self._group_routes_by_product(self._list_route_rows()).get(
            normalized_product_code,
            [],
        )
        process_stats_by_code = self._build_schedule_process_stats_by_code(
            self._list_schedule_task_detail_rows(reference_version_no),
        )
        process_items = self._build_order_process_timeline_items(
            task_rows=order_task_rows,
            route_rows=route_rows,
            process_stats_by_code=process_stats_by_code,
        )
        bottleneck_item = next(
            (item for item in process_items if int(item.get("is_bottleneck") or 0) == 1),
            None,
        )
        selected_process_detail = self._build_empty_selected_process_detail(
            process_code=normalized_process_code,
        )
        if normalized_process_code:
            selected_process_detail = self._build_selected_process_timeline_detail(
                version_no=reference_version_no,
                order_no=normalized_order_no,
                process_code=normalized_process_code,
                process_items=process_items,
            )

        return {
            "summary": {
                "reference_version_no": reference_version_no,
                "bottleneck_process_code": (
                    str(bottleneck_item.get("process_code") or "").strip().upper()
                    if bottleneck_item
                    else None
                ),
                "bottleneck_process_name_cn": (
                    str(
                        bottleneck_item.get("process_name_cn")
                        or bottleneck_item.get("process_code")
                        or ""
                    ).strip()
                    if bottleneck_item
                    else None
                ),
            },
            "process_items": process_items,
            "selected_process_detail": selected_process_detail,
        }

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
            "priority_level": _normalize_priority_level(current.get("priority_level"), PRIORITY_LEVEL_MAX),
            "urgent_flag": _urgent_flag_from_priority_level(current.get("priority_level")),
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
        expected_start_shift = str(payload.get("expected_start_shift") or "").strip().upper()
        if expected_start_shift and expected_start_shift not in {"DAY", "NIGHT"}:
            raise bad_request(
                code="ORDER_EXPECTED_START_SHIFT_INVALID",
                message="expected_start_shift must be DAY or NIGHT.",
            )
        if expected_start_date:
            next_row["expected_start_date"] = expected_start_date
            next_row["expected_start_time"] = _iso_at(
                expected_start_date,
                "20:00:00" if expected_start_shift == "NIGHT" else "08:00:00",
            )
        elif expected_start_shift:
            current_start_date = _normalize_date_text(current.get("expected_start_date"))
            if current_start_date is None:
                raise bad_request(
                    code="ORDER_EXPECTED_START_DATE_REQUIRED",
                    message="expected_start_date is required when expected_start_shift is provided.",
                )
            next_row["expected_start_time"] = _iso_at(
                current_start_date,
                "20:00:00" if expected_start_shift == "NIGHT" else "08:00:00",
            )

        if "priority_level" in payload:
            next_row["priority_level"] = _normalize_priority_level(payload.get("priority_level"), PRIORITY_LEVEL_MAX)
            next_row["urgent_flag"] = _urgent_flag_from_priority_level(next_row["priority_level"])
        elif "urgent_flag" in payload:
            next_row["priority_level"] = PRIORITY_LEVEL_MIN if int(payload["urgent_flag"] or 0) == 1 else PRIORITY_LEVEL_MAX
            next_row["urgent_flag"] = _urgent_flag_from_priority_level(next_row["priority_level"])

        for field in ("lock_flag", "frozen_flag"):
            if field in payload:
                next_row[field] = int(payload[field] or 0)

        status_value = str(payload.get("status") or "").strip().upper()
        order_status_value = str(payload.get("order_status") or "").strip().upper()
        if status_value:
            next_row["status"] = status_value
        if order_status_value:
            next_row["order_status"] = order_status_value

        if status_value == "DONE" or order_status_value == "DONE" or int(_to_number(payload.get("revoke_done_flag"), 0)) == 1:
            raise bad_request(
                code="ORDER_MANUAL_COMPLETION_FORBIDDEN",
                message="订单不能通过手工补丁直接完工或撤销完工，请使用末道报工更新订单状态。",
            )

        production_qty = _to_number(base_row.get("production_qty"), 0)
        normalized_status = str(
            next_row.get("order_status") or next_row.get("status") or ""
        ).strip().upper()
        if normalized_status in {"DONE", "COMPLETED"}:
            raise bad_request(
                code="ORDER_MANUAL_COMPLETION_FORBIDDEN",
                message="订单不能通过手工补丁直接完工，请使用末道报工更新订单状态。",
            )
        next_row["remaining_qty"] = max(0, _to_number(next_row.get("remaining_qty"), production_qty))
        next_row["progress_rate"] = max(0, _to_number(next_row.get("progress_rate"), 0))

        if "production_batch_no" in payload:
            next_row["production_batch_no"] = str(payload.get("production_batch_no") or "").strip() or None

        with transaction(self.connection):
            self._upsert_order_state(next_row)
        result = self.get_order_pool_item(order_no)
        result["save_impact"] = self._build_expected_start_save_impact(result)
        return result

    def delete_order_pool_order(self, order_no: str) -> dict[str, Any]:
        self._require_order(order_no)
        raise bad_request(
            code="ORDER_DELETE_FORBIDDEN",
            message="生产订单不允许物理删除，请使用 ERP 同步失效、关闭或后续审核能力处理。",
        )

    def list_mes_reportings(
        self,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.reporting_query_service.list_mes_reportings(
            start_time=start_time,
            end_time=end_time,
            current_user=current_user,
        )

    def list_reporting_import_files(self, *, limit: int = 50) -> dict[str, Any]:
        return self.reporting_query_service.list_reporting_import_files(limit=limit)

    def get_order_summary(
        self,
        *,
        start_date: str,
        end_date: str,
        workshop_manager_user_id: str | None = None,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.order_summary_query_service.get_order_summary(
            start_date=start_date,
            end_date=end_date,
            workshop_manager_user_id=workshop_manager_user_id,
            current_user=current_user,
        )

    def get_scheduler_dashboard(
        self,
        *,
        start_date: str,
        end_date: str,
        top_n: int = 8,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.dashboard_query_service.get_scheduler_dashboard(
            start_date=start_date,
            end_date=end_date,
            top_n=top_n,
            current_user=current_user,
        )

    def list_order_summary_workshop_managers(
        self,
        *,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.order_summary_query_service.list_order_summary_workshop_managers(
            current_user=current_user,
        )

    def list_line_daily_capacity(
        self,
        calendar_date: str,
        *,
        workshop_code: str | None = None,
        line_code: str | None = None,
        process_code: str | None = None,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.masterdata_query_service.list_line_daily_capacity(
            calendar_date,
            workshop_code=workshop_code,
            line_code=line_code,
            process_code=process_code,
            current_user=current_user,
        )

    def save_line_daily_capacity(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.line_daily_capacity_service.save_line_daily_capacity(payload)

    def list_line_daily_capacity_audits(
        self,
        calendar_date: str,
        *,
        workshop_code: str | None = None,
        line_code: str | None = None,
        process_code: str | None = None,
        operator_keyword: str | None = None,
        changed_only: bool = False,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.masterdata_query_service.list_line_daily_capacity_audits(
            calendar_date,
            workshop_code=workshop_code,
            line_code=line_code,
            process_code=process_code,
            operator_keyword=operator_keyword,
            changed_only=changed_only,
            current_user=current_user,
        )

    def rebuild_line_daily_actual_capacity(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.line_daily_capacity_service.rebuild_line_daily_actual_capacity(payload)

    def _rebuild_line_daily_actual_capacity_rows(
        self,
        normalized_date: str,
    ) -> tuple[int, int]:
        return self.line_daily_capacity_service._rebuild_line_daily_actual_capacity_rows(
            normalized_date
        )


    def create_reporting(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.reporting_command_service.create_reporting(payload)

    def import_mes_reportings_from_xlsx(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.reporting_command_service.import_mes_reportings_from_xlsx(payload)

    def select_reporting_capacity_compare(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.reporting_command_service.select_reporting_capacity_compare(payload)

    def delete_reporting(
        self,
        report_id: str,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.reporting_command_service.delete_reporting(report_id, actor)

    def list_schedule_versions(self) -> dict[str, Any]:
        rows = fetch_all(
            self.connection,
            """
            SELECT version_no, status, status_name_cn, strategy_code, created_at, published_at, result_status, result_summary
            FROM schedule_versions
            ORDER BY
                CASE
                    WHEN UPPER(TRIM(COALESCE(status, ''))) = 'CURRENT' THEN 0
                    ELSE 1
                END ASC,
                created_at DESC,
                CAST(
                    CASE
                        WHEN INSTR(version_no, '-D') > 0 THEN SUBSTR(version_no, INSTR(version_no, '-D') + 2)
                        ELSE '0'
                    END AS INTEGER
                ) DESC,
                version_no DESC
            """,
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["status_label"] = _schedule_version_status_label(row.get("status"))
            item["result_status_label"] = _schedule_result_status_label(row.get("result_status"))
            items.append(item)
        return {"items": items}

    def get_schedule_version(self, version_no: str) -> dict[str, Any]:
        row = fetch_one(
            self.connection,
            """
            SELECT version_no, status, status_name_cn, strategy_code, created_at, published_at, result_status, result_summary
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
        item = dict(row)
        item["status_label"] = _schedule_version_status_label(row.get("status"))
        item["result_status_label"] = _schedule_result_status_label(row.get("result_status"))
        return item

    def list_schedule_tasks(self, version_no: str) -> dict[str, Any]:
        self.get_schedule_version(version_no)
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

    def get_current_schedule(self) -> dict[str, Any]:
        return self.schedules_query_service.get_current_schedule()

    def list_current_schedule_tasks(self) -> dict[str, Any]:
        return self.schedules_query_service.list_current_schedule_tasks()

    def list_schedule_snapshots(self) -> dict[str, Any]:
        return self.schedules_query_service.list_schedule_snapshots()

    def _clone_schedule_version(
        self,
        source_version_no: str,
        *,
        target_status: str,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        source_version = self.get_schedule_version(source_version_no)
        source_tasks = self._list_schedule_task_rows_by_version(source_version_no)
        target_version_no = self._next_schedule_version_no()
        target_created_at = created_at or utc_now()
        status = str(target_status or "").strip().upper()
        if status not in {"CURRENT", "SAVED"}:
            raise bad_request(
                code="SCHEDULE_VERSION_STATUS_INVALID",
                message="排产方案状态无效。",
                details={"status": target_status},
            )
        with transaction(self.connection):
            if status == "CURRENT":
                self.connection.execute(
                    """
                    UPDATE schedule_versions
                    SET status = 'SAVED',
                        status_name_cn = ?
                    WHERE UPPER(TRIM(COALESCE(status, ''))) = 'CURRENT'
                    """,
                    (_status_name("SAVED"),),
                )
            self.connection.execute(
                """
                INSERT INTO schedule_versions (
                    version_no,
                    status,
                    status_name_cn,
                    strategy_code,
                    result_status,
                    result_summary,
                    created_at,
                    published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_version_no,
                    status,
                    _status_name(status),
                    str(source_version.get("strategy_code") or ""),
                    str(source_version.get("result_status") or "FEASIBLE"),
                    source_version.get("result_summary"),
                    target_created_at,
                    None,
                ),
            )
            if source_tasks:
                self.connection.executemany(
                    """
                    INSERT INTO schedule_tasks (
                        version_no,
                        task_no,
                        production_order_no,
                        process_code,
                        process_name_cn,
                        workshop_code,
                        line_code,
                        calendar_date,
                        shift_code,
                        plan_qty,
                        plan_start_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            target_version_no,
                            int(row.get("task_no") or 0),
                            row.get("production_order_no"),
                            row.get("process_code"),
                            row.get("process_name_cn"),
                            row.get("workshop_code"),
                            row.get("line_code"),
                            row.get("calendar_date"),
                            row.get("shift_code"),
                            row.get("plan_qty"),
                            row.get("plan_start_time"),
                        )
                        for row in source_tasks
                    ],
                )
        return {
            "version_no": target_version_no,
            "source_version_no": source_version_no,
            "status": status,
            "status_label": _schedule_version_status_label(status),
        }

    def _replace_current_schedule(
        self,
        *,
        strategy_code: str,
        result_status: str,
        result_summary: str,
        tasks: list[tuple[Any, ...]],
        order_rows: list[dict[str, Any]],
        states: dict[str, dict[str, Any]],
        created_at: str,
    ) -> None:
        with transaction(self.connection):
            self.connection.execute(
                """
                INSERT INTO current_schedule_meta (
                    singleton_key,
                    strategy_code,
                    result_status,
                    result_summary,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(singleton_key) DO UPDATE SET
                    strategy_code = excluded.strategy_code,
                    result_status = excluded.result_status,
                    result_summary = excluded.result_summary,
                    updated_at = excluded.updated_at
                """,
                (
                    "CURRENT",
                    strategy_code,
                    result_status,
                    result_summary,
                    created_at,
                ),
            )
            self.connection.execute("DELETE FROM current_schedule_tasks")
            if tasks:
                self.connection.executemany(
                    """
                    INSERT INTO current_schedule_tasks (
                        task_no,
                        production_order_no,
                        process_code,
                        process_name_cn,
                        workshop_code,
                        line_code,
                        calendar_date,
                        shift_code,
                        plan_qty,
                        plan_start_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [task[1:] for task in tasks],
                )
            self.connection.execute(
                """
                INSERT INTO schedule_versions (
                    version_no,
                    status,
                    status_name_cn,
                    strategy_code,
                    result_status,
                    result_summary,
                    created_at,
                    published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(version_no) DO UPDATE SET
                    status = excluded.status,
                    status_name_cn = excluded.status_name_cn,
                    strategy_code = excluded.strategy_code,
                    result_status = excluded.result_status,
                    result_summary = excluded.result_summary,
                    created_at = excluded.created_at,
                    published_at = excluded.published_at
                """,
                (
                    CURRENT_SCHEDULE_VERSION_NO,
                    "CURRENT",
                    _status_name("CURRENT"),
                    strategy_code,
                    result_status,
                    result_summary,
                    created_at,
                    None,
                ),
            )
            self.connection.execute(
                "DELETE FROM schedule_tasks WHERE version_no = ?",
                (CURRENT_SCHEDULE_VERSION_NO,),
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
                        workshop_code,
                        line_code,
                        calendar_date,
                        shift_code,
                        plan_qty,
                        plan_start_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tasks,
                )
                self._sync_order_pool_state_schedule_window_from_tasks(
                    tasks=tasks,
                    order_rows=order_rows,
                    states=states,
                )

    def save_current_schedule_version(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        current_meta = fetch_one(
            self.connection,
            """
            SELECT strategy_code, result_status, result_summary
            FROM current_schedule_meta
            WHERE singleton_key = 'CURRENT'
            """,
        )
        if current_meta is None:
            raise bad_request(
                code="SCHEDULE_CURRENT_VERSION_REQUIRED",
                message="当前没有可保存的排产方案，请先执行排产。",
            )
        current_tasks = fetch_all(
            self.connection,
            """
            SELECT
                task_no,
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
        snapshot_id = self._next_schedule_version_no()
        with transaction(self.connection):
            self.connection.execute(
                """
                INSERT INTO schedule_snapshots (
                    snapshot_id,
                    snapshot_name,
                    strategy_code,
                    result_status,
                    result_summary,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    snapshot_id,
                    str(current_meta.get("strategy_code") or ""),
                    str(current_meta.get("result_status") or "FEASIBLE"),
                    current_meta.get("result_summary"),
                    utc_now(),
                ),
            )
            if current_tasks:
                self.connection.executemany(
                    """
                    INSERT INTO schedule_snapshot_tasks (
                        snapshot_id,
                        task_no,
                        production_order_no,
                        process_code,
                        process_name_cn,
                        workshop_code,
                        line_code,
                        calendar_date,
                        shift_code,
                        plan_qty,
                        plan_start_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            snapshot_id,
                            int(row.get("task_no") or 0),
                            row.get("production_order_no"),
                            row.get("process_code"),
                            row.get("process_name_cn"),
                            row.get("workshop_code"),
                            row.get("line_code"),
                            row.get("calendar_date"),
                            row.get("shift_code"),
                            row.get("plan_qty"),
                            row.get("plan_start_time"),
                        )
                        for row in current_tasks
                    ],
                )
        return {
            "snapshot_id": snapshot_id,
            "snapshot_name": snapshot_id,
            "status": "SAVED",
            "status_label": _schedule_version_status_label("SAVED"),
        }

    def load_saved_schedule_version(self, version_no: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        selected_snapshot = fetch_one(
            self.connection,
            """
            SELECT snapshot_id, strategy_code, result_status, result_summary
            FROM schedule_snapshots
            WHERE snapshot_id = ?
            """,
            (version_no,),
        )
        if selected_snapshot is None:
            raise not_found(
                code="SCHEDULE_SNAPSHOT_NOT_FOUND",
                message="Saved schedule snapshot does not exist.",
                details={"snapshot_id": version_no},
            )
        selected_tasks = fetch_all(
            self.connection,
            """
            SELECT
                task_no,
                production_order_no,
                process_code,
                process_name_cn,
                workshop_code,
                line_code,
                calendar_date,
                shift_code,
                plan_qty,
                plan_start_time
            FROM schedule_snapshot_tasks
            WHERE snapshot_id = ?
            ORDER BY task_no ASC
            """,
            (version_no,),
        )
        created_at = utc_now()
        tasks = [
            (
                CURRENT_SCHEDULE_VERSION_NO,
                int(row.get("task_no") or 0),
                row.get("production_order_no"),
                row.get("process_code"),
                row.get("process_name_cn"),
                row.get("workshop_code"),
                row.get("line_code"),
                row.get("calendar_date"),
                row.get("shift_code"),
                row.get("plan_qty"),
                row.get("plan_start_time"),
            )
            for row in selected_tasks
        ]
        order_rows = self._list_order_rows()
        states = self._get_order_state_map(
            [str(row["production_order_no"]) for row in order_rows]
        )
        self._replace_current_schedule(
            strategy_code=str(selected_snapshot.get("strategy_code") or ""),
            result_status=str(selected_snapshot.get("result_status") or "FEASIBLE"),
            result_summary=str(selected_snapshot.get("result_summary") or ""),
            tasks=tasks,
            order_rows=order_rows,
            states=states,
            created_at=created_at,
        )
        return {
            "schedule_id": CURRENT_SCHEDULE_VERSION_NO,
            "loaded_snapshot_id": version_no,
            "status": "CURRENT",
            "status_label": _schedule_version_status_label("CURRENT"),
        }

    def _pick_current_schedule_version_no(self) -> str | None:
        row = fetch_one(
            self.connection,
            """
            SELECT version_no
            FROM schedule_versions
            WHERE UPPER(TRIM(COALESCE(status, ''))) IN ('CURRENT', 'PUBLISHED')
            ORDER BY
                CASE
                    WHEN UPPER(TRIM(COALESCE(status, ''))) = 'CURRENT' THEN 0
                    ELSE 1
                END,
                COALESCE(NULLIF(TRIM(COALESCE(published_at, '')), ''), created_at) DESC,
                created_at DESC,
                version_no DESC
            LIMIT 1
            """,
        )
        if row is None:
            return None
        version_no = str(row.get("version_no") or "").strip()
        return version_no or None

    def _resolve_order_pool_version_no(self, version_no: str | None) -> str | None:
        normalized_version_no = str(version_no or "").strip()
        if normalized_version_no:
            self.get_schedule_version(normalized_version_no)
            return normalized_version_no
        return self._pick_current_schedule_version_no()

    def _list_schedule_task_rows_by_version_order(
        self,
        *,
        version_no: str,
        order_no: str,
    ) -> list[dict[str, Any]]:
        return fetch_all(
            self.connection,
            """
            SELECT
                st.task_no,
                st.version_no,
                st.production_order_no,
                st.process_code,
                COALESCE(st.process_name_cn, st.process_code) AS process_name_cn,
                st.workshop_code,
                st.line_code,
                st.calendar_date,
                st.shift_code,
                st.plan_qty,
                st.plan_start_time,
                po.material_code,
                COALESCE(po.material_name, po.material_code) AS material_name,
                po.production_qty
            FROM schedule_tasks st
            JOIN production_orders po
              ON po.production_order_no = st.production_order_no
            WHERE st.version_no = ?
              AND st.production_order_no = ?
            ORDER BY st.task_no ASC
            """,
            (version_no, order_no),
        )

    def _list_schedule_task_rows_by_version_process(
        self,
        *,
        version_no: str,
        process_code: str,
    ) -> list[dict[str, Any]]:
        return fetch_all(
            self.connection,
            """
            SELECT
                st.task_no,
                st.version_no,
                st.production_order_no,
                st.process_code,
                COALESCE(st.process_name_cn, st.process_code) AS process_name_cn,
                st.workshop_code,
                st.line_code,
                st.calendar_date,
                st.shift_code,
                st.plan_qty,
                st.plan_start_time,
                po.material_code,
                COALESCE(po.material_name, po.material_code) AS material_name,
                po.production_qty
            FROM schedule_tasks st
            JOIN production_orders po
              ON po.production_order_no = st.production_order_no
            WHERE st.version_no = ?
              AND UPPER(TRIM(COALESCE(st.process_code, ''))) = ?
            ORDER BY st.task_no ASC
            """,
            (version_no, process_code),
        )

    def _parse_iso_datetime_strict(
        self,
        value: object,
        *,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> datetime:
        text = str(value or "").strip()
        if not text:
            raise server_error(
                code=error_code,
                message=message,
                details=details or {},
            )
        try:
            return datetime.fromisoformat(text)
        except ValueError as exc:
            raise server_error(
                code=error_code,
                message=message,
                details={
                    **(details or {}),
                    "value": text,
                },
            ) from exc

    def _task_start_time_from_schedule_row(self, row: dict[str, Any]) -> str:
        plan_start_time = str(row.get("plan_start_time") or "").strip()
        if plan_start_time:
            return plan_start_time

        calendar_date = _normalize_date_text(row.get("calendar_date"))
        if not calendar_date:
            raise server_error(
                code="SCHEDULE_TASK_CALENDAR_DATE_INVALID",
                message="schedule task calendar_date is required.",
                details={
                    "version_no": row.get("version_no"),
                    "task_no": row.get("task_no"),
                    "order_no": row.get("production_order_no"),
                },
            )
        shift_code = _normalize_shift_code(row.get("shift_code"))
        return str(
            _iso_at(
                calendar_date,
                "08:00:00" if shift_code == "DAY" else "20:00:00",
            )
            or ""
        )

    def _task_finish_time_from_schedule_row(self, row: dict[str, Any]) -> str:
        calendar_date = _normalize_date_text(row.get("calendar_date"))
        if not calendar_date:
            raise server_error(
                code="SCHEDULE_TASK_CALENDAR_DATE_INVALID",
                message="schedule task calendar_date is required.",
                details={
                    "version_no": row.get("version_no"),
                    "task_no": row.get("task_no"),
                    "order_no": row.get("production_order_no"),
                },
            )
        calendar_day = date.fromisoformat(calendar_date)
        shift_code = _normalize_shift_code(row.get("shift_code"))
        if shift_code == "NIGHT":
            return str(
                _iso_at(
                    (calendar_day + timedelta(days=1)).isoformat(),
                    "08:00:00",
                )
                or ""
            )
        return str(_iso_at(calendar_day.isoformat(), "20:00:00") or "")

    def _build_order_process_timeline_items(
        self,
        *,
        task_rows: list[dict[str, Any]],
        route_rows: list[dict[str, Any]],
        process_stats_by_code: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        route_by_process: dict[str, dict[str, Any]] = {}
        for route_row in route_rows:
            process_code = str(route_row.get("process_code") or "").strip().upper()
            if process_code and process_code not in route_by_process:
                route_by_process[process_code] = route_row

        grouped: dict[str, dict[str, Any]] = {}
        for task_row in task_rows:
            process_code = str(task_row.get("process_code") or "").strip().upper()
            if not process_code:
                raise server_error(
                    code="SCHEDULE_TASK_PROCESS_CODE_MISSING",
                    message="schedule task process_code is required.",
                    details={
                        "version_no": task_row.get("version_no"),
                        "task_no": task_row.get("task_no"),
                        "order_no": task_row.get("production_order_no"),
                    },
                )
            route_row = route_by_process.get(process_code, {})
            process_name_cn = str(
                task_row.get("process_name_cn")
                or route_row.get("process_name_cn")
                or process_code
            ).strip() or process_code
            start_time = self._task_start_time_from_schedule_row(task_row)
            finish_time = self._task_finish_time_from_schedule_row(task_row)
            start_dt = self._parse_iso_datetime_strict(
                start_time,
                error_code="SCHEDULE_TASK_START_TIME_INVALID",
                message="schedule task start_time is invalid.",
                details={
                    "version_no": task_row.get("version_no"),
                    "task_no": task_row.get("task_no"),
                    "order_no": task_row.get("production_order_no"),
                    "process_code": process_code,
                },
            )
            finish_dt = self._parse_iso_datetime_strict(
                finish_time,
                error_code="SCHEDULE_TASK_FINISH_TIME_INVALID",
                message="schedule task finish_time is invalid.",
                details={
                    "version_no": task_row.get("version_no"),
                    "task_no": task_row.get("task_no"),
                    "order_no": task_row.get("production_order_no"),
                    "process_code": process_code,
                },
            )
            if finish_dt < start_dt:
                raise server_error(
                    code="SCHEDULE_TASK_TIME_RANGE_INVALID",
                    message="schedule task finish_time must be >= start_time.",
                    details={
                        "version_no": task_row.get("version_no"),
                        "task_no": task_row.get("task_no"),
                        "order_no": task_row.get("production_order_no"),
                        "process_code": process_code,
                        "start_time": start_time,
                        "finish_time": finish_time,
                    },
                )
            current = grouped.get(process_code)
            if current is None:
                grouped[process_code] = {
                    "process_code": process_code,
                    "process_name_cn": process_name_cn,
                    "sequence_no": int(_to_number(route_row.get("sequence_no"), 10**9)),
                    "start_time": start_time,
                    "finish_time": finish_time,
                    "start_dt": start_dt,
                    "finish_dt": finish_dt,
                    "plan_qty_total": _to_number(task_row.get("plan_qty"), 0),
                }
                continue
            if start_dt < current["start_dt"]:
                current["start_dt"] = start_dt
                current["start_time"] = start_time
            if finish_dt > current["finish_dt"]:
                current["finish_dt"] = finish_dt
                current["finish_time"] = finish_time
            current["plan_qty_total"] = _to_number(current.get("plan_qty_total"), 0) + _to_number(
                task_row.get("plan_qty"),
                0,
            )

        items: list[dict[str, Any]] = []
        for current in grouped.values():
            process_code = str(current.get("process_code") or "").strip().upper()
            process_stats = process_stats_by_code.get(process_code)
            if process_stats is None:
                raise server_error(
                    code="SCHEDULE_PROCESS_STATS_MISSING",
                    message="schedule process stats are required.",
                    details={
                        "process_code": process_code,
                    },
                )
            duration_hours = (
                (current["finish_dt"] - current["start_dt"]).total_seconds() / 3600
            )
            items.append(
                {
                    "process_code": process_code,
                    "process_name_cn": current["process_name_cn"],
                    "start_time": current["start_time"],
                    "finish_time": current["finish_time"],
                    "duration_hours": round(duration_hours, 4),
                    "related_order_count": int(
                        _to_number(process_stats.get("related_order_count"), 0)
                    ),
                    "plan_qty_total": round(
                        _to_number(process_stats.get("plan_qty_total"), 0),
                        4,
                    ),
                    "is_bottleneck": 0,
                    "sequence_no": int(_to_number(current.get("sequence_no"), 10**9)),
                }
            )

        items.sort(
            key=lambda item: (
                int(_to_number(item.get("sequence_no"), 10**9)),
                str(item.get("process_code") or ""),
            )
        )
        if items:
            max_duration_hours = max(
                _to_number(item.get("duration_hours"), 0)
                for item in items
            )
            bottleneck_candidates = [
                item
                for item in items
                if _to_number(item.get("duration_hours"), 0) == max_duration_hours
            ]
            bottleneck = min(
                bottleneck_candidates,
                key=lambda item: (
                    int(_to_number(item.get("sequence_no"), 10**9)),
                    str(item.get("process_code") or ""),
                ),
            )
            bottleneck_code = str(bottleneck.get("process_code") or "").strip().upper()
            for item in items:
                item["is_bottleneck"] = (
                    1
                    if str(item.get("process_code") or "").strip().upper()
                    == bottleneck_code
                    else 0
                )
        for item in items:
            item.pop("sequence_no", None)
        return items

    def _build_schedule_process_stats_by_code(
        self,
        task_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for task_row in task_rows:
            process_code = str(task_row.get("process_code") or "").strip().upper()
            if not process_code:
                raise server_error(
                    code="SCHEDULE_TASK_PROCESS_CODE_MISSING",
                    message="schedule task process_code is required.",
                    details={
                        "version_no": task_row.get("version_no"),
                        "task_no": task_row.get("task_no"),
                        "order_no": task_row.get("production_order_no"),
                    },
                )
            order_no = str(task_row.get("production_order_no") or "").strip()
            if not order_no:
                raise server_error(
                    code="SCHEDULE_TASK_ORDER_NO_MISSING",
                    message="schedule task production_order_no is required.",
                    details={
                        "version_no": task_row.get("version_no"),
                        "task_no": task_row.get("task_no"),
                        "process_code": process_code,
                    },
                )
            current = grouped.get(process_code)
            if current is None:
                current = {
                    "plan_qty_total": 0.0,
                    "order_no_set": set(),
                }
                grouped[process_code] = current
            current["plan_qty_total"] = _to_number(
                current.get("plan_qty_total"),
                0,
            ) + _to_number(task_row.get("plan_qty"), 0)
            order_no_set = current.get("order_no_set")
            if not isinstance(order_no_set, set):
                raise server_error(
                    code="SCHEDULE_PROCESS_ORDER_SET_INVALID",
                    message="schedule process order set is invalid.",
                    details={
                        "process_code": process_code,
                    },
                )
            order_no_set.add(order_no)

        return {
            process_code: {
                "related_order_count": len(current.get("order_no_set") or set()),
                "plan_qty_total": round(_to_number(current.get("plan_qty_total"), 0), 4),
            }
            for process_code, current in grouped.items()
        }

    def _build_empty_selected_process_detail(
        self,
        *,
        process_code: str | None,
    ) -> dict[str, Any] | None:
        if not process_code:
            return None
        return {
            "process_code": process_code,
            "process_name_cn": process_code,
            "current_order_finish_time": None,
            "order_timeline_items": [],
            "message": "鏆傛棤鎺掍骇浠诲姟鏁版嵁",
        }

    def _build_selected_process_timeline_detail(
        self,
        *,
        version_no: str,
        order_no: str,
        process_code: str,
        process_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_process_code = str(process_code or "").strip().upper()
        selected_process_row = next(
            (
                item
                for item in process_items
                if str(item.get("process_code") or "").strip().upper() == normalized_process_code
            ),
            None,
        )
        process_name_cn = str(
            (selected_process_row or {}).get("process_name_cn") or normalized_process_code
        ).strip() or normalized_process_code

        task_rows = self._list_schedule_task_rows_by_version_process(
            version_no=version_no,
            process_code=normalized_process_code,
        )
        grouped: dict[str, dict[str, Any]] = {}
        for task_row in task_rows:
            current_order_no = str(task_row.get("production_order_no") or "").strip()
            if not current_order_no:
                continue
            start_time = self._task_start_time_from_schedule_row(task_row)
            finish_time = self._task_finish_time_from_schedule_row(task_row)
            start_dt = self._parse_iso_datetime_strict(
                start_time,
                error_code="SCHEDULE_TASK_START_TIME_INVALID",
                message="schedule task start_time is invalid.",
                details={
                    "version_no": task_row.get("version_no"),
                    "task_no": task_row.get("task_no"),
                    "order_no": current_order_no,
                    "process_code": normalized_process_code,
                },
            )
            finish_dt = self._parse_iso_datetime_strict(
                finish_time,
                error_code="SCHEDULE_TASK_FINISH_TIME_INVALID",
                message="schedule task finish_time is invalid.",
                details={
                    "version_no": task_row.get("version_no"),
                    "task_no": task_row.get("task_no"),
                    "order_no": current_order_no,
                    "process_code": normalized_process_code,
                },
            )
            if finish_dt < start_dt:
                raise server_error(
                    code="SCHEDULE_TASK_TIME_RANGE_INVALID",
                    message="schedule task finish_time must be >= start_time.",
                    details={
                        "version_no": task_row.get("version_no"),
                        "task_no": task_row.get("task_no"),
                        "order_no": current_order_no,
                        "process_code": normalized_process_code,
                        "start_time": start_time,
                        "finish_time": finish_time,
                    },
                )

            current = grouped.get(current_order_no)
            if current is None:
                grouped[current_order_no] = {
                    "order_no": current_order_no,
                    "product_code": str(task_row.get("material_code") or "").strip().upper() or None,
                    "product_name_cn": str(
                        task_row.get("material_name") or task_row.get("material_code") or ""
                    ).strip() or None,
                    "start_time": start_time,
                    "finish_time": finish_time,
                    "start_dt": start_dt,
                    "finish_dt": finish_dt,
                    "plan_qty_total": _to_number(task_row.get("plan_qty"), 0),
                }
                continue
            if start_dt < current["start_dt"]:
                current["start_dt"] = start_dt
                current["start_time"] = start_time
            if finish_dt > current["finish_dt"]:
                current["finish_dt"] = finish_dt
                current["finish_time"] = finish_time
            current["plan_qty_total"] = _to_number(current.get("plan_qty_total"), 0) + _to_number(
                task_row.get("plan_qty"),
                0,
            )

        order_timeline_items: list[dict[str, Any]] = []
        for row in grouped.values():
            duration_hours = (row["finish_dt"] - row["start_dt"]).total_seconds() / 3600
            order_timeline_items.append(
                {
                    "order_no": row["order_no"],
                    "product_code": row["product_code"],
                    "product_name_cn": row["product_name_cn"],
                    "start_time": row["start_time"],
                    "finish_time": row["finish_time"],
                    "duration_hours": round(duration_hours, 4),
                    "plan_qty_total": _to_number(row.get("plan_qty_total"), 0),
                }
            )
        order_timeline_items.sort(
            key=lambda item: (
                str(item.get("start_time") or ""),
                str(item.get("order_no") or ""),
            )
        )

        current_order_item = next(
            (
                item
                for item in order_timeline_items
                if str(item.get("order_no") or "").strip() == order_no
            ),
            None,
        )
        current_order_finish_time = (
            str(current_order_item.get("finish_time") or "").strip()
            if current_order_item
            else (
                str((selected_process_row or {}).get("finish_time") or "").strip()
                or None
            )
        )

        detail: dict[str, Any] = {
            "process_code": normalized_process_code,
            "process_name_cn": process_name_cn,
            "current_order_finish_time": current_order_finish_time,
            "order_timeline_items": order_timeline_items,
        }
        if len(order_timeline_items) == 0:
            detail["message"] = "鏆傛棤鎺掍骇浠诲姟鏁版嵁"
        return detail

    def _pick_schedule_compare_version(self, version_no: str) -> dict[str, Any] | None:
        rows = fetch_all(
            self.connection,
            """
            SELECT version_no, status, status_name_cn, strategy_code, created_at, published_at
            FROM schedule_versions
            WHERE version_no <> ?
            ORDER BY
                CASE
                    WHEN UPPER(TRIM(COALESCE(status, ''))) = 'CURRENT' THEN 0
                    ELSE 1
                END ASC,
                created_at DESC,
                version_no DESC
            """,
            (version_no,),
        )
        if not rows:
            return None
        saved_rows = [
            row for row in rows if str(row.get("status") or "").strip().upper() == "SAVED"
        ]
        if saved_rows:
            return saved_rows[0]
        return rows[0]

    def _list_schedule_task_detail_rows(self, version_no: str) -> list[dict[str, Any]]:
        return fetch_all(
            self.connection,
            """
            SELECT
                st.version_no,
                st.task_no,
                st.production_order_no,
                st.process_code,
                COALESCE(st.process_name_cn, st.process_code) AS process_name_cn,
                st.workshop_code,
                st.line_code,
                st.calendar_date,
                st.shift_code,
                st.plan_qty,
                st.plan_start_time,
                po.material_code,
                COALESCE(po.material_name, po.material_code) AS material_name,
                po.production_qty,
                po.planned_end_date
            FROM schedule_tasks st
            JOIN production_orders po
              ON po.production_order_no = st.production_order_no
            WHERE st.version_no = ?
            ORDER BY st.task_no ASC
            """,
            (version_no,),
        )

    def _build_schedule_order_summary_map(
        self,
        task_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in task_rows:
            order_no = str(row.get("production_order_no") or "").strip()
            if not order_no:
                continue
            current = out.get(order_no)
            if current is None:
                current = {
                    "order_no": order_no,
                    "material_code": str(row.get("material_code") or "").strip(),
                    "material_name": str(row.get("material_name") or row.get("material_code") or "").strip(),
                    "order_qty": _to_number(row.get("production_qty"), 0),
                    "due_date": _normalize_date_text(row.get("planned_end_date")),
                    "start_date": None,
                    "finish_date": None,
                    "task_count": 0,
                    "planned_qty": 0.0,
                    "signature_parts": [],
                    "process_codes": set(),
                    "date_set": set(),
                    "shift_set": set(),
                }
                out[order_no] = current
            calendar_date = _normalize_date_text(row.get("calendar_date"))
            if calendar_date and (current["start_date"] is None or calendar_date < current["start_date"]):
                current["start_date"] = calendar_date
            if calendar_date and (current["finish_date"] is None or calendar_date > current["finish_date"]):
                current["finish_date"] = calendar_date
            process_code = str(row.get("process_code") or "").strip().upper()
            shift_code = _normalize_shift_code(row.get("shift_code"))
            plan_qty = _to_number(row.get("plan_qty"), 0)
            current["task_count"] += 1
            current["planned_qty"] += plan_qty
            if process_code:
                current["process_codes"].add(process_code)
            if calendar_date:
                current["date_set"].add(calendar_date)
            if shift_code:
                current["shift_set"].add(shift_code)
            current["signature_parts"].append(
                "|".join(
                    [
                        calendar_date or "",
                        process_code,
                        shift_code,
                        f"{plan_qty:.6f}",
                    ]
                )
            )
        for row in out.values():
            row["signature"] = ";".join(sorted(row["signature_parts"]))
            row["process_codes"] = sorted(row["process_codes"])
            row["date_set"] = sorted(row["date_set"])
            row["shift_set"] = sorted(row["shift_set"])
            order_qty = _to_number(row.get("order_qty"), 0)
            if order_qty > 0:
                row["planned_ratio"] = max(0.0, min(1.0, _to_number(row["planned_qty"], 0) / order_qty))
            else:
                row["planned_ratio"] = 0.0
        return out

    def _build_schedule_delivery_changes(
        self,
        *,
        current_orders: dict[str, dict[str, Any]],
        compare_orders: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for order_no in sorted(set(current_orders) | set(compare_orders)):
            current = current_orders.get(order_no)
            compare = compare_orders.get(order_no)
            change_type = "UNCHANGED"
            if current and not compare:
                change_type = "ADDED"
            elif compare and not current:
                change_type = "REMOVED"
            elif current and compare:
                current_finish = current.get("finish_date")
                compare_finish = compare.get("finish_date")
                if current_finish and compare_finish and current_finish < compare_finish:
                    change_type = "EARLIER_FINISH"
                elif current_finish and compare_finish and current_finish > compare_finish:
                    change_type = "LATER_FINISH"
            if change_type == "UNCHANGED":
                continue
            selected_finish = current.get("finish_date") if current else None
            compare_finish = compare.get("finish_date") if compare else None
            selected_due = current.get("due_date") if current else compare.get("due_date") if compare else None
            compare_due = compare.get("due_date") if compare else current.get("due_date") if current else None
            items.append(
                {
                    "order_no": order_no,
                    "material_code": (current or compare or {}).get("material_code"),
                    "material_name": (current or compare or {}).get("material_name"),
                    "change_type": change_type,
                    "selected_finish_date": selected_finish,
                    "compare_finish_date": compare_finish,
                    "selected_due_date": selected_due,
                    "compare_due_date": compare_due,
                    "selected_overdue_days": _days_between(selected_due, selected_finish),
                    "compare_overdue_days": _days_between(compare_due, compare_finish),
                }
            )
        return {"items": items}

    def _build_schedule_schedule_changes(
        self,
        *,
        current_orders: dict[str, dict[str, Any]],
        compare_orders: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for order_no in sorted(set(current_orders) | set(compare_orders)):
            current = current_orders.get(order_no)
            compare = compare_orders.get(order_no)
            change_type = "UNCHANGED"
            if current and not compare:
                change_type = "ADDED"
            elif compare and not current:
                change_type = "REMOVED"
            elif current and compare:
                if current.get("start_date") != compare.get("start_date"):
                    change_type = "START_CHANGED"
                elif current.get("finish_date") != compare.get("finish_date"):
                    change_type = "FINISH_CHANGED"
                elif current.get("signature") != compare.get("signature"):
                    change_type = "TASK_CHANGED"
            if change_type == "UNCHANGED":
                continue
            items.append(
                {
                    "order_no": order_no,
                    "material_code": (current or compare or {}).get("material_code"),
                    "material_name": (current or compare or {}).get("material_name"),
                    "change_type": change_type,
                    "selected_start_date": current.get("start_date") if current else None,
                    "compare_start_date": compare.get("start_date") if compare else None,
                    "selected_finish_date": current.get("finish_date") if current else None,
                    "compare_finish_date": compare.get("finish_date") if compare else None,
                    "selected_task_count": int(current.get("task_count") or 0) if current else 0,
                    "compare_task_count": int(compare.get("task_count") or 0) if compare else 0,
                    "selected_planned_qty": _to_number(current.get("planned_qty"), 0) if current else 0,
                    "compare_planned_qty": _to_number(compare.get("planned_qty"), 0) if compare else 0,
                }
            )
        return {"items": items}

    def _build_schedule_line_changes(
        self,
        *,
        current_tasks: list[dict[str, Any]],
        compare_tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        binding_rows = fetch_all(
            self.connection,
            """
            SELECT production_order_no, process_code, workshop_code, line_code
            FROM capacity_bindings
            """
        )
        if len(binding_rows) == 0:
            return {
                "available": False,
                "reason": "schedule_tasks does not store workshop_code/line_code, and capacity_bindings is empty.",
                "items": [],
            }

        binding_map: dict[tuple[str, str], tuple[str, str]] = {}
        for row in binding_rows:
            key = (
                str(row.get("production_order_no") or "").strip(),
                str(row.get("process_code") or "").strip().upper(),
            )
            value = (
                str(row.get("workshop_code") or "").strip().upper(),
                str(row.get("line_code") or "").strip().upper(),
            )
            if key in binding_map and binding_map[key] != value:
                return {
                    "available": False,
                    "reason": "capacity_bindings contains multiple workshop/line mappings for the same order and process.",
                    "items": [],
                }
            binding_map[key] = value

        def summarize(task_rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
            out: dict[tuple[str, str], dict[str, Any]] = {}
            for row in task_rows:
                order_no = str(row.get("production_order_no") or "").strip()
                process_code = str(row.get("process_code") or "").strip().upper()
                if not order_no or not process_code:
                    continue
                mapping = binding_map.get((order_no, process_code))
                if mapping is None:
                    continue
                workshop_code, line_code = mapping
                key = (order_no, process_code)
                current = out.get(key)
                if current is None:
                    current = {
                        "order_no": order_no,
                        "process_code": process_code,
                        "process_name_cn": str(row.get("process_name_cn") or process_code),
                        "workshop_code": workshop_code,
                        "line_code": line_code,
                        "start_date": None,
                        "finish_date": None,
                    }
                    out[key] = current
                date_text = _normalize_date_text(row.get("calendar_date"))
                if date_text and (current["start_date"] is None or date_text < current["start_date"]):
                    current["start_date"] = date_text
                if date_text and (current["finish_date"] is None or date_text > current["finish_date"]):
                    current["finish_date"] = date_text
            return out

        current_map = summarize(current_tasks)
        compare_map = summarize(compare_tasks)
        items: list[dict[str, Any]] = []
        for key in sorted(set(current_map) | set(compare_map)):
            current = current_map.get(key)
            compare = compare_map.get(key)
            if current is None or compare is None:
                continue
            if (
                current["workshop_code"] == compare["workshop_code"]
                and current["line_code"] == compare["line_code"]
                and current["start_date"] == compare["start_date"]
                and current["finish_date"] == compare["finish_date"]
            ):
                continue
            items.append(
                {
                    "order_no": key[0],
                    "process_code": key[1],
                    "process_name_cn": current.get("process_name_cn") or compare.get("process_name_cn"),
                    "selected_workshop_code": current.get("workshop_code"),
                    "selected_line_code": current.get("line_code"),
                    "compare_workshop_code": compare.get("workshop_code"),
                    "compare_line_code": compare.get("line_code"),
                    "selected_start_date": current.get("start_date"),
                    "selected_finish_date": current.get("finish_date"),
                    "compare_start_date": compare.get("start_date"),
                    "compare_finish_date": compare.get("finish_date"),
                }
            )
        return {"available": True, "reason": "", "items": items}

    def _list_schedule_material_rows(self) -> list[dict[str, Any]]:
        return fetch_all(
            self.connection,
            """
            SELECT
                mi.production_order_no,
                mi.child_material_code,
                mi.child_material_name,
                mi.issue_qty,
                COALESCE(sc.supply_type_code, mi.supply_type_code, '') AS supply_type_code,
                COALESCE(sc.supply_type_name, mi.supply_type_name, '-') AS supply_type_name,
                COALESCE(ic.inventory_qty, mi.inventory_qty, 0) AS inventory_qty,
                mi.expandable
            FROM material_issue_items mi
            LEFT JOIN inventory_cache ic
              ON ic.material_code = mi.child_material_code
            LEFT JOIN material_supply_cache sc
              ON sc.material_code = mi.child_material_code
            """
        )

    def _list_schedule_bom_child_rows(self, parent_material_code: str) -> list[dict[str, Any]]:
        return fetch_all(
            self.connection,
            """
            SELECT
                bc.parent_material_code,
                bc.child_material_code,
                bc.child_material_name,
                bc.usage_numerator,
                bc.usage_denominator,
                COALESCE(sc.supply_type_code, bc.supply_type_code, '') AS supply_type_code,
                COALESCE(sc.supply_type_name, bc.supply_type_name, '-') AS supply_type_name,
                COALESCE(ic.inventory_qty, bc.inventory_qty, 0) AS inventory_qty,
                bc.expandable
            FROM bom_children bc
            LEFT JOIN inventory_cache ic
              ON ic.material_code = bc.child_material_code
            LEFT JOIN material_supply_cache sc
              ON sc.material_code = bc.child_material_code
            WHERE bc.parent_material_code = ?
            ORDER BY bc.display_order, bc.child_material_code
            """,
            (parent_material_code,),
        )

    def _expand_schedule_material_children(
        self,
        *,
        production_order_no: str,
        parent_material_code: str,
        parent_issue_qty: float,
        bom_child_cache: dict[str, list[dict[str, Any]]],
        lineage: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        normalized_parent_code = str(parent_material_code or "").strip().upper()
        if not normalized_parent_code or parent_issue_qty <= SCHEDULE_NUMBER_EPSILON:
            return []
        child_rows = bom_child_cache.get(normalized_parent_code)
        if child_rows is None:
            child_rows = self._list_schedule_bom_child_rows(normalized_parent_code)
            bom_child_cache[normalized_parent_code] = child_rows
        if not child_rows:
            return []

        out: list[dict[str, Any]] = []
        for child_row in child_rows:
            child_material_code = str(child_row.get("child_material_code") or "").strip().upper()
            if not child_material_code:
                continue
            if child_material_code in lineage:
                raise server_error(
                    code="BOM_CHILDREN_CYCLE_DETECTED",
                    message="BOM children contain a cycle and cannot be used for shortage analysis.",
                    details={
                        "parent_material_code": normalized_parent_code,
                        "child_material_code": child_material_code,
                        "lineage": list(lineage),
                    },
                )

            usage_denominator = _to_number(child_row.get("usage_denominator"), 0)
            usage_numerator = _to_number(child_row.get("usage_numerator"), 0)
            if usage_denominator <= SCHEDULE_NUMBER_EPSILON or usage_numerator <= SCHEDULE_NUMBER_EPSILON:
                continue

            child_issue_qty = parent_issue_qty * usage_numerator / usage_denominator
            if child_issue_qty <= SCHEDULE_NUMBER_EPSILON:
                continue

            derived_row = {
                "production_order_no": production_order_no,
                "child_material_code": child_material_code,
                "child_material_name": child_row.get("child_material_name"),
                "issue_qty": child_issue_qty,
                "supply_type_code": child_row.get("supply_type_code"),
                "supply_type_name": child_row.get("supply_type_name"),
                "inventory_qty": child_row.get("inventory_qty"),
                "expandable": child_row.get("expandable"),
            }
            out.append(derived_row)

            supply_type_code = str(child_row.get("supply_type_code") or "").strip().upper()
            is_expandable = supply_type_code == "SELF_MADE" or int(child_row.get("expandable") or 0) == 1
            if is_expandable:
                out.extend(
                    self._expand_schedule_material_children(
                        production_order_no=production_order_no,
                        parent_material_code=child_material_code,
                        parent_issue_qty=child_issue_qty,
                        bom_child_cache=bom_child_cache,
                        lineage=(*lineage, child_material_code),
                    )
                )
        return out

    def _list_expanded_schedule_material_rows(self) -> list[dict[str, Any]]:
        root_rows = self._list_schedule_material_rows()
        bom_child_cache: dict[str, list[dict[str, Any]]] = {}
        expanded_rows = list(root_rows)
        for row in root_rows:
            production_order_no = str(row.get("production_order_no") or "").strip()
            parent_material_code = str(row.get("child_material_code") or "").strip().upper()
            parent_issue_qty = _to_number(row.get("issue_qty"), 0)
            supply_type_code = str(row.get("supply_type_code") or "").strip().upper()
            is_expandable = supply_type_code == "SELF_MADE" or int(row.get("expandable") or 0) == 1
            if not production_order_no or not parent_material_code or not is_expandable:
                continue
            expanded_rows.extend(
                self._expand_schedule_material_children(
                    production_order_no=production_order_no,
                    parent_material_code=parent_material_code,
                    parent_issue_qty=parent_issue_qty,
                    bom_child_cache=bom_child_cache,
                    lineage=(parent_material_code,),
                )
            )
        return expanded_rows

    def _build_schedule_material_usage_map(
        self,
        order_map: dict[str, dict[str, Any]],
        *,
        material_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        source_rows = material_rows if material_rows is not None else self._list_expanded_schedule_material_rows()
        out: dict[str, dict[str, Any]] = {}
        for row in source_rows:
            order_no = str(row.get("production_order_no") or "").strip()
            order_summary = order_map.get(order_no)
            if order_summary is None:
                continue
            consume_ratio = _to_number(order_summary.get("planned_ratio"), 0)
            if consume_ratio <= 0:
                continue
            material_code = str(row.get("child_material_code") or "").strip().upper()
            if not material_code:
                continue
            supply_type_code = str(row.get("supply_type_code") or "").strip().upper()
            if supply_type_code == "SELF_MADE":
                continue
            current = out.get(material_code)
            if current is None:
                current = {
                    "material_code": material_code,
                    "material_name": str(row.get("child_material_name") or material_code).strip() or material_code,
                    "supply_type_code": supply_type_code,
                    "supply_type_name": str(row.get("supply_type_name") or "-").strip() or "-",
                    "inventory_qty": _to_number(row.get("inventory_qty"), 0),
                    "planned_consume_qty": 0.0,
                    "order_nos": set(),
                }
                out[material_code] = current
            current["inventory_qty"] = max(current["inventory_qty"], _to_number(row.get("inventory_qty"), 0))
            current["planned_consume_qty"] += _to_number(row.get("issue_qty"), 0) * consume_ratio
            current["order_nos"].add(order_no)
        for current in out.values():
            current["estimated_inventory_qty"] = current["inventory_qty"] - current["planned_consume_qty"]
            current["order_nos"] = sorted(current["order_nos"])
        return out

    def _build_schedule_shortage_analysis(self, version_no: str | None) -> dict[str, Any]:
        if not version_no:
            return {
                "summary": {
                    "shortage_material_count": 0,
                    "impacted_order_count": 0,
                },
                "items": [],
                "order_map": {},
            }

        task_rows = self._list_schedule_task_detail_rows(version_no)
        if len(task_rows) == 0:
            return {
                "summary": {
                    "shortage_material_count": 0,
                    "impacted_order_count": 0,
                },
                "items": [],
                "order_map": {},
            }

        current_orders = self._build_schedule_order_summary_map(task_rows)
        first_task_by_order: dict[str, dict[str, Any]] = {}
        for row in task_rows:
            order_no = str(row.get("production_order_no") or "").strip()
            if order_no and order_no not in first_task_by_order:
                first_task_by_order[order_no] = row

        material_map = self._build_schedule_material_usage_map(
            current_orders,
            material_rows=self._list_expanded_schedule_material_rows(),
        )
        impacted_order_nos: set[str] = set()
        items: list[dict[str, Any]] = []
        order_map: dict[str, dict[str, Any]] = {}

        def impacted_order_sort_key(item: dict[str, Any]) -> tuple[str, str]:
            start_date = str(item.get("shortage_start_date") or "").strip()
            return (start_date or "9999-12-31", str(item.get("order_no") or "").strip())

        for material_code in sorted(material_map):
            current = material_map[material_code]
            estimated_inventory_qty = _to_number(current.get("estimated_inventory_qty"), 0)
            if estimated_inventory_qty >= 0:
                continue
            order_nos = sorted(
                {
                    str(order_no).strip()
                    for order_no in current.get("order_nos", [])
                    if str(order_no).strip()
                }
            )
            impacted_order_nos.update(order_nos)
            impacted_orders: list[dict[str, Any]] = []
            for order_no in order_nos:
                order_summary = current_orders.get(order_no) or {}
                first_task = first_task_by_order.get(order_no) or {}
                impacted_order = {
                    "order_no": order_no,
                    "shortage_start_date": _normalize_date_text(order_summary.get("start_date")),
                    "first_impacted_process_code": str(
                        first_task.get("process_code") or ""
                    ).strip().upper()
                    or None,
                    "first_impacted_process_name_cn": str(
                        first_task.get("process_name_cn")
                        or first_task.get("process_code")
                        or ""
                    ).strip()
                    or None,
                }
                impacted_orders.append(impacted_order)

                current_order_summary = order_map.get(order_no)
                if current_order_summary is None:
                    current_order_summary = {
                        "shortage_material_count": 0,
                        "items": [],
                    }
                    order_map[order_no] = current_order_summary
                current_order_summary["items"].append(
                    {
                        "material_code": material_code,
                        "material_name": str(current.get("material_name") or material_code).strip()
                        or material_code,
                        "shortage_qty": abs(estimated_inventory_qty),
                        **impacted_order,
                    }
                )

            impacted_orders.sort(key=impacted_order_sort_key)
            first_impacted_order = impacted_orders[0] if impacted_orders else {}
            items.append(
                {
                    "material_code": material_code,
                    "material_name": current.get("material_name"),
                    "supply_type_name": current.get("supply_type_name"),
                    "inventory_qty": _to_number(current.get("inventory_qty"), 0),
                    "planned_consume_qty": _to_number(current.get("planned_consume_qty"), 0),
                    "estimated_inventory_qty": estimated_inventory_qty,
                    "shortage_qty": abs(estimated_inventory_qty),
                    "order_nos": order_nos,
                    "impacted_orders": impacted_orders,
                    "first_impacted_order_no": first_impacted_order.get("order_no"),
                    "shortage_start_date": first_impacted_order.get("shortage_start_date"),
                    "first_impacted_process_code": first_impacted_order.get("first_impacted_process_code"),
                    "first_impacted_process_name_cn": first_impacted_order.get(
                        "first_impacted_process_name_cn"
                    ),
                }
            )

        items.sort(
            key=lambda item: (
                -_to_number(item.get("shortage_qty"), 0),
                str(item.get("material_code") or ""),
            )
        )

        for order_summary in order_map.values():
            material_items = (
                order_summary.get("items")
                if isinstance(order_summary.get("items"), list)
                else []
            )
            material_items.sort(
                key=lambda item: (
                    str(item.get("shortage_start_date") or "").strip() or "9999-12-31",
                    -_to_number(item.get("shortage_qty"), 0),
                    str(item.get("material_code") or ""),
                )
            )
            first_item = material_items[0] if material_items else {}
            order_summary["shortage_material_count"] = len(material_items)
            order_summary["first_material_code"] = first_item.get("material_code")
            order_summary["first_material_name"] = first_item.get("material_name")
            order_summary["shortage_start_date"] = first_item.get("shortage_start_date")
            order_summary["first_impacted_process_code"] = first_item.get("first_impacted_process_code")
            order_summary["first_impacted_process_name_cn"] = first_item.get(
                "first_impacted_process_name_cn"
            )
            if material_items:
                first_material_name = str(
                    first_item.get("material_name") or first_item.get("material_code") or "鐗╂枡"
                ).strip() or "鐗╂枡"
                if len(material_items) == 1:
                    order_summary["summary_text"] = first_material_name
                else:
                    order_summary["summary_text"] = (
                        f"{first_material_name} 等 {len(material_items)} 项"
                    )
            else:
                order_summary["summary_text"] = ""

        return {
            "summary": {
                "shortage_material_count": len(items),
                "impacted_order_count": len(impacted_order_nos),
            },
            "items": items,
            "order_map": order_map,
        }

    def _build_schedule_material_changes(
        self,
        *,
        current_orders: dict[str, dict[str, Any]],
        compare_orders: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        material_rows = self._list_expanded_schedule_material_rows()
        current_map = self._build_schedule_material_usage_map(
            current_orders,
            material_rows=material_rows,
        )
        compare_map = self._build_schedule_material_usage_map(
            compare_orders,
            material_rows=material_rows,
        )
        items: list[dict[str, Any]] = []
        for material_code in sorted(set(current_map) | set(compare_map)):
            current = current_map.get(material_code)
            compare = compare_map.get(material_code)
            selected_inventory = _to_number(current.get("inventory_qty"), 0) if current else _to_number(compare.get("inventory_qty"), 0)
            compare_inventory = _to_number(compare.get("inventory_qty"), 0) if compare else selected_inventory
            selected_estimated = _to_number(current.get("estimated_inventory_qty"), selected_inventory) if current else selected_inventory
            compare_estimated = _to_number(compare.get("estimated_inventory_qty"), compare_inventory) if compare else compare_inventory
            selected_consume = _to_number(current.get("planned_consume_qty"), 0) if current else 0
            compare_consume = _to_number(compare.get("planned_consume_qty"), 0) if compare else 0
            if (
                abs(selected_consume - compare_consume) < SCHEDULE_NUMBER_EPSILON
                and abs(selected_estimated - compare_estimated) < SCHEDULE_NUMBER_EPSILON
            ):
                continue
            risk_change = "UNCHANGED"
            if compare_estimated >= 0 > selected_estimated:
                risk_change = "NEW_SHORTAGE"
            elif compare_estimated < 0 and selected_estimated < compare_estimated:
                risk_change = "SHORTAGE_WORSE"
            elif compare_estimated < 0 <= selected_estimated:
                risk_change = "SHORTAGE_RESOLVED"
            elif selected_estimated > compare_estimated:
                risk_change = "PRESSURE_RELIEVED"
            elif selected_estimated < compare_estimated:
                risk_change = "PRESSURE_INCREASED"
            items.append(
                {
                    "material_code": material_code,
                    "material_name": (current or compare or {}).get("material_name"),
                    "supply_type_name": (current or compare or {}).get("supply_type_name"),
                    "selected_inventory_qty": selected_inventory,
                    "compare_inventory_qty": compare_inventory,
                    "selected_planned_consume_qty": selected_consume,
                    "compare_planned_consume_qty": compare_consume,
                    "selected_estimated_inventory_qty": selected_estimated,
                    "compare_estimated_inventory_qty": compare_estimated,
                    "risk_change": risk_change,
                    "selected_order_nos": current.get("order_nos", []) if current else [],
                    "compare_order_nos": compare.get("order_nos", []) if compare else [],
                }
            )
        items.sort(
            key=lambda item: (
                0 if item["risk_change"] in {"NEW_SHORTAGE", "SHORTAGE_WORSE"} else 1,
                _to_number(item["selected_estimated_inventory_qty"], 0),
                str(item["material_code"]),
            )
        )
        return {"items": items}

    def get_masterdata_config(self) -> dict[str, Any]:
        return self.masterdata_query_service.get_masterdata_config()

    def save_masterdata_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.masterdata_command_service.save_masterdata_config(payload)

    def list_process_routes(self) -> dict[str, Any]:
        return self.masterdata_query_service.list_process_routes()

    def create_process_routes(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.masterdata_command_service.create_process_routes(payload)

    def update_process_routes(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.masterdata_command_service.update_process_routes(payload)

    def copy_process_routes(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.masterdata_command_service.copy_process_routes(payload)

    def delete_process_routes(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.masterdata_command_service.delete_process_routes(payload)

    def get_schedule_calendar_rules(self) -> dict[str, Any]:
        return self.masterdata_query_service.get_schedule_calendar_rules()

    def save_schedule_calendar_rules(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.masterdata_command_service.save_schedule_calendar_rules(payload)

    def generate_schedule(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.factory.build_inventory_refresh_service().refresh_inventory([])
        self._ensure_masterdata_seeded()
        strategy_code = self._normalize_strategy_code(payload.get("strategy_code"))
        capacity_source_mode = self._normalize_capacity_source_mode(
            payload.get("capacity_source_mode")
        )
        use_order_state_window = self._normalize_use_order_state_window(
            payload.get("use_order_state_window")
        )
        planning_rules = self._build_planning_rules_from_current_config()
        version_no = CURRENT_SCHEDULE_VERSION_NO
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
        capacity_resolver = self._build_schedule_capacity_resolver(
            capacity_source_mode=capacity_source_mode
        )

        schedule_candidates: list[dict[str, Any]] = []
        day_mode_cache: dict[str, str] = {}
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

            lock_flag = int(_to_number(state_row.get("lock_flag"), 0))
            frozen_flag = int(_to_number(state_row.get("frozen_flag"), 0))

            process_contexts = self._build_schedule_process_contexts(
                order_no=order_no,
                product_code=str(order_row["material_code"]),
                capacity_rows=capacity_map.get(order_no, []),
                route_rows=route_rows_by_product.get(str(order_row["material_code"]), []),
                topology_by_process=topology_by_process,
                capacity_resolver=capacity_resolver,
            )

            if use_order_state_window:
                start_date_source = (
                    state_row.get("expected_start_date")
                    or order_row.get("planned_start_date")
                    or simulation_start.isoformat()
                )
                due_date_source = (
                    state_row.get("promised_due_date")
                    or order_row.get("planned_end_date")
                    or start_date_source
                )
            else:
                start_date_source = (
                    order_row.get("planned_start_date") or simulation_start.isoformat()
                )
                due_date_source = order_row.get("planned_end_date") or start_date_source
            start_date = _parse_date_or_today(start_date_source)
            due_date = _parse_date_or_today(due_date_source)

            priority_level = _normalize_priority_level(state_row.get("priority_level"), PRIORITY_LEVEL_MAX)
            expected_start_shift = _expected_start_shift_from_datetime_text(
                state_row.get("expected_start_time")
            )
            start_slot = max(
                _slot_index_for(start_date, expected_start_shift),
                _slot_index_for(simulation_start, "DAY"),
            )
            effective_start_date, effective_start_shift = _slot_to_date_shift(start_slot)

            required_shifts = 0
            min_capacity = None
            total_capacity = 0.0
            for context in process_contexts:
                capacity_per_shift = self._resolve_effective_capacity_per_shift(
                    process_context=context,
                    calendar_date=effective_start_date.isoformat(),
                    shift_code=effective_start_shift,
                    capacity_resolver=capacity_resolver,
                )
                required_shifts += self._estimate_required_shifts_for_process(
                    process_context=context,
                    required_qty=remaining_qty_value,
                    start_slot=start_slot,
                    planning_rules=planning_rules,
                    day_mode_cache=day_mode_cache,
                    capacity_resolver=capacity_resolver,
                )
                min_capacity = (
                    capacity_per_shift
                    if min_capacity is None
                    else min(min_capacity, capacity_per_shift)
                )
                total_capacity += capacity_per_shift
            slack_days = (due_date - effective_start_date).days - required_shifts

            schedule_candidates.append(
                {
                    "order_no": order_no,
                    "product_code": str(order_row["material_code"]),
                    "remaining_qty": remaining_qty_value,
                    "start_date": effective_start_date,
                    "due_date": due_date,
                    "start_slot": start_slot,
                    "priority_level": priority_level,
                    "lock_flag": lock_flag,
                    "frozen_flag": frozen_flag,
                    "updated_at": str(order_row.get("updated_at") or ""),
                    "process_contexts": process_contexts,
                    "required_shifts": required_shifts,
                    "slack_days": slack_days,
                    "min_capacity_per_shift": _to_number(min_capacity, 0),
                    "total_capacity_per_shift": total_capacity,
                }
            )

        pending_candidates = self._sort_schedule_candidates(
            strategy_code=strategy_code,
            candidates=schedule_candidates,
        )

        tasks: list[tuple[Any, ...]] = []
        used_capacity_by_slot: dict[tuple[Any, ...], float] = {}
        task_no = 1

        while pending_candidates:
            selected_index = self._select_next_candidate_index(
                strategy_code=strategy_code,
                candidates=pending_candidates,
                planning_rules=planning_rules,
                day_mode_cache=day_mode_cache,
                used_capacity_by_slot=used_capacity_by_slot,
                capacity_resolver=capacity_resolver,
            )
            candidate = pending_candidates.pop(selected_index)
            order_no = str(candidate["order_no"])
            next_start_slot = int(candidate["start_slot"])
            for context in candidate["process_contexts"]:
                context_start_slot = next_start_slot
                process_code = str(context["process_code"])

                allocations, last_slot = self._allocate_process_tasks(
                    order_no=order_no,
                    process_context=context,
                    required_qty=_to_number(candidate["remaining_qty"], 0),
                    first_slot=context_start_slot,
                    planning_rules=planning_rules,
                    day_mode_cache=day_mode_cache,
                    used_capacity_by_slot=used_capacity_by_slot,
                    capacity_resolver=capacity_resolver,
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
                            allocation.get("workshop_code"),
                            allocation.get("line_code"),
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

        order_summary_map = self._build_schedule_order_summary_map_from_generated_tasks(
            tasks=tasks,
            order_rows=order_rows,
        )
        shortage_result = self._build_generated_schedule_material_shortages(
            order_summary_map=order_summary_map,
        )
        if False and shortage_result["items"]:
            preview = ", ".join(
                f"{item['material_code']}(-{round(_to_number(item.get('shortage_qty'), 0), 4)})"
                for item in shortage_result["items"][:3]
            )
            raise bad_request(
                code="SCHEDULE_MATERIAL_SHORTAGE_BLOCKED",
                message=(
                    f"鎺掍骇澶辫触锛氬瓨鍦?{shortage_result['summary']['shortage_material_count']} 椤圭己鏂欙紝"
                    f"影响 {shortage_result['summary']['impacted_order_count']} 张订单。"
                    f"{' 缺料示例：' + preview if preview else ''}"
                ),
                details=shortage_result,
            )

        result_status = "RISKY" if shortage_result["items"] else "FEASIBLE"
        result_summary = (
            f"瀛樺湪 {shortage_result['summary']['shortage_material_count']} 椤圭墿鏂欑煭缂洪闄╋紝"
            f"影响 {shortage_result['summary']['impacted_order_count']} 张订单。"
            if shortage_result["items"]
            else "已生成班次级建议计划。"
        )
        created_at = utc_now()
        self._replace_current_schedule(
            strategy_code=strategy_code,
            result_status=result_status,
            result_summary=result_summary,
            tasks=tasks,
            order_rows=order_rows,
            states=states,
            created_at=created_at,
        )
        return {
            "schedule_id": CURRENT_SCHEDULE_VERSION_NO,
            "version_no": CURRENT_SCHEDULE_VERSION_NO,
            "auto_saved_version_no": None,
            "capacity_source_mode": capacity_source_mode,
            "result_status": result_status,
            "result_status_label": _schedule_result_status_label(result_status),
            "result_summary": result_summary,
            "material_shortages": shortage_result,
        }

    def generate_schedule_by_fact(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.factory.build_inventory_refresh_service().refresh_inventory([])
        self._ensure_masterdata_seeded()
        strategy_code = self._normalize_strategy_code(payload.get("strategy_code"))
        capacity_source_mode = self._normalize_fact_replan_capacity_source_mode(
            payload.get("capacity_source_mode")
        )
        use_order_state_window = self._normalize_use_order_state_window(
            payload.get("use_order_state_window")
        )
        planning_rules = self._build_planning_rules_from_current_config()
        current_version_no = self._pick_current_schedule_version_no()
        version_no = CURRENT_SCHEDULE_VERSION_NO
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
        capacity_resolver = self._build_schedule_capacity_resolver(
            capacity_source_mode=capacity_source_mode
        )
        simulation_state = self._get_simulation_state()
        simulation_start = _parse_date_or_today(simulation_state.get("current_date"))
        fact_boundary = self._build_fact_replan_boundary(simulation_start=simulation_start)

        schedule_candidates: list[dict[str, Any]] = []
        day_mode_cache: dict[str, str] = {}
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

            lock_flag = int(_to_number(state_row.get("lock_flag"), 0))
            frozen_flag = int(_to_number(state_row.get("frozen_flag"), 0))

            process_contexts = self._build_schedule_process_contexts(
                order_no=order_no,
                product_code=str(order_row["material_code"]),
                capacity_rows=capacity_map.get(order_no, []),
                route_rows=route_rows_by_product.get(str(order_row["material_code"]), []),
                topology_by_process=topology_by_process,
                capacity_resolver=capacity_resolver,
            )

            if use_order_state_window:
                start_date_source = (
                    state_row.get("expected_start_date")
                    or order_row.get("planned_start_date")
                    or simulation_start.isoformat()
                )
                due_date_source = (
                    state_row.get("promised_due_date")
                    or order_row.get("planned_end_date")
                    or start_date_source
                )
            else:
                start_date_source = (
                    order_row.get("planned_start_date") or simulation_start.isoformat()
                )
                due_date_source = order_row.get("planned_end_date") or start_date_source
            start_date = _parse_date_or_today(start_date_source)
            due_date = _parse_date_or_today(due_date_source)

            priority_level = _normalize_priority_level(
                state_row.get("priority_level"),
                PRIORITY_LEVEL_MAX,
            )
            expected_start_shift = _expected_start_shift_from_datetime_text(
                state_row.get("expected_start_time")
            )
            start_slot = max(
                _slot_index_for(start_date, expected_start_shift),
                int(fact_boundary["next_slot"]),
            )
            effective_start_date, effective_start_shift = _slot_to_date_shift(start_slot)

            required_shifts = 0
            min_capacity = None
            total_capacity = 0.0
            for context in process_contexts:
                capacity_per_shift = self._resolve_effective_capacity_per_shift(
                    process_context=context,
                    calendar_date=effective_start_date.isoformat(),
                    shift_code=effective_start_shift,
                    capacity_resolver=capacity_resolver,
                )
                required_shifts += self._estimate_required_shifts_for_process(
                    process_context=context,
                    required_qty=remaining_qty_value,
                    start_slot=start_slot,
                    planning_rules=planning_rules,
                    day_mode_cache=day_mode_cache,
                    capacity_resolver=capacity_resolver,
                )
                min_capacity = (
                    capacity_per_shift
                    if min_capacity is None
                    else min(min_capacity, capacity_per_shift)
                )
                total_capacity += capacity_per_shift
            slack_days = (due_date - effective_start_date).days - required_shifts

            schedule_candidates.append(
                {
                    "order_no": order_no,
                    "product_code": str(order_row["material_code"]),
                    "remaining_qty": remaining_qty_value,
                    "start_date": effective_start_date,
                    "due_date": due_date,
                    "start_slot": start_slot,
                    "priority_level": priority_level,
                    "lock_flag": lock_flag,
                    "frozen_flag": frozen_flag,
                    "updated_at": str(order_row.get("updated_at") or ""),
                    "process_contexts": process_contexts,
                    "required_shifts": required_shifts,
                    "slack_days": slack_days,
                    "min_capacity_per_shift": _to_number(min_capacity, 0),
                    "total_capacity_per_shift": total_capacity,
                }
            )

        pending_candidates = self._sort_schedule_candidates(
            strategy_code=strategy_code,
            candidates=schedule_candidates,
        )

        tasks = self._build_fact_locked_task_rows(
            current_version_no=current_version_no,
            version_no=version_no,
            reported_slot=fact_boundary.get("reported_slot"),
        )
        used_capacity_by_slot: dict[tuple[Any, ...], float] = {}
        for task in tasks:
            workshop_code = str(task[5] or "").strip().upper()
            line_code = str(task[6] or "").strip().upper()
            process_code = str(task[3] or "").strip().upper()
            calendar_date = _normalize_date_text(task[7])
            if not workshop_code or not line_code or not process_code or not calendar_date:
                continue
            shift_code = _normalize_shift_code(task[8])
            slot_index = _slot_index_from_text(calendar_date, shift_code)
            key = self._capacity_usage_key(
                process_context={
                    "company_code": DEFAULT_COMPANY_CODE,
                    "workshop_code": workshop_code,
                    "line_code": line_code,
                    "process_code": process_code,
                },
                slot_index=slot_index,
                calendar_date=calendar_date,
                shift_code=shift_code,
                capacity_resolver=capacity_resolver,
            )
            used_capacity_by_slot[key] = (
                _to_number(used_capacity_by_slot.get(key), 0) + _to_number(task[9], 0)
            )

        task_no = len(tasks) + 1
        while pending_candidates:
            selected_index = self._select_next_candidate_index(
                strategy_code=strategy_code,
                candidates=pending_candidates,
                planning_rules=planning_rules,
                day_mode_cache=day_mode_cache,
                used_capacity_by_slot=used_capacity_by_slot,
                capacity_resolver=capacity_resolver,
            )
            candidate = pending_candidates.pop(selected_index)
            order_no = str(candidate["order_no"])
            next_start_slot = int(candidate["start_slot"])
            for context in candidate["process_contexts"]:
                allocations, last_slot = self._allocate_process_tasks(
                    order_no=order_no,
                    process_context=context,
                    required_qty=_to_number(candidate["remaining_qty"], 0),
                    first_slot=next_start_slot,
                    planning_rules=planning_rules,
                    day_mode_cache=day_mode_cache,
                    used_capacity_by_slot=used_capacity_by_slot,
                    capacity_resolver=capacity_resolver,
                )
                process_code = str(context["process_code"])
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
                            allocation.get("workshop_code"),
                            allocation.get("line_code"),
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

        order_summary_map = self._build_schedule_order_summary_map_from_generated_tasks(
            tasks=tasks,
            order_rows=order_rows,
        )
        shortage_result = self._build_generated_schedule_material_shortages(
            order_summary_map=order_summary_map,
        )
        result_status = "RISKY" if shortage_result["items"] else "FEASIBLE"
        result_summary = (
            f"鐎涙ê婀?{shortage_result['summary']['shortage_material_count']} 妞ゅ湱澧块弬娆戠叚缂傛椽顥撻梽鈺嬬礉"
            f"瑜板崬鎼?{shortage_result['summary']['impacted_order_count']} 瀵姾顓归崡鏇樷偓?"
            if shortage_result["items"]
            else "瀹稿弶瀵滄禍瀣杽鏉堝湱鏅悽鐔稿灇閸氬海鐢婚悵顓燁偧閹烘帊楠囬妴?"
        )
        created_at = utc_now()
        self._replace_current_schedule(
            strategy_code=strategy_code,
            result_status=result_status,
            result_summary=result_summary,
            tasks=tasks,
            order_rows=order_rows,
            states=states,
            created_at=created_at,
        )
        return {
            "schedule_id": CURRENT_SCHEDULE_VERSION_NO,
            "version_no": CURRENT_SCHEDULE_VERSION_NO,
            "auto_saved_version_no": None,
            "capacity_source_mode": capacity_source_mode,
            "result_status": result_status,
            "result_status_label": _schedule_result_status_label(result_status),
            "result_summary": result_summary,
            "material_shortages": shortage_result,
        }

    def create_dispatch_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.dispatch_command_service.create_dispatch_command(payload)

    def approve_dispatch_command(
        self,
        command_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.dispatch_command_service.approve_dispatch_command(command_id, payload)

    def batch_dispatch_commands(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.dispatch_command_service.batch_dispatch_commands(payload)

    def advance_simulation_one_day(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._get_simulation_state()
        current_date = _normalize_date_text(current.get("current_date"))
        client_date = _normalize_date_text(payload.get("client_date"))
        baseline_candidates = [
            candidate
            for candidate in (current_date, client_date, _today_text())
            if candidate is not None
        ]
        baseline_date = (
            max(date.fromisoformat(candidate) for candidate in baseline_candidates).isoformat()
            if baseline_candidates
            else None
        )
        if baseline_date is None:
            raise server_error(
                code="SIMULATION_CURRENT_DATE_INVALID",
                message="Current simulation date is invalid.",
                details={"current_date": current.get("current_date")},
            )
        next_date = (date.fromisoformat(baseline_date) + timedelta(days=1)).isoformat()
        with transaction(self.connection):
            if current_date is None or date.fromisoformat(current_date) < date.fromisoformat(baseline_date):
                self._clear_simulation_restore_snapshot()
            snapshot_created = self._ensure_simulation_restore_snapshot(
                baseline_date=baseline_date
            )
            seeded_capacity_count = self._seed_simulated_morning_capacity(
                baseline_date
            )
            reporting_stats = self._simulate_same_day_reportings(baseline_date)
            rebuilt_actual_row_count, skipped_rebuild_report_count = (
                self._rebuild_line_daily_actual_capacity_rows(baseline_date)
            )
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
            "simulated_date": baseline_date,
            "snapshot_created": snapshot_created,
            "seeded_morning_capacity_count": seeded_capacity_count,
            "simulated_reporting_count": reporting_stats["inserted_report_count"],
            "skipped_existing_reporting_count": reporting_stats[
                "skipped_existing_report_count"
            ],
            "skipped_zero_capacity_reporting_count": reporting_stats[
                "skipped_zero_capacity_report_count"
            ],
            "rebuild_actual_row_count": rebuilt_actual_row_count,
            "rebuild_skipped_report_count": skipped_rebuild_report_count,
        }

    def reset_manual_simulation(self) -> dict[str, Any]:
        snapshot = fetch_one(
            self.connection,
            """
            SELECT snapshot_current_date
            FROM simulation_restore_snapshot_meta
            WHERE singleton_key = ?
            """,
            (RULES_SINGLETON_KEY,),
        )
        if snapshot is None:
            raise bad_request(
                code="SIMULATION_SNAPSHOT_NOT_FOUND",
                message=(
                    "No simulation snapshot is available to restore. "
                    "Advance simulation first."
                ),
            )
        restored_date = _normalize_date_text(snapshot.get("snapshot_current_date"))
        if restored_date is None:
            raise server_error(
                code="SIMULATION_SNAPSHOT_DATE_INVALID",
                message="Snapshot simulation date is invalid.",
                details={"snapshot_current_date": snapshot.get("snapshot_current_date")},
            )
        restored_plan_count = int(
            _to_number(
                fetch_one(
                    self.connection,
                    """
                    SELECT COUNT(1) AS total
                    FROM simulation_restore_snapshot_daily_line_capacity_plan
                    """,
                )["total"],
                0,
            )
        )
        restored_actual_count = int(
            _to_number(
                fetch_one(
                    self.connection,
                    """
                    SELECT COUNT(1) AS total
                    FROM simulation_restore_snapshot_daily_line_capacity_actual
                    """,
                )["total"],
                0,
            )
        )
        restored_report_count = int(
            _to_number(
                fetch_one(
                    self.connection,
                    """
                    SELECT COUNT(1) AS total
                    FROM simulation_restore_snapshot_work_reports
                    """,
                )["total"],
                0,
            )
        )
        restored_plan_audit_count = int(
            _to_number(
                fetch_one(
                    self.connection,
                    """
                    SELECT COUNT(1) AS total
                    FROM simulation_restore_snapshot_daily_line_capacity_plan_audit
                    """,
                )["total"],
                0,
            )
        )
        with transaction(self.connection):
            self.connection.execute("DELETE FROM daily_line_capacity_plan_audit")
            self.connection.execute("DELETE FROM daily_line_capacity_actual")
            self.connection.execute("DELETE FROM daily_line_capacity_plan")
            self.connection.execute("DELETE FROM work_reports")
            self.connection.execute(
                """
                INSERT INTO daily_line_capacity_plan_audit (
                    audit_id,
                    calendar_date,
                    shift_code,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    old_planned_capacity_qty,
                    new_planned_capacity_qty,
                    old_worker_count,
                    new_worker_count,
                    old_machine_count,
                    new_machine_count,
                    operator_user_id,
                    operator_username,
                    operator_display_name,
                    changed_at
                )
                SELECT
                    audit_id,
                    calendar_date,
                    shift_code,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    old_planned_capacity_qty,
                    new_planned_capacity_qty,
                    old_worker_count,
                    new_worker_count,
                    old_machine_count,
                    new_machine_count,
                    operator_user_id,
                    operator_username,
                    operator_display_name,
                    changed_at
                FROM simulation_restore_snapshot_daily_line_capacity_plan_audit
                """
            )
            self.connection.execute(
                """
                INSERT INTO daily_line_capacity_plan (
                    calendar_date,
                    shift_code,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    planned_capacity_qty,
                    worker_count,
                    machine_count,
                    source_note,
                    updated_at
                )
                SELECT
                    calendar_date,
                    shift_code,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    planned_capacity_qty,
                    worker_count,
                    machine_count,
                    source_note,
                    updated_at
                FROM simulation_restore_snapshot_daily_line_capacity_plan
                """
            )
            self.connection.execute(
                """
                INSERT INTO daily_line_capacity_actual (
                    calendar_date,
                    shift_code,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    actual_capacity_qty,
                    report_count,
                    last_report_time,
                    updated_at
                )
                SELECT
                    calendar_date,
                    shift_code,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    actual_capacity_qty,
                    report_count,
                    last_report_time,
                    updated_at
                FROM simulation_restore_snapshot_daily_line_capacity_actual
                """
            )
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
                    daily_capacity_compare_audit_id,
                    daily_capacity_compare_qty,
                    daily_capacity_compare_selected_at,
                    updated_at
                )
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
                    operator_name,
                    daily_capacity_compare_audit_id,
                    daily_capacity_compare_qty,
                    daily_capacity_compare_selected_at,
                    updated_at
                FROM simulation_restore_snapshot_work_reports
                """
            )
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
                (RULES_SINGLETON_KEY, restored_date, utc_now()),
            )
            self._clear_simulation_restore_snapshot()
        return {
            "current_date": restored_date,
            "message": "Simulation reset.",
            "restored_plan_count": restored_plan_count,
            "restored_actual_count": restored_actual_count,
            "restored_report_count": restored_report_count,
            "restored_plan_audit_count": restored_plan_audit_count,
        }

    def _ensure_simulation_restore_snapshot(self, *, baseline_date: str) -> bool:
        existing = fetch_one(
            self.connection,
            """
            SELECT singleton_key
            FROM simulation_restore_snapshot_meta
            WHERE singleton_key = ?
            """,
            (RULES_SINGLETON_KEY,),
        )
        if existing is not None:
            return False
        normalized_date = _normalize_date_text(baseline_date)
        if normalized_date is None:
            raise bad_request(
                code="SIMULATION_BASELINE_DATE_INVALID",
                message="baseline_date must be a valid YYYY-MM-DD date.",
                details={"baseline_date": baseline_date},
            )
        self._clear_simulation_restore_snapshot()
        self.connection.execute(
            """
            INSERT INTO simulation_restore_snapshot_meta (
                singleton_key,
                snapshot_current_date,
                snapshot_created_at
            ) VALUES (?, ?, ?)
            """,
            (RULES_SINGLETON_KEY, normalized_date, utc_now()),
        )
        self.connection.execute(
            """
            INSERT INTO simulation_restore_snapshot_daily_line_capacity_plan (
                calendar_date,
                shift_code,
                company_code,
                workshop_code,
                line_code,
                process_code,
                planned_capacity_qty,
                worker_count,
                machine_count,
                source_note,
                updated_at
            )
            SELECT
                calendar_date,
                shift_code,
                company_code,
                workshop_code,
                line_code,
                process_code,
                planned_capacity_qty,
                worker_count,
                machine_count,
                source_note,
                updated_at
            FROM daily_line_capacity_plan
            """
        )
        self.connection.execute(
            """
            INSERT INTO simulation_restore_snapshot_daily_line_capacity_actual (
                calendar_date,
                shift_code,
                company_code,
                workshop_code,
                line_code,
                process_code,
                actual_capacity_qty,
                report_count,
                last_report_time,
                updated_at
            )
            SELECT
                calendar_date,
                shift_code,
                company_code,
                workshop_code,
                line_code,
                process_code,
                actual_capacity_qty,
                report_count,
                last_report_time,
                updated_at
            FROM daily_line_capacity_actual
            """
        )
        self.connection.execute(
            """
            INSERT INTO simulation_restore_snapshot_daily_line_capacity_plan_audit (
                audit_id,
                calendar_date,
                shift_code,
                company_code,
                workshop_code,
                line_code,
                process_code,
                old_planned_capacity_qty,
                new_planned_capacity_qty,
                old_worker_count,
                new_worker_count,
                old_machine_count,
                new_machine_count,
                operator_user_id,
                operator_username,
                operator_display_name,
                changed_at
            )
            SELECT
                audit_id,
                calendar_date,
                shift_code,
                company_code,
                workshop_code,
                line_code,
                process_code,
                old_planned_capacity_qty,
                new_planned_capacity_qty,
                old_worker_count,
                new_worker_count,
                old_machine_count,
                new_machine_count,
                operator_user_id,
                operator_username,
                operator_display_name,
                changed_at
            FROM daily_line_capacity_plan_audit
            """
        )
        self.connection.execute(
            """
            INSERT INTO simulation_restore_snapshot_work_reports (
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
                daily_capacity_compare_audit_id,
                daily_capacity_compare_qty,
                daily_capacity_compare_selected_at,
                updated_at
            )
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
                operator_name,
                daily_capacity_compare_audit_id,
                daily_capacity_compare_qty,
                daily_capacity_compare_selected_at,
                updated_at
            FROM work_reports
            """
        )
        return True

    def _clear_simulation_restore_snapshot(self) -> None:
        self.connection.execute("DELETE FROM simulation_restore_snapshot_daily_line_capacity_plan")
        self.connection.execute("DELETE FROM simulation_restore_snapshot_daily_line_capacity_actual")
        self.connection.execute("DELETE FROM simulation_restore_snapshot_daily_line_capacity_plan_audit")
        self.connection.execute("DELETE FROM simulation_restore_snapshot_work_reports")
        self.connection.execute(
            "DELETE FROM simulation_restore_snapshot_meta WHERE singleton_key = ?",
            (RULES_SINGLETON_KEY,),
        )

    def _seed_simulated_morning_capacity(self, calendar_date: str) -> int:
        normalized_date = _normalize_date_text(calendar_date)
        if normalized_date is None:
            raise bad_request(
                code="CALENDAR_DATE_REQUIRED",
                message="calendar_date must be a valid YYYY-MM-DD date.",
            )
        capacity_data = self.list_line_daily_capacity(normalized_date)
        capacity_items = capacity_data.get("items") if isinstance(capacity_data, dict) else []
        if not isinstance(capacity_items, list) or len(capacity_items) == 0:
            raise server_error(
                code="SIMULATION_CAPACITY_TOPOLOGY_EMPTY",
                message="No line topology rows are available for simulation capacity seeding.",
                details={"calendar_date": normalized_date},
            )
        existing_rows = fetch_all(
            self.connection,
            """
            SELECT company_code, workshop_code, line_code, process_code
            FROM daily_line_capacity_plan
            WHERE calendar_date = ?
            """,
            (normalized_date,),
        )
        existing_keys = {
            (
                str(row.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper()
                or DEFAULT_COMPANY_CODE,
                str(row.get("workshop_code") or "").strip().upper(),
                str(row.get("line_code") or "").strip().upper(),
                str(row.get("process_code") or "").strip().upper(),
                _normalize_shift_code(row.get("shift_code") or "DAY"),
            )
            for row in existing_rows
        }
        rows_to_insert: list[tuple[Any, ...]] = []
        updated_at = utc_now()
        for item in capacity_items:
            company_code = (
                str(item.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper()
                or DEFAULT_COMPANY_CODE
            )
            workshop_code = str(item.get("workshop_code") or "").strip().upper()
            line_code = str(item.get("line_code") or "").strip().upper()
            process_code = str(item.get("process_code") or "").strip().upper()
            if not workshop_code or not line_code or not process_code:
                raise server_error(
                    code="SIMULATION_CAPACITY_KEY_INVALID",
                    message="Simulation capacity row key is invalid.",
                    details={
                        "calendar_date": normalized_date,
                        "workshop_code": workshop_code,
                        "line_code": line_code,
                        "process_code": process_code,
                    },
                )
            shift_code = _normalize_shift_code(item.get("shift_code") or "DAY")
            key = (company_code, workshop_code, line_code, process_code, shift_code)
            if key in existing_keys:
                continue
            rows_to_insert.append(
                (
                    normalized_date,
                    shift_code,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    _to_number(item.get("planned_capacity_qty"), 0),
                    int(_to_number(item.get("worker_count"), 0)),
                    int(_to_number(item.get("machine_count"), 0)),
                    "SIMULATION_AUTO_MORNING_ESTIMATE",
                    updated_at,
                )
            )
        if rows_to_insert:
            self.connection.executemany(
                """
                INSERT INTO daily_line_capacity_plan (
                    calendar_date,
                    shift_code,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    planned_capacity_qty,
                    worker_count,
                    machine_count,
                    source_note,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )
        return len(rows_to_insert)

    def _simulate_same_day_reportings(self, calendar_date: str) -> dict[str, int]:
        normalized_date = _normalize_date_text(calendar_date)
        if normalized_date is None:
            raise bad_request(
                code="CALENDAR_DATE_REQUIRED",
                message="calendar_date must be a valid YYYY-MM-DD date.",
            )
        plan_rows = fetch_all(
            self.connection,
            """
            SELECT
                plan.company_code,
                plan.workshop_code,
                COALESCE(top.workshop_name, plan.workshop_code) AS workshop_name,
                plan.line_code,
                COALESCE(top.line_name, plan.line_code) AS line_name,
                plan.process_code,
                plan.planned_capacity_qty
            FROM daily_line_capacity_plan plan
            LEFT JOIN masterdata_line_topology top
              ON top.company_code = plan.company_code
             AND top.workshop_code = plan.workshop_code
             AND top.line_code = plan.line_code
             AND top.process_code = plan.process_code
            WHERE plan.calendar_date = ?
            ORDER BY
                plan.workshop_code ASC,
                plan.line_code ASC,
                plan.process_code ASC
            """,
            (normalized_date,),
        )
        if len(plan_rows) == 0:
            raise server_error(
                code="SIMULATION_CAPACITY_PLAN_EMPTY",
                message=(
                    "No daily line capacity plan rows exist for the simulation date. "
                    "Simulation reporting cannot be generated."
                ),
                details={"calendar_date": normalized_date},
            )
        existing_reporting_rows = fetch_all(
            self.connection,
            """
            SELECT DISTINCT
                UPPER(TRIM(COALESCE(workshop_code, ''))) AS workshop_code,
                UPPER(TRIM(COALESCE(line_code, ''))) AS line_code,
                UPPER(TRIM(COALESCE(process_code, ''))) AS process_code
            FROM work_reports
            WHERE date(report_time, '+8 hours') = ?
            """,
            (normalized_date,),
        )
        existing_report_keys = {
            (
                str(row.get("workshop_code") or "").strip().upper(),
                str(row.get("line_code") or "").strip().upper(),
                str(row.get("process_code") or "").strip().upper(),
            )
            for row in existing_reporting_rows
        }
        process_name_by_code = self._process_name_by_code()
        report_base_time = (
            datetime.fromisoformat(f"{normalized_date}T10:00:00+08:00")
            .astimezone(timezone.utc)
            .replace(microsecond=0)
        )
        rows_to_insert: list[tuple[Any, ...]] = []
        skipped_existing_report_count = 0
        skipped_zero_capacity_report_count = 0
        for index, row in enumerate(plan_rows):
            company_code = (
                str(row.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper()
                or DEFAULT_COMPANY_CODE
            )
            workshop_code = str(row.get("workshop_code") or "").strip().upper()
            line_code = str(row.get("line_code") or "").strip().upper()
            process_code = str(row.get("process_code") or "").strip().upper()
            if not workshop_code or not line_code or not process_code:
                raise server_error(
                    code="SIMULATION_REPORTING_KEY_INVALID",
                    message="Simulation reporting row key is invalid.",
                    details={
                        "calendar_date": normalized_date,
                        "workshop_code": workshop_code,
                        "line_code": line_code,
                        "process_code": process_code,
                    },
                )
            if (workshop_code, line_code, process_code) in existing_report_keys:
                skipped_existing_report_count += 1
                continue
            planned_capacity_qty = _to_number(row.get("planned_capacity_qty"), 0)
            if planned_capacity_qty <= SCHEDULE_NUMBER_EPSILON:
                skipped_zero_capacity_report_count += 1
                continue
            ratio = self._simulation_reporting_ratio(
                calendar_date=normalized_date,
                company_code=company_code,
                workshop_code=workshop_code,
                line_code=line_code,
                process_code=process_code,
            )
            report_qty = round(planned_capacity_qty * ratio)
            if report_qty <= SCHEDULE_NUMBER_EPSILON:
                skipped_zero_capacity_report_count += 1
                continue
            report_time = (report_base_time + timedelta(minutes=index)).isoformat()
            rows_to_insert.append(
                (
                    f"RPT-SIM-{uuid4().hex[:10].upper()}",
                    None,
                    process_code,
                    process_name_by_code.get(process_code, process_code),
                    workshop_code,
                    str(row.get("workshop_name") or workshop_code).strip() or workshop_code,
                    line_code,
                    str(row.get("line_name") or line_code).strip() or line_code,
                    float(report_qty),
                    report_time,
                    "simulation-auto",
                    report_time,
                )
            )
        if rows_to_insert:
            self.connection.executemany(
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
                rows_to_insert,
            )
        return {
            "inserted_report_count": len(rows_to_insert),
            "skipped_existing_report_count": skipped_existing_report_count,
            "skipped_zero_capacity_report_count": skipped_zero_capacity_report_count,
        }

    def _simulation_reporting_ratio(
        self,
        *,
        calendar_date: str,
        company_code: str,
        workshop_code: str,
        line_code: str,
        process_code: str,
    ) -> float:
        seed_text = (
            f"{calendar_date}|{company_code}|{workshop_code}|{line_code}|{process_code}"
        )
        weighted_sum = sum((index + 1) * ord(ch) for index, ch in enumerate(seed_text))
        bucket = weighted_sum % 31
        return 0.65 + (bucket / 100.0)

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
        product_name = "瀵间笣淇濇姢缁勪欢" if random_guidewire else material_code
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
                        "priority_level": PRIORITY_LEVEL_MAX,
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
                        "priority_level": PRIORITY_LEVEL_MAX,
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

    def _get_order_rows_by_nos(self, order_nos: list[str]) -> dict[str, dict[str, Any]]:
        if len(order_nos) == 0:
            return {}
        placeholders = ",".join("?" for _ in order_nos)
        rows = fetch_all(
            self.connection,
            f"""
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
            WHERE production_order_no IN ({placeholders})
            """,
            tuple(order_nos),
        )
        return {str(row["production_order_no"]): row for row in rows}

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
                priority_level,
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
                priority_level,
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
                priority_level,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(production_order_no) DO UPDATE SET
                promised_due_date = excluded.promised_due_date,
                expected_start_date = excluded.expected_start_date,
                expected_start_time = excluded.expected_start_time,
                expected_finish_time = excluded.expected_finish_time,
                priority_level = excluded.priority_level,
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
                _normalize_priority_level(row.get("priority_level"), PRIORITY_LEVEL_MAX),
                _urgent_flag_from_priority_level(row.get("priority_level")),
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

    def _sync_order_pool_state_schedule_window_from_tasks(
        self,
        *,
        tasks: list[tuple[Any, ...]],
        order_rows: list[dict[str, Any]],
        states: dict[str, dict[str, Any]],
    ) -> None:
        windows_by_order_no: dict[str, dict[str, str]] = {}
        for task in tasks:
            if len(task) < 9:
                continue
            order_no = str(task[2] or "").strip()
            calendar_date = _normalize_date_text(task[7])
            if not order_no or not calendar_date:
                continue
            finish_date = date.fromisoformat(calendar_date)
            if _normalize_shift_code(task[8]) == "NIGHT":
                finish_date = finish_date + timedelta(days=1)
            finish_date_text = finish_date.isoformat()
            current = windows_by_order_no.get(order_no)
            if current is None:
                windows_by_order_no[order_no] = {
                    "start_date": calendar_date,
                    "finish_date": finish_date_text,
                }
                continue
            if calendar_date < current["start_date"]:
                current["start_date"] = calendar_date
            if finish_date_text > current["finish_date"]:
                current["finish_date"] = finish_date_text

        if len(windows_by_order_no) == 0:
            return

        order_row_by_no = {
            str(row.get("production_order_no") or "").strip(): row
            for row in order_rows
        }
        for order_no, window in windows_by_order_no.items():
            state_row = states.get(order_no) or {}
            base_row = order_row_by_no.get(order_no) or {}
            status = str(
                state_row.get("status")
                or state_row.get("order_status")
                or base_row.get("status")
                or "OPEN"
            ).strip().upper() or "OPEN"
            order_status = str(
                state_row.get("order_status")
                or state_row.get("status")
                or status
            ).strip().upper() or status
            production_qty = _to_number(base_row.get("production_qty"), 0)
            completed_qty = (
                _to_number(state_row.get("completed_qty"), 0)
                if state_row.get("completed_qty") is not None
                else (production_qty if order_status == "DONE" else 0)
            )
            remaining_qty = (
                _to_number(state_row.get("remaining_qty"), 0)
                if state_row.get("remaining_qty") is not None
                else max(0.0, production_qty - completed_qty)
            )
            progress_rate = (
                _to_number(state_row.get("progress_rate"), 0)
                if state_row.get("progress_rate") is not None
                else ((completed_qty / production_qty * 100) if production_qty > 0 else 0)
            )
            source_bill_no = str(base_row.get("source_bill_no") or "").strip()
            production_batch_no = state_row.get("production_batch_no")
            if production_batch_no is None and source_bill_no:
                production_batch_no = f"{source_bill_no}-B1"

            next_row = {
                "production_order_no": order_no,
                "promised_due_date": state_row.get("promised_due_date") or base_row.get("planned_end_date"),
                "expected_start_date": window["start_date"],
                "expected_start_time": _iso_at(window["start_date"], "08:00:00"),
                "expected_finish_time": _iso_at(window["finish_date"], "18:00:00"),
                "priority_level": _normalize_priority_level(
                    state_row.get("priority_level"),
                    PRIORITY_LEVEL_MAX,
                ),
                "urgent_flag": _urgent_flag_from_priority_level(
                    state_row.get("priority_level")
                ),
                "lock_flag": int(_to_number(state_row.get("lock_flag"), 0)),
                "frozen_flag": int(_to_number(state_row.get("frozen_flag"), 0)),
                "status": status,
                "order_status": order_status,
                "completed_qty": completed_qty,
                "remaining_qty": remaining_qty,
                "progress_rate": progress_rate,
                "production_batch_no": production_batch_no,
            }
            self._upsert_order_state(next_row)

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
        topology_by_process: dict[str, list[dict[str, Any]]],
        reference_version: dict[str, Any] | None,
        schedule_fact: dict[str, Any] | None,
        published_version: dict[str, Any] | None,
        published_schedule_fact: dict[str, Any] | None,
        shortage_summary: dict[str, Any] | None,
        final_process_metrics: dict[str, Any] | None,
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
        promised_due_date = _normalize_date_text(
            (state_row or {}).get("promised_due_date") or base_row.get("planned_end_date")
        )
        base_expected_start_date = _normalize_date_text(base_row.get("planned_start_date"))
        expected_start_date = _normalize_date_text(
            (state_row or {}).get("expected_start_date") or base_expected_start_date
        )
        base_expected_start_time = _iso_at(base_expected_start_date, "08:00:00")
        expected_start_time = (
            (state_row or {}).get("expected_start_time")
            or _iso_at(expected_start_date, "08:00:00")
        )
        base_expected_finish_time = _iso_at(promised_due_date, "18:00:00")
        expected_finish_time = (
            (state_row or {}).get("expected_finish_time")
            or base_expected_finish_time
        )
        manual_expected_start_date = _normalize_date_text((state_row or {}).get("expected_start_date"))
        manual_expected_start_time = str((state_row or {}).get("expected_start_time") or "").strip() or None
        manual_expected_start_shift = _expected_start_shift_from_datetime_text(manual_expected_start_time)
        manual_expected_start_override = (
            manual_expected_start_date is not None
            and (
                manual_expected_start_date != base_expected_start_date
                or (
                    manual_expected_start_time is not None
                    and manual_expected_start_time != base_expected_start_time
                )
            )
        )
        base_status = str(base_row.get("status") or "").strip().upper()
        status = str(
            (state_row or {}).get("status")
            or (state_row or {}).get("order_status")
            or base_row.get("status")
            or "OPEN"
        ).strip().upper()
        order_status = str(
            (state_row or {}).get("order_status") or status
        ).strip().upper()
        erp_status = base_status if base_status and base_status not in LOCAL_ORDER_STATUS_CODES else None
        source_bill_no = str(base_row.get("source_bill_no") or "").strip()
        final_process_code = str(
            (final_process_metrics or {}).get("final_process_code") or ""
        ).strip().upper() or None
        final_process_name_cn = str(
            (final_process_metrics or {}).get("final_process_name_cn")
            or final_process_code
            or ""
        ).strip() or None
        final_process_completed_qty = _to_number(
            (final_process_metrics or {}).get("final_process_completed_qty"),
            0,
        )
        final_process_eta_date = _normalize_date_text(
            (final_process_metrics or {}).get("final_process_eta_date")
        )
        shortage_items = (
            shortage_summary.get("items")
            if isinstance(shortage_summary, dict) and isinstance(shortage_summary.get("items"), list)
            else []
        )
        reference_version_no = str((reference_version or {}).get("version_no") or "").strip() or None
        reference_version_status = str((reference_version or {}).get("status") or "").strip().upper() or None
        scheduled_in_reference_version = schedule_fact is not None
        published_in_reference_version = (
            scheduled_in_reference_version and reference_version_status == "PUBLISHED"
        )
        published_version_no = str((published_version or {}).get("version_no") or "").strip() or None
        published_version_status = str((published_version or {}).get("status") or "").strip().upper() or None
        scheduled_in_published_version = published_schedule_fact is not None
        scheduled_start_date = _normalize_date_text((schedule_fact or {}).get("scheduled_start_date"))
        scheduled_start_time = str((schedule_fact or {}).get("scheduled_start_time") or "").strip() or None
        scheduled_start_shift = str((schedule_fact or {}).get("scheduled_start_shift") or "").strip().upper() or None
        scheduled_finish_date = _normalize_date_text((schedule_fact or {}).get("scheduled_finish_date"))
        scheduled_finish_time = str((schedule_fact or {}).get("scheduled_finish_time") or "").strip() or None
        published_scheduled_start_date = _normalize_date_text((published_schedule_fact or {}).get("scheduled_start_date"))
        published_scheduled_start_time = str((published_schedule_fact or {}).get("scheduled_start_time") or "").strip() or None
        published_scheduled_start_shift = str((published_schedule_fact or {}).get("scheduled_start_shift") or "").strip().upper() or None
        published_scheduled_finish_date = _normalize_date_text((published_schedule_fact or {}).get("scheduled_finish_date"))
        published_scheduled_finish_time = str((published_schedule_fact or {}).get("scheduled_finish_time") or "").strip() or None
        actual_workshop_codes = (
            schedule_fact.get("actual_workshop_codes")
            if isinstance(schedule_fact, dict) and isinstance(schedule_fact.get("actual_workshop_codes"), list)
            else []
        )
        actual_line_codes = (
            schedule_fact.get("actual_line_codes")
            if isinstance(schedule_fact, dict) and isinstance(schedule_fact.get("actual_line_codes"), list)
            else []
        )
        actual_process_codes = (
            schedule_fact.get("actual_process_codes")
            if isinstance(schedule_fact, dict) and isinstance(schedule_fact.get("actual_process_codes"), list)
            else []
        )
        expected_start_due_gap_days = _signed_due_gap_days(
            promised_due_date,
            expected_start_time,
            event_default_clock_text="08:00:00",
        )
        is_naturally_overdue = (
            expected_start_due_gap_days is not None and expected_start_due_gap_days > 0
        )
        order_window_finish_date = _normalize_date_text(expected_finish_time)
        order_window_due_gap_days = _signed_due_gap_days(promised_due_date, expected_finish_time)
        order_window_risk_level = "UNKNOWN"
        if order_window_due_gap_days is not None:
            if order_window_due_gap_days > 0:
                order_window_risk_level = "OVERDUE"
            elif order_window_due_gap_days >= -1:
                order_window_risk_level = "TIGHT"
            else:
                order_window_risk_level = "SAFE"
        final_process_due_gap_days = (
            _signed_due_gap_days(promised_due_date, final_process_eta_date)
            if final_process_eta_date
            else None
        )
        scheduled_due_gap_days = _signed_due_gap_days(promised_due_date, scheduled_finish_time or scheduled_finish_date)
        published_scheduled_due_gap_days = _signed_due_gap_days(
            promised_due_date,
            published_scheduled_finish_time or published_scheduled_finish_date,
        )
        final_process_risk_level = "UNKNOWN"
        if final_process_due_gap_days is not None:
            if final_process_due_gap_days > 0:
                final_process_risk_level = "OVERDUE"
            elif final_process_due_gap_days >= -1:
                final_process_risk_level = "TIGHT"
            else:
                final_process_risk_level = "SAFE"
        scheduled_risk_level = "UNKNOWN"
        if scheduled_due_gap_days is not None:
            if scheduled_due_gap_days > 0:
                scheduled_risk_level = "OVERDUE"
            elif scheduled_due_gap_days >= -1:
                scheduled_risk_level = "TIGHT"
            else:
                scheduled_risk_level = "SAFE"
        published_scheduled_risk_level = "UNKNOWN"
        if published_scheduled_due_gap_days is not None:
            if published_scheduled_due_gap_days > 0:
                published_scheduled_risk_level = "OVERDUE"
            elif published_scheduled_due_gap_days >= -1:
                published_scheduled_risk_level = "TIGHT"
            else:
                published_scheduled_risk_level = "SAFE"
        delay_risk_source = "UNKNOWN"
        if final_process_eta_date:
            delay_risk_source = "FINAL_PROCESS_ETA"
        elif scheduled_finish_date:
            delay_risk_source = "SCHEDULE_FACT"
        elif _normalize_date_text(expected_finish_time):
            delay_risk_source = "ORDER_WINDOW"
        process_contexts = self._merge_process_contexts_with_schedule_fact(
            process_contexts=self._build_process_contexts(
                order_no=str(base_row["production_order_no"]),
                product_code=str(base_row["material_code"]),
                capacity_rows=capacity_rows,
                route_rows=route_rows,
                topology_by_process=topology_by_process,
            ),
            schedule_fact=schedule_fact,
        )
        manual_intervention_types = self._build_manual_intervention_types(
            manual_expected_start_override=manual_expected_start_override,
            priority_level=_normalize_priority_level((state_row or {}).get("priority_level"), PRIORITY_LEVEL_MAX),
            lock_flag=int((state_row or {}).get("lock_flag") or 0),
            frozen_flag=int((state_row or {}).get("frozen_flag") or 0),
        )
        reference_schedule_version_status_label = _schedule_version_status_label(
            reference_version_status
        )
        published_schedule_version_status_label = _schedule_version_status_label(
            published_version_status
        )
        if published_in_reference_version:
            reference_schedule_version_label = f"褰撳墠鏂规 {reference_version_no}"
        elif scheduled_in_reference_version and reference_version_no:
            reference_schedule_version_label = (
                f"参考排程 {reference_version_no}（{reference_schedule_version_status_label}）"
            )
        else:
            reference_schedule_version_label = "未进入排程"
        viewing_schedule_version_label = (
            f"当前方案 {reference_version_no}（{reference_schedule_version_status_label}）"
            if reference_version_no
            else "鏆傛棤褰撳墠鏂规"
        )
        published_schedule_version_label = (
            f"褰撳墠鏂规 {published_version_no}"
            if published_version_no
            else "鏆傛棤褰撳墠鏂规"
        )
        return {
            "order_no": base_row["production_order_no"],
            "product_code": base_row["material_code"],
            "product_name_cn": base_row["material_name"],
            "product_name": base_row["material_name"],
            "has_process_route": len(route_rows) > 0,
            "order_qty": production_qty,
            "completed_qty": completed_qty,
            "remaining_qty": remaining_qty,
            "progress_rate": progress_rate,
            "promised_due_date": promised_due_date,
            "due_in_days": _days_from_today(promised_due_date),
            "expected_start_time": expected_start_time,
            "expected_start_shift": _expected_start_shift_from_datetime_text(expected_start_time),
            "expected_finish_time": expected_finish_time,
            "expected_start_date": expected_start_date,
            "manual_expected_start_date": manual_expected_start_date,
            "manual_expected_start_time": manual_expected_start_time,
            "manual_expected_start_shift": manual_expected_start_shift,
            "manual_expected_start_override": manual_expected_start_override,
            "scheduled_start_date": scheduled_start_date,
            "scheduled_start_time": scheduled_start_time,
            "scheduled_start_shift": scheduled_start_shift,
            "scheduled_finish_date": scheduled_finish_date,
            "scheduled_finish_time": scheduled_finish_time,
            "expected_start_due_gap_days": expected_start_due_gap_days,
            "is_naturally_overdue": is_naturally_overdue,
            "order_window_due_gap_days": order_window_due_gap_days,
            "order_window_risk_level": order_window_risk_level,
            "priority_level": _normalize_priority_level((state_row or {}).get("priority_level"), PRIORITY_LEVEL_MAX),
            "urgent_flag": _urgent_flag_from_priority_level((state_row or {}).get("priority_level")),
            "lock_flag": int((state_row or {}).get("lock_flag") or 0),
            "frozen_flag": int((state_row or {}).get("frozen_flag") or 0),
            "status": status,
            "order_status": order_status,
            "erp_status": erp_status,
            "production_batch_no": (state_row or {}).get("production_batch_no")
            or (f"{source_bill_no}-B1" if source_bill_no else "-"),
            "final_process_code": final_process_code,
            "final_process_name_cn": final_process_name_cn,
            "final_process_completed_qty": final_process_completed_qty,
            "final_process_last_report_date": (final_process_metrics or {}).get("final_process_last_report_date"),
            "final_process_eta_date": final_process_eta_date,
            "final_process_due_gap_days": final_process_due_gap_days,
            "scheduled_due_gap_days": scheduled_due_gap_days,
            "final_process_risk_level": final_process_risk_level,
            "scheduled_risk_level": scheduled_risk_level,
            "published_scheduled_due_gap_days": published_scheduled_due_gap_days,
            "published_scheduled_risk_level": published_scheduled_risk_level,
            "delay_risk_source": delay_risk_source,
            "scheduled_in_reference_version": scheduled_in_reference_version,
            "material_shortage_count": int((shortage_summary or {}).get("shortage_material_count") or 0),
            "material_shortage_summary": str((shortage_summary or {}).get("summary_text") or "").strip(),
            "material_shortage_start_date": _normalize_date_text(
                (shortage_summary or {}).get("shortage_start_date")
            ),
            "material_shortage_first_process_code": str(
                (shortage_summary or {}).get("first_impacted_process_code") or ""
            ).strip().upper()
            or None,
            "material_shortage_first_process_name_cn": str(
                (shortage_summary or {}).get("first_impacted_process_name_cn") or ""
            ).strip()
            or None,
            "material_shortage_first_material_code": str(
                (shortage_summary or {}).get("first_material_code") or ""
            ).strip().upper()
            or None,
            "material_shortage_first_material_name": str(
                (shortage_summary or {}).get("first_material_name") or ""
            ).strip()
            or None,
            "material_shortage_items": shortage_items,
            "actual_workshop_codes": actual_workshop_codes,
            "actual_line_codes": actual_line_codes,
            "actual_process_codes": actual_process_codes,
            "manual_intervention_types": manual_intervention_types,
            "manual_intervention_count": len(manual_intervention_types),
            "process_contexts": process_contexts,
        }

    def _build_expected_start_save_impact(self, row: dict[str, Any]) -> dict[str, Any]:
        expected_start_date = _normalize_date_text(row.get("expected_start_date"))
        expected_start_shift = _normalize_shift_code(row.get("expected_start_shift"))
        expected_start_text = (
            f"{expected_start_date} {'澶滅彮' if expected_start_shift == 'NIGHT' else '鐧界彮'}"
            if expected_start_date
            else "未设置"
        )
        viewing_version_no = str(row.get("viewing_schedule_version_no") or "").strip() or None
        published_version_no = str(row.get("published_schedule_version_no") or "").strip() or None
        impacts_viewing_version = bool(row.get("scheduled_in_viewing_version"))
        impacts_published_version = bool(row.get("scheduled_in_published_version"))
        viewing_conflict = impacts_viewing_version and (
            _normalize_date_text(row.get("scheduled_start_date")) != expected_start_date
            or _normalize_shift_code(row.get("scheduled_start_shift")) != expected_start_shift
        )
        published_conflict = impacts_published_version and (
            _normalize_date_text(row.get("published_scheduled_start_date")) != expected_start_date
            or _normalize_shift_code(row.get("published_scheduled_start_shift")) != expected_start_shift
        )
        has_schedule_conflict = viewing_conflict or published_conflict
        causes_unavoidable_delay = bool(row.get("is_naturally_overdue"))
        requires_reschedule = has_schedule_conflict
        summary_items = [f"鎵嬪伐寮€宸ョ‖绾︽潫宸茶涓猴細{expected_start_text}"]
        if impacts_published_version and published_version_no:
            summary_items.append(f"浼氬奖鍝嶅綋鍓嶆柟妗?{published_version_no}")
        else:
            summary_items.append("褰撳墠涓嶄細鐩存帴鏀瑰啓褰撳墠鏂规")
        if impacts_viewing_version and viewing_version_no:
            summary_items.append(f"会影响当前排程口径 {viewing_version_no} 的判断")
        if has_schedule_conflict:
            summary_items.append("与现有排程事实冲突")
        if causes_unavoidable_delay:
            summary_items.append("璇ヨ鍗曞凡蹇呯劧寤舵湡")
        if requires_reschedule:
            summary_items.append("需要立即重排")
        return {
            "expected_start_text": expected_start_text,
            "impacts_viewing_version": impacts_viewing_version,
            "viewing_version_no": viewing_version_no,
            "impacts_published_version": impacts_published_version,
            "published_version_no": published_version_no,
            "has_schedule_conflict": has_schedule_conflict,
            "causes_unavoidable_delay": causes_unavoidable_delay,
            "requires_reschedule": requires_reschedule,
            "summary_items": summary_items,
        }

    def _build_reference_schedule_context(self, version_no: str | None) -> dict[str, Any]:
        if not version_no:
            return {"version": None, "order_map": {}}
        version = self.get_schedule_version(version_no)
        task_rows = self._list_schedule_task_detail_rows(version_no)
        order_map: dict[str, dict[str, Any]] = {}
        for row in task_rows:
            order_no = str(row.get("production_order_no") or "").strip()
            calendar_date = _normalize_date_text(row.get("calendar_date"))
            if not order_no or not calendar_date:
                continue
            shift_code = _normalize_shift_code(row.get("shift_code"))
            start_slot = _slot_index_from_text(calendar_date, shift_code)
            scheduled_finish_date = (
                (date.fromisoformat(calendar_date) + timedelta(days=1)).isoformat()
                if shift_code == "NIGHT"
                else calendar_date
            )
            scheduled_start_time = str(row.get("plan_start_time") or "").strip() or _iso_at(
                calendar_date,
                "20:00:00" if shift_code == "NIGHT" else "08:00:00",
            )
            scheduled_finish_time = _iso_at(
                scheduled_finish_date,
                "08:00:00" if shift_code == "NIGHT" else "20:00:00",
            )
            current = order_map.get(order_no)
            if current is None:
                current = {
                    "scheduled_start_slot": start_slot,
                    "scheduled_start_date": calendar_date,
                    "scheduled_start_time": scheduled_start_time,
                    "scheduled_start_shift": shift_code,
                    "scheduled_finish_slot": start_slot,
                    "scheduled_finish_date": scheduled_finish_date,
                    "scheduled_finish_time": scheduled_finish_time,
                    "actual_workshop_codes": set(),
                    "actual_line_codes": set(),
                    "actual_process_codes": set(),
                    "actual_process_map": {},
                }
                order_map[order_no] = current
            if start_slot < int(current["scheduled_start_slot"]):
                current["scheduled_start_slot"] = start_slot
                current["scheduled_start_date"] = calendar_date
                current["scheduled_start_time"] = scheduled_start_time
                current["scheduled_start_shift"] = shift_code
            if start_slot >= int(current["scheduled_finish_slot"]):
                current["scheduled_finish_slot"] = start_slot
                current["scheduled_finish_date"] = scheduled_finish_date
                current["scheduled_finish_time"] = scheduled_finish_time

            workshop_code = str(row.get("workshop_code") or "").strip().upper()
            line_code = str(row.get("line_code") or "").strip().upper()
            process_code = str(row.get("process_code") or "").strip().upper()
            process_name_cn = str(row.get("process_name_cn") or process_code).strip() or process_code
            if workshop_code:
                current["actual_workshop_codes"].add(workshop_code)
            if line_code:
                current["actual_line_codes"].add(line_code)
            if process_code:
                current["actual_process_codes"].add(process_code)
                process_item = current["actual_process_map"].get(process_code)
                if process_item is None:
                    process_item = {
                        "process_code": process_code,
                        "process_name_cn": process_name_cn,
                        "actual_workshop_codes": set(),
                        "actual_line_codes": set(),
                    }
                    current["actual_process_map"][process_code] = process_item
                if workshop_code:
                    process_item["actual_workshop_codes"].add(workshop_code)
                if line_code:
                    process_item["actual_line_codes"].add(line_code)

        normalized_order_map: dict[str, dict[str, Any]] = {}
        for order_no, item in order_map.items():
            normalized_order_map[order_no] = {
                "scheduled_start_date": item["scheduled_start_date"],
                "scheduled_start_time": item["scheduled_start_time"],
                "scheduled_start_shift": item["scheduled_start_shift"],
                "scheduled_finish_date": item["scheduled_finish_date"],
                "scheduled_finish_time": item["scheduled_finish_time"],
                "actual_workshop_codes": sorted(item["actual_workshop_codes"]),
                "actual_line_codes": sorted(item["actual_line_codes"]),
                "actual_process_codes": sorted(item["actual_process_codes"]),
                "actual_process_map": {
                    process_code: {
                        "process_code": process_code,
                        "process_name_cn": process_item["process_name_cn"],
                        "actual_workshop_codes": sorted(process_item["actual_workshop_codes"]),
                        "actual_line_codes": sorted(process_item["actual_line_codes"]),
                    }
                    for process_code, process_item in item["actual_process_map"].items()
                },
            }
        return {"version": version, "order_map": normalized_order_map}

    def _merge_process_contexts_with_schedule_fact(
        self,
        *,
        process_contexts: list[dict[str, Any]],
        schedule_fact: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        actual_process_map = (
            schedule_fact.get("actual_process_map")
            if isinstance(schedule_fact, dict) and isinstance(schedule_fact.get("actual_process_map"), dict)
            else {}
        )
        merged: list[dict[str, Any]] = []
        for context in process_contexts:
            process_code = str(context.get("process_code") or "").strip().upper()
            actual_process_item = actual_process_map.get(process_code, {})
            merged.append(
                {
                    **context,
                    "actual_workshop_codes": actual_process_item.get("actual_workshop_codes", []),
                    "actual_line_codes": actual_process_item.get("actual_line_codes", []),
                }
            )
        return merged

    def _build_manual_intervention_types(
        self,
        *,
        manual_expected_start_override: bool,
        priority_level: int,
        lock_flag: int,
        frozen_flag: int,
    ) -> list[str]:
        items: list[str] = []
        if manual_expected_start_override:
            items.append("EXPECTED_START")
        if priority_level < PRIORITY_LEVEL_MAX:
            items.append("PRIORITY")
        if lock_flag == 1:
            items.append("LOCK")
        if frozen_flag == 1:
            items.append("FREEZE")
        return items

    def _build_process_contexts(
        self,
        *,
        order_no: str,
        product_code: str,
        capacity_rows: list[dict[str, Any]],
        route_rows: list[dict[str, Any]],
        topology_by_process: dict[str, dict[str, Any]] | dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        def normalize_candidate_rows(value: Any) -> list[dict[str, Any]]:
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return [value]
            return []

        capacity_rows_by_process = self._best_capacity_row_by_process(capacity_rows)

        if route_rows:
            contexts: list[dict[str, Any]] = []
            for index, row in enumerate(route_rows):
                process_code = str(row.get("process_code") or "").strip().upper()
                if not process_code:
                    continue
                candidate_rows = normalize_candidate_rows(
                    capacity_rows_by_process.get(process_code) or topology_by_process.get(process_code)
                )
                candidate_contexts = self._build_candidate_process_contexts(
                    process_code=process_code,
                    process_name_cn=str(row.get("process_name_cn") or process_code).strip() or process_code,
                    candidate_rows=candidate_rows,
                )
                primary_candidate = candidate_contexts[0] if candidate_contexts else {}
                capacity_per_shift = _to_number(primary_candidate.get("capacity_per_shift"), 0)
                contexts.append(
                    {
                        "sequence_no": index + 1,
                        "process_code": process_code,
                        "company_code": str(
                            primary_candidate.get("company_code") or DEFAULT_COMPANY_CODE
                        ).strip().upper()
                        or DEFAULT_COMPANY_CODE,
                        "process_name_cn": str(row.get("process_name_cn") or process_code).strip() or process_code,
                        "workshop_code": str(primary_candidate.get("workshop_code") or "-").strip() or "-",
                        "line_code": str(primary_candidate.get("line_code") or "-").strip() or "-",
                        "candidate_workshop_codes": [item["workshop_code"] for item in candidate_contexts],
                        "candidate_line_codes": [item["line_code"] for item in candidate_contexts],
                        "candidate_contexts": candidate_contexts,
                        "dependency_type": str(row.get("dependency_type") or "FS").strip().upper() or "FS",
                        "default_capacity_per_shift": capacity_per_shift,
                        "capacity_per_shift": capacity_per_shift,
                    }
                )
            return contexts

        contexts = []
        deduplicated_rows = sorted(
            capacity_rows_by_process.values(),
            key=lambda items: str((items[0] if items else {}).get("process_code") or ""),
        )
        for index, process_rows in enumerate(deduplicated_rows):
            primary_row = process_rows[0] if process_rows else {}
            process_code = str(primary_row.get("process_code") or "").strip().upper()
            if not process_code:
                continue
            candidate_contexts = self._build_candidate_process_contexts(
                process_code=process_code,
                process_name_cn=str(primary_row.get("process_name") or process_code).strip() or process_code,
                candidate_rows=process_rows,
            )
            primary_candidate = candidate_contexts[0] if candidate_contexts else {}
            contexts.append(
                {
                    "sequence_no": index + 1,
                    "process_code": process_code,
                    "company_code": str(primary_candidate.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper() or DEFAULT_COMPANY_CODE,
                    "process_name_cn": str(primary_row.get("process_name") or process_code).strip() or process_code,
                    "workshop_code": str(primary_candidate.get("workshop_code") or "-").strip() or "-",
                    "line_code": str(primary_candidate.get("line_code") or "-").strip() or "-",
                    "candidate_workshop_codes": [item["workshop_code"] for item in candidate_contexts],
                    "candidate_line_codes": [item["line_code"] for item in candidate_contexts],
                    "candidate_contexts": candidate_contexts,
                    "dependency_type": "FS",
                    "default_capacity_per_shift": _to_number(primary_candidate.get("capacity_per_shift"), 0),
                    "capacity_per_shift": _to_number(primary_candidate.get("capacity_per_shift"), 0),
                }
            )
        return contexts

    def _build_candidate_process_contexts(
        self,
        *,
        process_code: str,
        process_name_cn: str,
        candidate_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str, str]] = set()
        for row in candidate_rows:
            company_code = str(row.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper() or DEFAULT_COMPANY_CODE
            workshop_code = str(row.get("workshop_code") or "").strip().upper()
            line_code = str(row.get("line_code") or "").strip().upper()
            if not workshop_code or not line_code:
                continue
            key = (company_code, workshop_code, line_code)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            capacity_per_shift = _to_number(
                row.get("capacity_qty"),
                _to_number(row.get("capacity_per_shift"), 0),
            )
            out.append(
                {
                    "company_code": company_code,
                    "workshop_code": workshop_code,
                    "line_code": line_code,
                    "process_code": process_code,
                    "process_name_cn": process_name_cn,
                    "default_capacity_per_shift": capacity_per_shift,
                    "capacity_per_shift": capacity_per_shift,
                }
            )
        out.sort(
            key=lambda item: (
                -_to_number(item.get("capacity_per_shift"), 0),
                str(item.get("workshop_code") or ""),
                str(item.get("line_code") or ""),
            )
        )
        return out

    def _build_schedule_process_contexts(
        self,
        *,
        order_no: str,
        product_code: str,
        capacity_rows: list[dict[str, Any]],
        route_rows: list[dict[str, Any]],
        topology_by_process: dict[str, list[dict[str, Any]]],
        capacity_resolver: dict[str, dict[tuple[str, str, str, str, str], float]],
    ) -> list[dict[str, Any]]:
        if len(route_rows) == 0:
            raise server_error(
                code="SCHEDULE_ROUTE_REQUIRED",
                message="生成排程前必须先维护工艺路线。",
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
                message="当前订单没有可用于排程的工序上下文，请检查工艺路线和产线配置。",
                details={"order_no": order_no, "product_code": product_code},
            )

        for context in contexts:
            process_code = str(context.get("process_code") or "").strip().upper()
            candidate_contexts = (
                context.get("candidate_contexts")
                if isinstance(context.get("candidate_contexts"), list)
                else []
            )
            company_code = str(context.get("company_code") or "").strip().upper() or "COMPANY-MAIN"
            default_capacity_per_shift = _to_number(
                context.get("default_capacity_per_shift"),
                _to_number(context.get("capacity_per_shift"), 0),
            )
            if not process_code:
                raise server_error(
                    code="SCHEDULE_PROCESS_CODE_REQUIRED",
                    message="排程工序上下文缺少工序编码。",
                    details={"order_no": order_no, "product_code": product_code},
                )
            if len(candidate_contexts) == 0:
                raise server_error(
                    code="SCHEDULE_PROCESS_CANDIDATE_LINES_EMPTY",
                    message="当前工序没有可用的候选车间或产线，无法生成排程。",
                    details={
                        "order_no": order_no,
                        "product_code": product_code,
                        "process_code": process_code,
                    },
                )
            if default_capacity_per_shift <= SCHEDULE_NUMBER_EPSILON:
                raise server_error(
                    code="SCHEDULE_CAPACITY_PER_SHIFT_INVALID",
                    message="排程涉及的工序产能必须大于 0。",
                    details={
                        "order_no": order_no,
                        "product_code": product_code,
                        "process_code": process_code,
                        "capacity_per_shift": default_capacity_per_shift,
                    },
            )
            context["company_code"] = company_code
            primary_candidate = candidate_contexts[0]
            context["workshop_code"] = str(primary_candidate.get("workshop_code") or "").strip().upper()
            context["line_code"] = str(primary_candidate.get("line_code") or "").strip().upper()
            context["process_code"] = process_code
            context["default_capacity_per_shift"] = default_capacity_per_shift
            context["capacity_per_shift"] = default_capacity_per_shift
        return contexts

    def _build_schedule_capacity_resolver(
        self,
        *,
        capacity_source_mode: str,
    ) -> dict[str, dict[tuple[str, str, str, str, str], float]]:
        planned_map: dict[tuple[str, str, str, str, str, str], float] = {}
        actual_map: dict[tuple[str, str, str, str, str, str], float] = {}
        if capacity_source_mode in {"PLANNED", "ACTUAL"}:
            for row in fetch_all(
                self.connection,
                """
                SELECT
                    calendar_date,
                    shift_code,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    planned_capacity_qty
                FROM daily_line_capacity_plan
                """
            ):
                key = (
                    str(row.get("calendar_date") or "").strip(),
                    _normalize_shift_code(row.get("shift_code")),
                    str(row.get("company_code") or "COMPANY-MAIN").strip().upper() or "COMPANY-MAIN",
                    str(row.get("workshop_code") or "").strip().upper(),
                    str(row.get("line_code") or "").strip().upper(),
                    str(row.get("process_code") or "").strip().upper(),
                )
                planned_map[key] = _to_number(row.get("planned_capacity_qty"), 0)
        if capacity_source_mode == "ACTUAL":
            for row in fetch_all(
                self.connection,
                """
                SELECT
                    calendar_date,
                    shift_code,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    actual_capacity_qty
                FROM daily_line_capacity_actual
                """
            ):
                key = (
                    str(row.get("calendar_date") or "").strip(),
                    _normalize_shift_code(row.get("shift_code")),
                    str(row.get("company_code") or "COMPANY-MAIN").strip().upper() or "COMPANY-MAIN",
                    str(row.get("workshop_code") or "").strip().upper(),
                    str(row.get("line_code") or "").strip().upper(),
                    str(row.get("process_code") or "").strip().upper(),
                )
                actual_map[key] = _to_number(row.get("actual_capacity_qty"), 0)
        return {"planned": planned_map, "actual": actual_map}

    def _resolve_effective_capacity_per_shift(
        self,
        *,
        process_context: dict[str, Any],
        calendar_date: str,
        shift_code: str,
        capacity_resolver: dict[str, dict[tuple[str, str, str, str, str, str], float]],
    ) -> float:
        company_code = str(process_context.get("company_code") or "COMPANY-MAIN").strip().upper() or "COMPANY-MAIN"
        workshop_code = str(process_context.get("workshop_code") or "").strip().upper()
        line_code = str(process_context.get("line_code") or "").strip().upper()
        process_code = str(process_context.get("process_code") or "").strip().upper()
        lookup_key = (
            str(calendar_date or "").strip(),
            _normalize_shift_code(shift_code),
            company_code,
            workshop_code,
            line_code,
            process_code,
        )
        actual_map = capacity_resolver.get("actual") or {}
        if lookup_key in actual_map:
            return _to_number(actual_map[lookup_key], 0)
        planned_map = capacity_resolver.get("planned") or {}
        if lookup_key in planned_map:
            return _to_number(planned_map[lookup_key], 0)
        return _to_number(process_context.get("default_capacity_per_shift"), 0)

    def _capacity_usage_key(
        self,
        *,
        process_context: dict[str, Any],
        slot_index: int,
        calendar_date: str,
        shift_code: str,
        capacity_resolver: dict[str, dict[tuple[str, str, str, str, str, str], float]],
    ) -> tuple[Any, ...]:
        company_code = str(process_context.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper() or DEFAULT_COMPANY_CODE
        workshop_code = str(process_context.get("workshop_code") or "").strip().upper()
        line_code = str(process_context.get("line_code") or "").strip().upper()
        process_code = str(process_context.get("process_code") or "").strip().upper()
        lookup_key = (
            str(calendar_date or "").strip(),
            _normalize_shift_code(shift_code),
            company_code,
            workshop_code,
            line_code,
            process_code,
        )
        return ("SHIFT", int(slot_index), *lookup_key)

    def _select_candidate_context_for_slot(
        self,
        *,
        process_context: dict[str, Any],
        slot_index: int,
        calendar_date: str,
        used_capacity_by_slot: dict[tuple[Any, ...], float],
        capacity_resolver: dict[str, dict[tuple[str, str, str, str, str, str], float]],
    ) -> tuple[dict[str, Any] | None, float]:
        candidate_contexts = (
            process_context.get("candidate_contexts")
            if isinstance(process_context.get("candidate_contexts"), list)
            else []
        )
        if len(candidate_contexts) == 0:
            candidate_contexts = [process_context]

        best_candidate: dict[str, Any] | None = None
        best_available_capacity = 0.0
        best_sort_key: tuple[float, float, str, str] | None = None
        _, derived_shift_code = _slot_to_date_shift(slot_index)
        for candidate in candidate_contexts:
            capacity_per_shift = self._resolve_effective_capacity_per_shift(
                process_context=candidate,
                calendar_date=calendar_date,
                shift_code=derived_shift_code,
                capacity_resolver=capacity_resolver,
            )
            usage_key = self._capacity_usage_key(
                process_context=candidate,
                slot_index=slot_index,
                calendar_date=calendar_date,
                shift_code=derived_shift_code,
                capacity_resolver=capacity_resolver,
            )
            used_capacity = _to_number(used_capacity_by_slot.get(usage_key), 0)
            available_capacity = max(0.0, capacity_per_shift - used_capacity)
            if available_capacity <= SCHEDULE_NUMBER_EPSILON:
                continue
            load_ratio = used_capacity / capacity_per_shift if capacity_per_shift > SCHEDULE_NUMBER_EPSILON else 1.0
            sort_key = (
                round(load_ratio, 8),
                -available_capacity,
                str(candidate.get("workshop_code") or ""),
                str(candidate.get("line_code") or ""),
            )
            if best_sort_key is None or sort_key < best_sort_key:
                best_sort_key = sort_key
                best_candidate = candidate
                best_available_capacity = available_capacity
        return best_candidate, best_available_capacity

    def _estimate_required_shifts_for_process(
        self,
        *,
        process_context: dict[str, Any],
        required_qty: float,
        start_slot: int,
        planning_rules: dict[str, Any],
        day_mode_cache: dict[str, str],
        capacity_resolver: dict[str, dict[tuple[str, str, str, str, str], float]],
    ) -> int:
        remaining_qty = max(0.0, _to_number(required_qty, 0))
        if remaining_qty <= SCHEDULE_NUMBER_EPSILON:
            return 0
        slot_cursor = max(0, int(start_slot))
        occupied_slot_set: set[int] = set()
        simulated_used_capacity: dict[tuple[Any, ...], float] = {}
        for loop_guard in range(SCHEDULE_SLOT_SEARCH_GUARD):
            if remaining_qty <= SCHEDULE_NUMBER_EPSILON:
                break
            slot_index, calendar_date, _ = self._next_working_slot(
                start_slot=slot_cursor,
                planning_rules=planning_rules,
                day_mode_cache=day_mode_cache,
                allow_exact_start_slot=slot_cursor == max(0, int(start_slot)),
            )
            candidate_context, available_capacity = self._select_candidate_context_for_slot(
                process_context=process_context,
                slot_index=slot_index,
                calendar_date=calendar_date,
                used_capacity_by_slot=simulated_used_capacity,
                capacity_resolver=capacity_resolver,
            )
            if candidate_context is None or available_capacity <= SCHEDULE_NUMBER_EPSILON:
                slot_cursor = slot_index + 1
                continue
            usage_key = self._capacity_usage_key(
                process_context=candidate_context,
                slot_index=slot_index,
                calendar_date=calendar_date,
                shift_code=_slot_to_date_shift(slot_index)[1],
                capacity_resolver=capacity_resolver,
            )
            used_capacity = _to_number(simulated_used_capacity.get(usage_key), 0)
            planned_qty = min(remaining_qty, available_capacity)
            simulated_used_capacity[usage_key] = used_capacity + planned_qty
            remaining_qty -= planned_qty
            occupied_slot_set.add(slot_index)
            slot_cursor = slot_index if remaining_qty > SCHEDULE_NUMBER_EPSILON else slot_index + 1
        else:
            raise server_error(
                code="SCHEDULE_REQUIRED_SHIFTS_ESTIMATION_EXCEEDED",
                message="Unable to estimate required shifts within slot guard limit.",
                details={
                    "order_no": str(process_context.get("order_no") or ""),
                    "process_code": str(process_context.get("process_code") or ""),
                    "required_qty": required_qty,
                },
            )
        return len(occupied_slot_set)

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

    def _normalize_capacity_source_mode(self, value: object) -> str:
        normalized = str(value or "ACTUAL").strip().upper() or "ACTUAL"
        if normalized not in SUPPORTED_CAPACITY_SOURCE_MODES:
            raise bad_request(
                code="SCHEDULE_CAPACITY_SOURCE_MODE_INVALID",
                message="capacity_source_mode is invalid.",
                details={
                    "capacity_source_mode": normalized,
                    "supported": sorted(SUPPORTED_CAPACITY_SOURCE_MODES),
                },
            )
        return normalized

    def _normalize_fact_replan_capacity_source_mode(self, value: object) -> str:
        normalized = self._normalize_capacity_source_mode(value)
        if normalized not in {"ACTUAL", "PLANNED"}:
            raise bad_request(
                code="FACT_SCHEDULE_CAPACITY_SOURCE_MODE_INVALID",
                message="Fact replan capacity_source_mode must be ACTUAL or PLANNED.",
                details={
                    "capacity_source_mode": normalized,
                    "supported": ["ACTUAL", "PLANNED"],
                },
            )
        return normalized

    def _normalize_use_order_state_window(self, value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value == 1:
                return True
            if value == 0:
                return False
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False
        raise bad_request(
            code="SCHEDULE_USE_ORDER_STATE_WINDOW_INVALID",
            message="use_order_state_window is invalid.",
            details={"use_order_state_window": value},
        )

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
    ) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in capacity_rows:
            process_code = str(row.get("process_code") or "").strip().upper()
            if not process_code:
                continue
            out[process_code].append(row)
        for process_code in list(out):
            out[process_code] = sorted(
                out[process_code],
                key=lambda item: (
                    -_to_number(item.get("capacity_qty"), 0),
                    str(item.get("workshop_code") or ""),
                    str(item.get("line_code") or ""),
                ),
            )
        return out

    def _enabled_topology_by_process(
        self,
        topology_rows: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in topology_rows:
            if int(_to_number(row.get("enabled_flag"), 0)) != 1:
                continue
            process_code = str(row.get("process_code") or "").strip().upper()
            if not process_code:
                continue
            out[process_code].append(row)
        for process_code in list(out):
            out[process_code] = sorted(
                out[process_code],
                key=lambda item: (
                    -_to_number(item.get("capacity_per_shift"), 0),
                    str(item.get("workshop_code") or ""),
                    str(item.get("line_code") or ""),
                ),
            )
        return out

    def _build_fact_replan_boundary(self, *, simulation_start: date) -> dict[str, Any]:
        latest_report_row = fetch_one(
            self.connection,
            """
            SELECT report_time
            FROM work_reports
            ORDER BY report_time DESC, report_id DESC
            LIMIT 1
            """,
        )
        reported_slot = None
        report_time_text = str((latest_report_row or {}).get("report_time") or "").strip()
        if report_time_text:
            report_date = _normalize_date_text(
                datetime.fromisoformat(report_time_text)
                .astimezone(LOCAL_TIMEZONE)
                .date()
                .isoformat()
            )
            if report_date is not None:
                reported_slot = _slot_index_from_text(
                    report_date,
                    _expected_start_shift_from_datetime_text(report_time_text),
                )

        simulation_slot = _slot_index_for(simulation_start, "DAY")
        next_slot = simulation_slot if reported_slot is None else max(simulation_slot, reported_slot + 1)
        boundary_date, boundary_shift = _slot_to_date_shift(next_slot)
        return {
            "reported_slot": reported_slot,
            "next_slot": next_slot,
            "next_date": boundary_date.isoformat(),
            "next_shift_code": boundary_shift,
        }

    def _build_fact_locked_task_rows(
        self,
        *,
        current_version_no: str | None,
        version_no: str,
        reported_slot: int | None,
    ) -> list[tuple[Any, ...]]:
        if not current_version_no or reported_slot is None:
            return []
        rows = fetch_all(
            self.connection,
            """
            SELECT
                task_no,
                production_order_no,
                process_code,
                process_name_cn,
                workshop_code,
                line_code,
                calendar_date,
                shift_code,
                plan_qty,
                plan_start_time
            FROM schedule_tasks
            WHERE version_no = ?
            ORDER BY task_no ASC
            """,
            (current_version_no,),
        )
        tasks: list[tuple[Any, ...]] = []
        next_task_no = 1
        for row in rows:
            calendar_date = _normalize_date_text(row.get("calendar_date"))
            if calendar_date is None:
                continue
            shift_code = _normalize_shift_code(row.get("shift_code"))
            slot_index = _slot_index_from_text(calendar_date, shift_code)
            if slot_index > reported_slot:
                continue
            tasks.append(
                (
                    version_no,
                    next_task_no,
                    str(row.get("production_order_no") or "").strip(),
                    str(row.get("process_code") or "").strip().upper(),
                    str(row.get("process_name_cn") or row.get("process_code") or "").strip(),
                    str(row.get("workshop_code") or "").strip().upper() or None,
                    str(row.get("line_code") or "").strip().upper() or None,
                    calendar_date,
                    shift_code,
                    _to_number(row.get("plan_qty"), 0),
                    row.get("plan_start_time"),
                )
            )
            next_task_no += 1
        return tasks

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
        allow_exact_start_slot: bool = False,
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
            if allow_exact_start_slot and slot_cursor == max(0, int(start_slot)):
                if shift_code in self._allowed_shifts_for_day_mode(day_mode):
                    return slot_cursor, date_text, shift_code
                slot_cursor += 1
                continue
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
        used_capacity_by_slot: dict[tuple[Any, ...], float],
        capacity_resolver: dict[str, dict[tuple[str, str, str, str, str], float]],
    ) -> tuple[list[dict[str, Any]], int]:
        remaining_qty = max(0.0, _to_number(required_qty, 0))
        if remaining_qty <= SCHEDULE_NUMBER_EPSILON:
            return [], int(first_slot)

        process_code = str(process_context.get("process_code") or "").strip().upper()
        default_capacity_per_shift = _to_number(process_context.get("default_capacity_per_shift"), 0)
        if default_capacity_per_shift <= SCHEDULE_NUMBER_EPSILON:
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
                allow_exact_start_slot=slot_cursor == max(0, int(first_slot)),
            )
            candidate_context, available_capacity = self._select_candidate_context_for_slot(
                process_context=process_context,
                slot_index=slot_index,
                calendar_date=calendar_date,
                used_capacity_by_slot=used_capacity_by_slot,
                capacity_resolver=capacity_resolver,
            )
            if candidate_context is None or available_capacity <= SCHEDULE_NUMBER_EPSILON:
                slot_cursor = slot_index + 1
                loop_guard += 1
                continue
            key = self._capacity_usage_key(
                process_context=candidate_context,
                slot_index=slot_index,
                calendar_date=calendar_date,
                shift_code=shift_code,
                capacity_resolver=capacity_resolver,
            )
            used_capacity = _to_number(used_capacity_by_slot.get(key), 0)

            planned_qty = min(remaining_qty, available_capacity)
            used_capacity_by_slot[key] = used_capacity + planned_qty
            allocations.append(
                {
                    "calendar_date": calendar_date,
                    "shift_code": shift_code,
                    "workshop_code": str(candidate_context.get("workshop_code") or "").strip().upper(),
                    "line_code": str(candidate_context.get("line_code") or "").strip().upper(),
                    "plan_qty": planned_qty,
                }
            )
            remaining_qty -= planned_qty
            last_slot = slot_index
            slot_cursor = slot_index if remaining_qty > SCHEDULE_NUMBER_EPSILON else slot_index + 1
            loop_guard += 1

        return allocations, last_slot

    def _build_schedule_order_summary_map_from_generated_tasks(
        self,
        *,
        tasks: list[tuple[Any, ...]],
        order_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        order_row_by_no = {
            str(row.get("production_order_no") or "").strip(): row for row in order_rows
        }
        out: dict[str, dict[str, Any]] = {}
        for task in tasks:
            if len(task) < 10:
                continue
            order_no = str(task[2] or "").strip()
            if not order_no:
                continue
            base_row = order_row_by_no.get(order_no) or {}
            current = out.get(order_no)
            if current is None:
                current = {
                    "order_no": order_no,
                    "material_code": str(base_row.get("material_code") or "").strip(),
                    "material_name": str(
                        base_row.get("material_name") or base_row.get("material_code") or ""
                    ).strip(),
                    "order_qty": _to_number(base_row.get("production_qty"), 0),
                    "planned_ratio": 0.0,
                    "planned_qty": 0.0,
                }
                out[order_no] = current
            current["planned_qty"] += _to_number(task[9], 0)
        for row in out.values():
            order_qty = _to_number(row.get("order_qty"), 0)
            row["planned_ratio"] = (
                max(0.0, min(1.0, _to_number(row.get("planned_qty"), 0) / order_qty))
                if order_qty > 0
                else 0.0
            )
        return out

    def _build_generated_schedule_material_shortages(
        self,
        *,
        order_summary_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        material_map = self._build_schedule_material_usage_map(
            order_summary_map,
            material_rows=self._list_expanded_schedule_material_rows(),
        )
        impacted_order_nos: set[str] = set()
        items: list[dict[str, Any]] = []
        for material_code in sorted(material_map):
            current = material_map[material_code]
            estimated_inventory_qty = _to_number(current.get("estimated_inventory_qty"), 0)
            if estimated_inventory_qty >= 0:
                continue
            order_nos = sorted(
                {
                    str(order_no).strip()
                    for order_no in current.get("order_nos", [])
                    if str(order_no).strip()
                }
            )
            impacted_order_nos.update(order_nos)
            items.append(
                {
                    "material_code": material_code,
                    "material_name": current.get("material_name"),
                    "supply_type_name": current.get("supply_type_name"),
                    "inventory_qty": _to_number(current.get("inventory_qty"), 0),
                    "planned_consume_qty": _to_number(current.get("planned_consume_qty"), 0),
                    "estimated_inventory_qty": estimated_inventory_qty,
                    "shortage_qty": abs(estimated_inventory_qty),
                    "order_nos": order_nos,
                }
            )
        items.sort(
            key=lambda item: (
                -_to_number(item.get("shortage_qty"), 0),
                str(item.get("material_code") or ""),
            )
        )
        return {
            "summary": {
                "shortage_material_count": len(items),
                "impacted_order_count": len(impacted_order_nos),
            },
            "items": items,
        }

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
                    _normalize_priority_level(item.get("priority_level"), PRIORITY_LEVEL_MAX),
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
                    _normalize_priority_level(item.get("priority_level"), PRIORITY_LEVEL_MAX),
                    -_to_number(item.get("total_capacity_per_shift"), 0),
                    -_to_number(item.get("min_capacity_per_shift"), 0),
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
                    _normalize_priority_level(item.get("priority_level"), PRIORITY_LEVEL_MAX),
                    int(_to_number(item.get("slack_days"), 0)),
                    item.get("due_date"),
                    item.get("start_date"),
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
        used_capacity_by_slot: dict[tuple[Any, ...], float],
        capacity_resolver: dict[str, dict[tuple[str, str, str, str, str], float]],
    ) -> int:
        process_code = str(process_context.get("process_code") or "").strip().upper()
        default_capacity_per_shift = _to_number(process_context.get("default_capacity_per_shift"), 0)
        if default_capacity_per_shift <= SCHEDULE_NUMBER_EPSILON:
            raise server_error(
                code="SCHEDULE_CAPACITY_PER_SHIFT_INVALID",
                message="capacity_per_shift must be greater than 0 for all scheduled processes.",
                details={"process_code": process_code},
            )

        slot_cursor = max(0, int(start_slot))
        for _ in range(SCHEDULE_SLOT_SEARCH_GUARD):
            slot_index, calendar_date, _ = self._next_working_slot(
                start_slot=slot_cursor,
                planning_rules=planning_rules,
                day_mode_cache=day_mode_cache,
                allow_exact_start_slot=slot_cursor == max(0, int(start_slot)),
            )
            capacity_per_shift = self._resolve_effective_capacity_per_shift(
                process_context=process_context,
                calendar_date=calendar_date,
                shift_code=_slot_to_date_shift(slot_index)[1],
                capacity_resolver=capacity_resolver,
            )
            key = self._capacity_usage_key(
                process_context=process_context,
                slot_index=slot_index,
                calendar_date=calendar_date,
                shift_code=_slot_to_date_shift(slot_index)[1],
                capacity_resolver=capacity_resolver,
            )
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
        used_capacity_by_slot: dict[tuple[Any, ...], float],
        capacity_resolver: dict[str, dict[tuple[str, str, str, str, str], float]],
    ) -> dict[str, int]:
        process_contexts = candidate["process_contexts"]
        if len(process_contexts) == 0:
            raise server_error(
                code="SCHEDULE_PROCESS_CONTEXTS_EMPTY",
                message="No process contexts available for schedule candidate.",
                details={"order_no": candidate.get("order_no")},
            )

        first_context = process_contexts[0]
        first_slot = int(candidate.get("start_slot") or 0)

        simulated_used_capacity = dict(used_capacity_by_slot)
        first_ready_slot = None
        projected_finish_slot = first_slot
        next_start_slot = first_slot
        for process_context in process_contexts:
            context_start_slot = next_start_slot
            allocations, last_slot = self._allocate_process_tasks(
                order_no=str(candidate.get("order_no") or ""),
                process_context=process_context,
                required_qty=_to_number(candidate.get("remaining_qty"), 0),
                first_slot=context_start_slot,
                planning_rules=planning_rules,
                day_mode_cache=day_mode_cache,
                used_capacity_by_slot=simulated_used_capacity,
                capacity_resolver=capacity_resolver,
            )
            if allocations and first_ready_slot is None:
                first_ready_slot = _slot_index_from_text(
                    str(allocations[0]["calendar_date"]),
                    str(allocations[0]["shift_code"]),
                )
            projected_finish_slot = last_slot
            next_start_slot = last_slot + 1
        if first_ready_slot is None:
            first_ready_slot = first_slot
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
        used_capacity_by_slot: dict[tuple[Any, ...], float],
        capacity_resolver: dict[str, dict[tuple[str, str, str, str, str], float]],
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
                capacity_resolver=capacity_resolver,
            )
            late_slots = int(metrics["projected_lateness_slots"])
            late_rank = 0 if late_slots > 0 else 1
            late_severity = -max(late_slots, 0)
            business_head = (
                -int(candidate.get("frozen_flag") or 0),
                -int(candidate.get("lock_flag") or 0),
                _normalize_priority_level(candidate.get("priority_level"), PRIORITY_LEVEL_MAX),
            )
            base_tail = (str(candidate.get("order_no") or ""),)

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
            SELECT
                simulation_state.singleton_key,
                simulation_state.current_date AS current_date,
                simulation_state.updated_at
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
        skeleton_count = fetch_one(
            self.connection,
            "SELECT COUNT(1) AS total FROM masterdata_line_skeletons",
        )
        need_topology_seed = int(topology_count["total"]) == 0
        need_route_seed = int(route_count["total"]) == 0
        need_skeleton_seed = int(skeleton_count["total"]) == 0
        if not need_topology_seed and not need_route_seed and not need_skeleton_seed:
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
        route_rows = self._build_route_seed_rows(upstream_route_rows) if need_route_seed else self._list_route_rows()
        if len(route_rows) == 0:
            raise server_error(
                code="MASTERDATA_PROCESS_ROUTES_EMPTY",
                message="Upstream process route seed returned no rows.",
            )
        if need_topology_seed and len(topology_rows) == 0:
            raise server_error(
                code="MASTERDATA_LINE_TOPOLOGY_EMPTY",
                message="Upstream line topology seed returned no rows.",
            )
        base_topology_rows = topology_rows if need_topology_seed else self._list_line_topology_rows()
        normalized_topology_rows = (
            self._build_default_angio_line_topology_rows(route_rows, base_topology_rows)
            if need_topology_seed or need_skeleton_seed
            else base_topology_rows
        )
        skeleton_rows = (
            self._build_line_skeleton_seed_rows(base_topology_rows)
            if need_skeleton_seed
            else []
        )
        updated_at = utc_now()
        with transaction(self.connection):
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
                        is_final_process,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                            int(_to_number(row.get("is_final_process"), 0)),
                            updated_at,
                        )
                        for row in route_rows
                    ],
                )
            if need_skeleton_seed:
                self.connection.execute("DELETE FROM masterdata_line_skeletons")
                self.connection.executemany(
                    """
                    INSERT INTO masterdata_line_skeletons (
                        company_code,
                        workshop_code,
                        workshop_name,
                        line_code,
                        line_name,
                        enabled_flag,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            row["company_code"],
                            row["workshop_code"],
                            row["workshop_name"],
                            row["line_code"],
                            row["line_name"],
                            row["enabled_flag"],
                            updated_at,
                        )
                        for row in skeleton_rows
                    ],
                )
            if need_topology_seed or need_skeleton_seed:
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
                        for row in normalized_topology_rows
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
        return self._apply_default_final_process_flags(out)

    def _apply_default_final_process_flags(
        self,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        max_sequence_by_product: dict[str, int] = {}
        marked_count_by_product: dict[str, int] = defaultdict(int)
        for row in rows:
            product_code = str(row.get("product_code") or "").strip().upper()
            sequence_no = int(_to_number(row.get("sequence_no"), 0))
            if not product_code or sequence_no <= 0:
                continue
            max_sequence_by_product[product_code] = max(
                max_sequence_by_product.get(product_code, 0),
                sequence_no,
            )
            if int(_to_number(row.get("is_final_process"), 0)) == 1:
                marked_count_by_product[product_code] += 1

        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            product_code = str(row.get("product_code") or "").strip().upper()
            sequence_no = int(_to_number(row.get("sequence_no"), 0))
            has_marked = marked_count_by_product.get(product_code, 0) > 0
            is_final_process = (
                int(_to_number(row.get("is_final_process"), 0)) == 1
                if has_marked
                else (
                    bool(product_code)
                    and sequence_no > 0
                    and sequence_no == max_sequence_by_product.get(product_code, -1)
                )
            )
            normalized_rows.append(
                {
                    **row,
                    "is_final_process": 1 if is_final_process else 0,
                }
            )
        return normalized_rows

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

    def _build_line_skeleton_seed_rows(
        self,
        topology_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in topology_rows:
            company_code = str(row.get("company_code") or "COMPANY-MAIN").strip().upper() or "COMPANY-MAIN"
            workshop_code = str(row.get("workshop_code") or "").strip().upper()
            line_code = str(row.get("line_code") or "").strip().upper()
            if not workshop_code or not line_code:
                continue
            key = (company_code, workshop_code, line_code)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "company_code": company_code,
                    "workshop_code": workshop_code,
                    "workshop_name": str(row.get("workshop_name") or workshop_code).strip() or workshop_code,
                    "line_code": line_code,
                    "line_name": str(row.get("line_name") or line_code).strip() or line_code,
                    "enabled_flag": 1,
                }
            )
        default_key = ("COMPANY-MAIN", DEFAULT_ANGIO_WORKSHOP_CODE, DEFAULT_ANGIO_LINE_CODE)
        if default_key not in seen:
            out.append(
                {
                    "company_code": "COMPANY-MAIN",
                    "workshop_code": DEFAULT_ANGIO_WORKSHOP_CODE,
                    "workshop_name": DEFAULT_ANGIO_WORKSHOP_NAME,
                    "line_code": DEFAULT_ANGIO_LINE_CODE,
                    "line_name": DEFAULT_ANGIO_LINE_NAME,
                    "enabled_flag": 1,
                }
            )
        out.sort(
            key=lambda item: (
                str(item["workshop_code"]),
                str(item["line_code"]),
            )
        )
        return out

    def _build_default_angio_line_topology_rows(
        self,
        route_rows: list[dict[str, Any]],
        topology_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        angio_route_rows = [
            row
            for row in route_rows
            if str(row.get("product_code") or "").strip().upper() in ANGIO_CATHETER_PRODUCT_CODES
        ]
        if len(angio_route_rows) == 0:
            raise server_error(
                code="ANGIO_ROUTE_ROWS_EMPTY",
                message="No angio catheter process routes are available for default topology generation.",
            )
        ordered_process_codes: list[str] = []
        meta_by_process: dict[str, dict[str, Any]] = {}
        for row in angio_route_rows:
            process_code = str(row.get("process_code") or "").strip().upper()
            if not process_code:
                continue
            if process_code not in meta_by_process:
                ordered_process_codes.append(process_code)
                meta_by_process[process_code] = {
                    "process_name_cn": str(row.get("process_name_cn") or process_code).strip() or process_code,
                    "capacity_per_shift": _to_number(row.get("capacity_per_shift"), 0),
                    "required_workers": int(_to_number(row.get("required_manpower_per_group"), 0)),
                    "required_machines": int(_to_number(row.get("required_equipment_count"), 0)),
                    "enabled_flag": 1 if int(_to_number(row.get("enabled_flag"), 1)) == 1 else 0,
                }
                continue
            current = meta_by_process[process_code]
            current["capacity_per_shift"] = max(
                _to_number(current.get("capacity_per_shift"), 0),
                _to_number(row.get("capacity_per_shift"), 0),
            )
            current["required_workers"] = max(
                int(_to_number(current.get("required_workers"), 0)),
                int(_to_number(row.get("required_manpower_per_group"), 0)),
            )
            current["required_machines"] = max(
                int(_to_number(current.get("required_machines"), 0)),
                int(_to_number(row.get("required_equipment_count"), 0)),
            )
            if not current.get("process_name_cn"):
                current["process_name_cn"] = (
                    str(row.get("process_name_cn") or process_code).strip() or process_code
                )
            if int(_to_number(row.get("enabled_flag"), 1)) == 1:
                current["enabled_flag"] = 1
        for row in topology_rows:
            process_code = str(row.get("process_code") or "").strip().upper()
            if process_code not in meta_by_process:
                continue
            current = meta_by_process[process_code]
            current["capacity_per_shift"] = max(
                _to_number(current.get("capacity_per_shift"), 0),
                _to_number(row.get("capacity_per_shift"), 0),
            )
            current["required_workers"] = max(
                int(_to_number(current.get("required_workers"), 0)),
                int(_to_number(row.get("required_workers"), 0)),
            )
            current["required_machines"] = max(
                int(_to_number(current.get("required_machines"), 0)),
                int(_to_number(row.get("required_machines"), 0)),
            )
            if not current.get("process_name_cn"):
                current["process_name_cn"] = (
                    str(row.get("process_name_cn") or process_code).strip() or process_code
                )
            if int(_to_number(row.get("enabled_flag"), 0)) == 1:
                current["enabled_flag"] = 1
        return [
            {
                "company_code": "COMPANY-MAIN",
                "workshop_code": DEFAULT_ANGIO_WORKSHOP_CODE,
                "workshop_name": DEFAULT_ANGIO_WORKSHOP_NAME,
                "line_code": DEFAULT_ANGIO_LINE_CODE,
                "line_name": DEFAULT_ANGIO_LINE_NAME,
                "process_code": process_code,
                "capacity_per_shift": _to_number(meta_by_process[process_code].get("capacity_per_shift"), 0),
                "required_workers": int(_to_number(meta_by_process[process_code].get("required_workers"), 0)),
                "required_machines": int(_to_number(meta_by_process[process_code].get("required_machines"), 0)),
                "enabled_flag": 1 if int(_to_number(meta_by_process[process_code].get("enabled_flag"), 0)) == 1 else 0,
            }
            for process_code in ordered_process_codes
        ]

    def _resolve_final_process_meta_by_product(
        self,
        product_codes: set[str],
    ) -> dict[str, dict[str, str]]:
        normalized_product_codes = {
            str(product_code or "").strip().upper()
            for product_code in product_codes
            if str(product_code or "").strip()
        }
        if not normalized_product_codes:
            return {}
        placeholders = ",".join("?" for _ in normalized_product_codes)
        rows = fetch_all(
            self.connection,
            f"""
            SELECT
                product_code,
                sequence_no,
                process_code,
                process_name_cn,
                COALESCE(is_final_process, 0) AS is_final_process
            FROM masterdata_process_routes
            WHERE product_code IN ({placeholders})
            ORDER BY product_code ASC, sequence_no ASC
            """,
            tuple(sorted(normalized_product_codes)),
        )
        rows_by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            product_code = str(row.get("product_code") or "").strip().upper()
            process_code = str(row.get("process_code") or "").strip().upper()
            sequence_no = int(_to_number(row.get("sequence_no"), 0))
            if not product_code or not process_code or sequence_no <= 0:
                continue
            rows_by_product[product_code].append(
                {
                    "sequence_no": sequence_no,
                    "process_code": process_code,
                    "process_name_cn": str(row.get("process_name_cn") or process_code).strip() or process_code,
                    "is_final_process": 1 if int(_to_number(row.get("is_final_process"), 0)) == 1 else 0,
                }
            )

        out: dict[str, dict[str, str]] = {}
        for product_code, route_rows in rows_by_product.items():
            ordered_rows = sorted(route_rows, key=lambda item: int(item["sequence_no"]))
            marked_rows = [row for row in ordered_rows if int(row.get("is_final_process") or 0) == 1]
            if len(marked_rows) > 1:
                raise server_error(
                    code="ROUTE_FINAL_PROCESS_DUPLICATED",
                    message="Route has more than one final process step.",
                    details={"product_code": product_code},
                )
            target_row = marked_rows[0] if marked_rows else ordered_rows[-1]
            process_code = str(target_row.get("process_code") or "").strip().upper()
            if not process_code:
                continue
            out[product_code] = {
                "process_code": process_code,
                "process_name_cn": str(target_row.get("process_name_cn") or process_code).strip() or process_code,
            }
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
                product_name_cn,
                COALESCE(is_final_process, 0) AS is_final_process
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
        return self._apply_default_final_process_flags(out)

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

