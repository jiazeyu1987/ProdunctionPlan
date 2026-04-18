from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import sqlite3
from typing import Any
from uuid import uuid4

from ..db import fetch_all, fetch_one, transaction, utc_now
from ..errors import bad_request, forbidden, server_error


DEFAULT_COMPANY_CODE = "COMPANY-MAIN"
ROLE_WORKSHOP_MANAGER = "WORKSHOP_MANAGER"
SHIFT_SEQUENCE = ("DAY", "NIGHT")
SHIFT_SPLIT_RULES = {"DAY_ONLY", "NIGHT_ONLY", "DAY_NIGHT_EQUAL", "CUSTOM"}
SHIFT_CHANGE_TYPES = {"worker_count changed", "machine_count changed", "shift unavailable"}


def _normalize_date_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _normalize_shift_code(value: object) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"DAY", "D"}:
        return "DAY"
    if normalized in {"NIGHT", "N"}:
        return "NIGHT"
    raise bad_request(
        code="SHIFT_CODE_INVALID",
        message="shift_code must be DAY or NIGHT.",
        details={"shift_code": value},
    )


def _to_number(value: object, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def _derive_shift_code_from_report_time(report_time_text: str) -> str | None:
    try:
        local_time = datetime.fromisoformat(report_time_text).astimezone(timezone(timedelta(hours=8)))
    except ValueError:
        return None
    return "NIGHT" if local_time.hour >= 20 or local_time.hour < 8 else "DAY"


class LineDailyCapacityService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_line_daily_capacity(
        self,
        calendar_date: str,
        *,
        workshop_code: str | None = None,
        line_code: str | None = None,
        process_code: str | None = None,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_date = _normalize_date_text(calendar_date)
        if normalized_date is None:
            raise bad_request(code="CALENDAR_DATE_REQUIRED", message="calendar_date must be a valid YYYY-MM-DD date.")
        previous_date = (date.fromisoformat(normalized_date) - timedelta(days=1)).isoformat()
        topology_rows = self._list_topology_rows(
            workshop_code=workshop_code,
            line_code=line_code,
            process_code=process_code,
            current_user=current_user,
        )
        today_plan_map = self._list_capacity_plan_map(normalized_date)
        previous_plan_map = self._list_capacity_plan_map(previous_date)
        actual_map = self._list_capacity_actual_map(normalized_date)
        items: list[dict[str, Any]] = []
        for topology_row in topology_rows:
            for shift_code in SHIFT_SEQUENCE:
                items.append(
                    self._build_capacity_item(
                        topology_row=topology_row,
                        shift_code=shift_code,
                        calendar_date=normalized_date,
                        previous_date=previous_date,
                        plan_row=today_plan_map.get(self._capacity_key(normalized_date, shift_code, topology_row)),
                        previous_plan_row=previous_plan_map.get(self._capacity_key(previous_date, shift_code, topology_row)),
                        actual_row=actual_map.get(self._capacity_key(normalized_date, shift_code, topology_row)),
                    )
                )
        return {"calendar_date": normalized_date, "items": items}

    def save_line_daily_capacity(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_date = _normalize_date_text(payload.get("calendar_date"))
        if normalized_date is None:
            raise bad_request(code="CALENDAR_DATE_REQUIRED", message="calendar_date must be a valid YYYY-MM-DD date.")
        items = payload.get("items")
        if not isinstance(items, list) or len(items) == 0:
            raise bad_request(code="DAILY_CAPACITY_ITEMS_REQUIRED", message="items must be a non-empty array.")
        actor = payload.get("actor") if isinstance(payload.get("actor"), dict) else {}
        updated_at = utc_now()
        rows: list[tuple[Any, ...]] = []
        audit_rows: list[tuple[Any, ...]] = []
        normalized_items: list[dict[str, Any]] = []
        for item in items:
            if str(item.get("shift_code") or "").strip():
                normalized_items.append(item)
            else:
                normalized_items.extend(self._expand_daily_capacity_item(item))
        for item in normalized_items:
            prepared = self._prepare_capacity_save_item(normalized_date, item, actor, updated_at)
            rows.append(prepared["row"])
            audit_row = prepared.get("audit_row")
            if audit_row is not None:
                audit_rows.append(audit_row)
        with transaction(self.connection):
            self.connection.executemany(
                """
                INSERT INTO daily_line_capacity_plan (
                    calendar_date, shift_code, company_code, workshop_code, line_code, process_code,
                    planned_capacity_qty, worker_count, machine_count, split_rule, split_day_ratio, split_night_ratio,
                    capacity_change_type, capacity_change_reason, source_note, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(calendar_date, shift_code, company_code, workshop_code, line_code, process_code)
                DO UPDATE SET
                    planned_capacity_qty = excluded.planned_capacity_qty,
                    worker_count = excluded.worker_count,
                    machine_count = excluded.machine_count,
                    split_rule = excluded.split_rule,
                    split_day_ratio = excluded.split_day_ratio,
                    split_night_ratio = excluded.split_night_ratio,
                    capacity_change_type = excluded.capacity_change_type,
                    capacity_change_reason = excluded.capacity_change_reason,
                    source_note = excluded.source_note,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
            if audit_rows:
                self.connection.executemany(
                    """
                    INSERT INTO daily_line_capacity_plan_audit (
                        audit_id, calendar_date, shift_code, company_code, workshop_code, line_code, process_code,
                        old_planned_capacity_qty, new_planned_capacity_qty, old_worker_count, new_worker_count,
                        old_machine_count, new_machine_count, capacity_change_type, capacity_change_reason,
                        operator_user_id, operator_username, operator_display_name, changed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    audit_rows,
                )
        return self.list_line_daily_capacity(normalized_date, current_user=actor)

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
        normalized_date = _normalize_date_text(calendar_date)
        if normalized_date is None:
            raise bad_request(code="CALENDAR_DATE_REQUIRED", message="calendar_date must be a valid YYYY-MM-DD date.")
        filters = ["calendar_date = ?"]
        parameters: list[Any] = [normalized_date]
        if workshop_code:
            filters.append("workshop_code = ?")
            parameters.append(str(workshop_code).strip().upper())
        if line_code:
            filters.append("line_code = ?")
            parameters.append(str(line_code).strip().upper())
        if process_code:
            filters.append("process_code = ?")
            parameters.append(str(process_code).strip().upper())
        if operator_keyword:
            keyword = f"%{str(operator_keyword).strip()}%"
            filters.append("(COALESCE(operator_display_name, '') LIKE ? OR COALESCE(operator_username, '') LIKE ?)")
            parameters.extend([keyword, keyword])
        if changed_only:
            filters.append(
                "(COALESCE(old_planned_capacity_qty, 0) <> COALESCE(new_planned_capacity_qty, 0)"
                " OR COALESCE(old_worker_count, 0) <> COALESCE(new_worker_count, 0)"
                " OR COALESCE(old_machine_count, 0) <> COALESCE(new_machine_count, 0)"
                " OR COALESCE(capacity_change_type, '') <> ''"
                " OR COALESCE(capacity_change_reason, '') <> '')"
            )
        manager_user_id = self._resolve_manager_user_id(current_user)
        if manager_user_id is not None:
            filters.append(
                "EXISTS (SELECT 1 FROM app_user_line_scopes scope WHERE scope.user_id = ?"
                " AND scope.company_code = daily_line_capacity_plan_audit.company_code"
                " AND scope.workshop_code = daily_line_capacity_plan_audit.workshop_code"
                " AND scope.line_code = daily_line_capacity_plan_audit.line_code)"
            )
            parameters.append(manager_user_id)
        rows = fetch_all(
            self.connection,
            f"""
            SELECT audit_id, calendar_date, shift_code, company_code, workshop_code, line_code, process_code,
                   old_planned_capacity_qty, new_planned_capacity_qty, old_worker_count, new_worker_count,
                   old_machine_count, new_machine_count, capacity_change_type, capacity_change_reason,
                   operator_user_id, operator_username, operator_display_name, changed_at
            FROM daily_line_capacity_plan_audit
            WHERE {' AND '.join(filters)}
            ORDER BY changed_at DESC, audit_id DESC
            """,
            tuple(parameters),
        )
        return {"calendar_date": normalized_date, "items": [self._with_audit_deltas(row) for row in rows]}

    def rebuild_line_daily_actual_capacity(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_date = _normalize_date_text(payload.get("calendar_date"))
        if normalized_date is None:
            raise bad_request(code="CALENDAR_DATE_REQUIRED", message="calendar_date must be a valid YYYY-MM-DD date.")
        with transaction(self.connection):
            updated_row_count, skipped_report_count = self._rebuild_line_daily_actual_capacity_rows(normalized_date)
        return {
            "calendar_date": normalized_date,
            "updated_row_count": updated_row_count,
            "skipped_report_count": skipped_report_count,
            "items": self.list_line_daily_capacity(normalized_date)["items"],
        }

    def _list_topology_rows(
        self,
        *,
        workshop_code: str | None,
        line_code: str | None,
        process_code: str | None,
        current_user: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        parameters: list[Any] = []
        if workshop_code:
            filters.append("lt.workshop_code = ?")
            parameters.append(str(workshop_code).strip().upper())
        if line_code:
            filters.append("lt.line_code = ?")
            parameters.append(str(line_code).strip().upper())
        if process_code:
            filters.append("lt.process_code = ?")
            parameters.append(str(process_code).strip().upper())
        manager_user_id = self._resolve_manager_user_id(current_user)
        if manager_user_id is not None:
            filters.append(
                "EXISTS (SELECT 1 FROM app_user_line_scopes scope WHERE scope.user_id = ?"
                " AND scope.company_code = lt.company_code"
                " AND scope.workshop_code = lt.workshop_code"
                " AND scope.line_code = lt.line_code)"
            )
            parameters.append(manager_user_id)
        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        return fetch_all(
            self.connection,
            f"""
            SELECT lt.company_code, COALESCE(lt.workshop_name, lt.workshop_code) AS workshop_name,
                   lt.workshop_code, COALESCE(lt.line_name, lt.line_code) AS line_name, lt.line_code,
                   lt.process_code, lt.capacity_per_shift AS default_capacity_qty,
                   lt.required_workers, lt.required_machines
            FROM masterdata_line_topology lt
            {where_sql}
            ORDER BY lt.workshop_code ASC, lt.line_code ASC, lt.process_code ASC
            """,
            tuple(parameters),
        )

    def _list_capacity_plan_map(self, calendar_date: str) -> dict[tuple[str, ...], dict[str, Any]]:
        rows = fetch_all(
            self.connection,
            """
            SELECT calendar_date, shift_code, company_code, workshop_code, line_code, process_code,
                   planned_capacity_qty, worker_count, machine_count, split_rule, split_day_ratio, split_night_ratio,
                   capacity_change_type, capacity_change_reason, source_note, updated_at
            FROM daily_line_capacity_plan
            WHERE calendar_date = ?
            """,
            (calendar_date,),
        )
        return {self._capacity_key(row.get("calendar_date"), row.get("shift_code"), row): row for row in rows}

    def _list_capacity_actual_map(self, calendar_date: str) -> dict[tuple[str, ...], dict[str, Any]]:
        rows = fetch_all(
            self.connection,
            """
            SELECT calendar_date, shift_code, company_code, workshop_code, line_code, process_code,
                   actual_capacity_qty, report_count, last_report_time, updated_at
            FROM daily_line_capacity_actual
            WHERE calendar_date = ?
            """,
            (calendar_date,),
        )
        return {self._capacity_key(row.get("calendar_date"), row.get("shift_code"), row): row for row in rows}

    def _capacity_key(
        self,
        calendar_date: object,
        shift_code: object,
        row: dict[str, Any],
    ) -> tuple[str, str, str, str, str, str]:
        return (
            str(calendar_date or "").strip(),
            str(shift_code or "").strip().upper(),
            str(row.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper() or DEFAULT_COMPANY_CODE,
            str(row.get("workshop_code") or "").strip().upper(),
            str(row.get("line_code") or "").strip().upper(),
            str(row.get("process_code") or "").strip().upper(),
        )

    def _build_capacity_item(
        self,
        *,
        topology_row: dict[str, Any],
        shift_code: str,
        calendar_date: str,
        previous_date: str,
        plan_row: dict[str, Any] | None,
        previous_plan_row: dict[str, Any] | None,
        actual_row: dict[str, Any] | None,
    ) -> dict[str, Any]:
        default_capacity_qty = _to_number(topology_row.get("default_capacity_qty"), 0)
        required_workers = int(_to_number(topology_row.get("required_workers"), 0))
        required_machines = int(_to_number(topology_row.get("required_machines"), 0))
        source_row = plan_row or previous_plan_row or {}
        worker_count = int(_to_number(source_row.get("worker_count"), required_workers))
        machine_count = int(_to_number(source_row.get("machine_count"), required_machines))
        seeded_from_date = None if plan_row is not None else (previous_date if previous_plan_row is not None else None)
        capacity_driver, planned_capacity_qty = self._resolve_planned_capacity(
            default_capacity_qty=default_capacity_qty,
            required_workers=required_workers,
            required_machines=required_machines,
            worker_count=worker_count,
            machine_count=machine_count,
            error_factory=server_error,
            details={
                "workshop_code": topology_row.get("workshop_code"),
                "line_code": topology_row.get("line_code"),
                "process_code": topology_row.get("process_code"),
                "shift_code": shift_code,
            },
        )
        capacity_change_type = self._resolve_capacity_change_type(
            source_row.get("capacity_change_type"),
            worker_count=worker_count,
            machine_count=machine_count,
            required_workers=required_workers,
            required_machines=required_machines,
            planned_capacity_qty=planned_capacity_qty,
        )
        return {
            "calendar_date": calendar_date,
            "shift_code": shift_code,
            "company_code": topology_row.get("company_code"),
            "workshop_code": topology_row.get("workshop_code"),
            "workshop_name": topology_row.get("workshop_name"),
            "line_code": topology_row.get("line_code"),
            "line_name": topology_row.get("line_name"),
            "process_code": topology_row.get("process_code"),
            "default_capacity_qty": default_capacity_qty,
            "planned_capacity_qty": planned_capacity_qty,
            "worker_count": worker_count,
            "machine_count": machine_count,
            "required_workers": required_workers,
            "required_machines": required_machines,
            "capacity_driver": capacity_driver,
            "seeded_from_date": seeded_from_date,
            "split_rule": str(source_row.get("split_rule") or self._default_split_rule_for_shift(shift_code)),
            "split_day_ratio": source_row.get("split_day_ratio"),
            "split_night_ratio": source_row.get("split_night_ratio"),
            "capacity_change_type": capacity_change_type,
            "capacity_change_reason": str(source_row.get("capacity_change_reason") or "").strip() or None,
            "source_note": source_row.get("source_note"),
            "actual_capacity_qty": _to_number((actual_row or {}).get("actual_capacity_qty"), 0),
            "report_count": int(_to_number((actual_row or {}).get("report_count"), 0)),
            "last_report_time": (actual_row or {}).get("last_report_time"),
        }

    def _prepare_capacity_save_item(
        self,
        normalized_date: str,
        item: dict[str, Any],
        actor: dict[str, Any],
        updated_at: str,
    ) -> dict[str, Any]:
        company_code = str(item.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper() or DEFAULT_COMPANY_CODE
        workshop_code = str(item.get("workshop_code") or "").strip().upper()
        line_code = str(item.get("line_code") or "").strip().upper()
        process_code = str(item.get("process_code") or "").strip().upper()
        shift_code = _normalize_shift_code(item.get("shift_code"))
        worker_count = int(_to_number(item.get("worker_count"), -1))
        machine_count = int(_to_number(item.get("machine_count"), -1))
        if not workshop_code or not line_code or not process_code:
            raise bad_request(code="DAILY_CAPACITY_KEY_REQUIRED", message="workshop_code, line_code and process_code are required.")
        if worker_count < 0 or machine_count < 0:
            raise bad_request(code="DAILY_CAPACITY_COUNT_INVALID", message="worker_count and machine_count must be >= 0.")
        self._assert_actor_can_access_line(
            actor,
            company_code=company_code,
            workshop_code=workshop_code,
            line_code=line_code,
            missing_user_error_code="DAILY_CAPACITY_ACTOR_USER_REQUIRED",
            forbidden_error_code="DAILY_CAPACITY_LINE_SCOPE_FORBIDDEN",
            forbidden_message="Current workshop manager is not allowed to modify this shift capacity row.",
        )
        topology_row = fetch_one(
            self.connection,
            """
            SELECT capacity_per_shift, required_workers, required_machines
            FROM masterdata_line_topology
            WHERE company_code = ? AND workshop_code = ? AND line_code = ? AND process_code = ?
            LIMIT 1
            """,
            (company_code, workshop_code, line_code, process_code),
        )
        if topology_row is None:
            raise bad_request(code="DAILY_CAPACITY_TOPOLOGY_MISSING", message="The target line/process does not exist in masterdata_line_topology.")
        default_capacity_qty = _to_number(topology_row.get("capacity_per_shift"), 0)
        required_workers = int(_to_number(topology_row.get("required_workers"), 0))
        required_machines = int(_to_number(topology_row.get("required_machines"), 0))
        manual_planned_capacity_qty = item.get("manual_planned_capacity_qty")
        if manual_planned_capacity_qty is None:
            _, planned_capacity_qty = self._resolve_planned_capacity(
                default_capacity_qty=default_capacity_qty,
                required_workers=required_workers,
                required_machines=required_machines,
                worker_count=worker_count,
                machine_count=machine_count,
                error_factory=bad_request,
                details={"shift_code": shift_code, "workshop_code": workshop_code, "line_code": line_code, "process_code": process_code},
            )
        else:
            planned_capacity_qty = round(_to_number(manual_planned_capacity_qty, -1))
            if planned_capacity_qty < 0:
                raise bad_request(code="DAILY_CAPACITY_PLANNED_QTY_INVALID", message="manual_planned_capacity_qty must be >= 0.")
        split_rule = self._normalize_split_rule(item.get("split_rule"), shift_code=shift_code)
        split_day_ratio, split_night_ratio = self._resolve_split_ratios(
            split_rule=split_rule,
            day_ratio=item.get("split_day_ratio"),
            night_ratio=item.get("split_night_ratio"),
        )
        capacity_change_type = self._resolve_capacity_change_type(
            item.get("capacity_change_type"),
            worker_count=worker_count,
            machine_count=machine_count,
            required_workers=required_workers,
            required_machines=required_machines,
            planned_capacity_qty=planned_capacity_qty,
        )
        capacity_change_reason = str(item.get("capacity_change_reason") or "").strip() or None
        existing_row = fetch_one(
            self.connection,
            """
            SELECT planned_capacity_qty, worker_count, machine_count, capacity_change_type, capacity_change_reason
            FROM daily_line_capacity_plan
            WHERE calendar_date = ? AND shift_code = ? AND company_code = ? AND workshop_code = ? AND line_code = ? AND process_code = ?
            LIMIT 1
            """,
            (normalized_date, shift_code, company_code, workshop_code, line_code, process_code),
        )
        row = (
            normalized_date,
            shift_code,
            company_code,
            workshop_code,
            line_code,
            process_code,
            planned_capacity_qty,
            worker_count,
            machine_count,
            split_rule,
            split_day_ratio,
            split_night_ratio,
            capacity_change_type,
            capacity_change_reason,
            str(item.get("source_note") or "").strip() or None,
            updated_at,
        )
        values_changed = (
            existing_row is None
            or _to_number(existing_row.get("planned_capacity_qty"), 0) != planned_capacity_qty
            or int(_to_number(existing_row.get("worker_count"), 0)) != worker_count
            or int(_to_number(existing_row.get("machine_count"), 0)) != machine_count
            or str(existing_row.get("capacity_change_type") or "").strip() != str(capacity_change_type or "")
            or str(existing_row.get("capacity_change_reason") or "").strip() != str(capacity_change_reason or "")
        )
        audit_row = None
        if values_changed:
            audit_row = (
                f"DLC-AUD-{uuid4().hex[:16].upper()}",
                normalized_date,
                shift_code,
                company_code,
                workshop_code,
                line_code,
                process_code,
                _to_number(existing_row.get("planned_capacity_qty"), 0) if existing_row else None,
                planned_capacity_qty,
                int(_to_number(existing_row.get("worker_count"), 0)) if existing_row else None,
                worker_count,
                int(_to_number(existing_row.get("machine_count"), 0)) if existing_row else None,
                machine_count,
                capacity_change_type,
                capacity_change_reason,
                str(actor.get("user_id") or "").strip() or None,
                str(actor.get("username") or "").strip() or None,
                str(actor.get("display_name") or "").strip() or None,
                updated_at,
            )
        return {"row": row, "audit_row": audit_row}

    def _expand_daily_capacity_item(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        split_rule = self._normalize_split_rule(item.get("split_rule"), shift_code="DAY")
        day_ratio, night_ratio = self._resolve_split_ratios(
            split_rule=split_rule,
            day_ratio=item.get("split_day_ratio"),
            night_ratio=item.get("split_night_ratio"),
        )
        planned_capacity_qty = _to_number(
            item.get("planned_capacity_qty", item.get("daily_capacity_qty")),
            -1,
        )
        if planned_capacity_qty < 0:
            raise bad_request(
                code="DAILY_CAPACITY_DAILY_TOTAL_REQUIRED",
                message="planned_capacity_qty or daily_capacity_qty is required when shift_code is omitted.",
            )
        worker_count = max(0, int(_to_number(item.get("worker_count"), 0)))
        machine_count = max(0, int(_to_number(item.get("machine_count"), 0)))
        day_planned_capacity_qty = round(planned_capacity_qty * day_ratio)
        night_planned_capacity_qty = round(planned_capacity_qty - day_planned_capacity_qty)
        day_worker_count = round(worker_count * day_ratio) if worker_count > 0 else (1 if day_planned_capacity_qty > 0 else 0)
        night_worker_count = round(worker_count - day_worker_count) if worker_count > 0 else (1 if night_planned_capacity_qty > 0 else 0)
        day_machine_count = round(machine_count * day_ratio) if machine_count > 0 else (1 if day_planned_capacity_qty > 0 else 0)
        night_machine_count = round(machine_count - day_machine_count) if machine_count > 0 else (1 if night_planned_capacity_qty > 0 else 0)
        return [
            {
                **item,
                "shift_code": "DAY",
                "split_rule": split_rule,
                "split_day_ratio": day_ratio,
                "split_night_ratio": night_ratio,
                "worker_count": max(0, day_worker_count),
                "machine_count": max(0, day_machine_count),
                "manual_planned_capacity_qty": max(0, day_planned_capacity_qty),
            },
            {
                **item,
                "shift_code": "NIGHT",
                "split_rule": split_rule,
                "split_day_ratio": day_ratio,
                "split_night_ratio": night_ratio,
                "worker_count": max(0, night_worker_count),
                "machine_count": max(0, night_machine_count),
                "manual_planned_capacity_qty": max(0, night_planned_capacity_qty),
            },
        ]

    def _normalize_split_rule(self, value: object, *, shift_code: str) -> str:
        normalized = str(value or "").strip().upper()
        if normalized:
            if normalized not in SHIFT_SPLIT_RULES:
                raise bad_request(code="DAILY_CAPACITY_SPLIT_RULE_INVALID", message="split_rule is invalid.")
            return normalized
        return self._default_split_rule_for_shift(shift_code)

    def _default_split_rule_for_shift(self, shift_code: str) -> str:
        return "DAY_ONLY" if shift_code == "DAY" else "NIGHT_ONLY"

    def _resolve_split_ratios(self, *, split_rule: str, day_ratio: object, night_ratio: object) -> tuple[float, float]:
        if split_rule == "DAY_ONLY":
            return 1.0, 0.0
        if split_rule == "NIGHT_ONLY":
            return 0.0, 1.0
        if split_rule == "DAY_NIGHT_EQUAL":
            return 0.5, 0.5
        resolved_day_ratio = _to_number(day_ratio, -1)
        resolved_night_ratio = _to_number(night_ratio, -1)
        if resolved_day_ratio < 0 or resolved_night_ratio < 0 or resolved_day_ratio + resolved_night_ratio <= 0:
            raise bad_request(code="DAILY_CAPACITY_CUSTOM_RATIO_INVALID", message="CUSTOM split ratios are invalid.")
        total = resolved_day_ratio + resolved_night_ratio
        return resolved_day_ratio / total, resolved_night_ratio / total

    def _resolve_capacity_change_type(
        self,
        value: object,
        *,
        worker_count: int,
        machine_count: int,
        required_workers: int,
        required_machines: int,
        planned_capacity_qty: int,
    ) -> str | None:
        normalized = str(value or "").strip()
        if normalized:
            if normalized not in SHIFT_CHANGE_TYPES:
                raise bad_request(code="DAILY_CAPACITY_CHANGE_TYPE_INVALID", message="capacity_change_type is invalid.")
            return normalized
        if planned_capacity_qty <= 0 or (worker_count <= 0 and machine_count <= 0):
            return "shift unavailable"
        if required_machines > 0 and machine_count != required_machines:
            return "machine_count changed"
        if worker_count != required_workers:
            return "worker_count changed"
        return None

    def _resolve_planned_capacity(
        self,
        *,
        default_capacity_qty: float,
        required_workers: int,
        required_machines: int,
        worker_count: int,
        machine_count: int,
        error_factory: Any,
        details: dict[str, Any],
    ) -> tuple[str, int]:
        if required_machines > 0:
            if required_machines <= 0:
                raise error_factory(code="DAILY_CAPACITY_REQUIRED_MACHINES_INVALID", message="required_machines must be > 0.", details=details)
            return "MACHINE", round(default_capacity_qty * machine_count / required_machines)
        if required_workers <= 0:
            raise error_factory(code="DAILY_CAPACITY_REQUIRED_WORKERS_INVALID", message="required_workers must be > 0.", details=details)
        return "WORKER", round(default_capacity_qty * worker_count / required_workers)

    def _with_audit_deltas(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            **row,
            "planned_capacity_delta": None
            if row.get("old_planned_capacity_qty") is None or row.get("new_planned_capacity_qty") is None
            else _to_number(row.get("new_planned_capacity_qty"), 0) - _to_number(row.get("old_planned_capacity_qty"), 0),
            "worker_count_delta": None
            if row.get("old_worker_count") is None or row.get("new_worker_count") is None
            else int(_to_number(row.get("new_worker_count"), 0) - _to_number(row.get("old_worker_count"), 0)),
            "machine_count_delta": None
            if row.get("old_machine_count") is None or row.get("new_machine_count") is None
            else int(_to_number(row.get("new_machine_count"), 0) - _to_number(row.get("old_machine_count"), 0)),
        }

    def _rebuild_line_daily_actual_capacity_rows(self, normalized_date: str) -> tuple[int, int]:
        report_rows = fetch_all(
            self.connection,
            "SELECT report_id, process_code, workshop_code, line_code, report_qty, report_time FROM work_reports",
        )
        local_timezone = timezone(timedelta(hours=8))
        aggregated: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        skipped_report_count = 0
        for row in report_rows:
            process_code = str(row.get("process_code") or "").strip().upper()
            workshop_code = str(row.get("workshop_code") or "").strip().upper()
            line_code = str(row.get("line_code") or "").strip().upper()
            report_time_text = str(row.get("report_time") or "").strip()
            if not process_code or not workshop_code or not line_code or not report_time_text:
                skipped_report_count += 1
                continue
            try:
                local_date = datetime.fromisoformat(report_time_text).astimezone(local_timezone).date().isoformat()
            except ValueError:
                skipped_report_count += 1
                continue
            if local_date != normalized_date:
                continue
            shift_code = _derive_shift_code_from_report_time(report_time_text)
            if shift_code is None:
                skipped_report_count += 1
                continue
            topology_row = fetch_one(
                self.connection,
                "SELECT company_code FROM masterdata_line_topology WHERE workshop_code = ? AND line_code = ? AND process_code = ? LIMIT 1",
                (workshop_code, line_code, process_code),
            )
            if topology_row is None:
                skipped_report_count += 1
                continue
            company_code = str(topology_row.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper() or DEFAULT_COMPANY_CODE
            key = (company_code, workshop_code, line_code, process_code, shift_code)
            current = aggregated.get(key) or {"actual_capacity_qty": 0.0, "report_count": 0, "last_report_time": report_time_text}
            current["actual_capacity_qty"] += _to_number(row.get("report_qty"), 0)
            current["report_count"] += 1
            if report_time_text > str(current["last_report_time"] or ""):
                current["last_report_time"] = report_time_text
            aggregated[key] = current
        updated_at = utc_now()
        self.connection.execute("DELETE FROM daily_line_capacity_actual WHERE calendar_date = ?", (normalized_date,))
        if aggregated:
            self.connection.executemany(
                """
                INSERT INTO daily_line_capacity_actual (
                    calendar_date, shift_code, company_code, workshop_code, line_code, process_code,
                    actual_capacity_qty, report_count, last_report_time, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        normalized_date,
                        shift_code,
                        company_code,
                        workshop_code,
                        line_code,
                        process_code,
                        values["actual_capacity_qty"],
                        values["report_count"],
                        values["last_report_time"],
                        updated_at,
                    )
                    for (company_code, workshop_code, line_code, process_code, shift_code), values in aggregated.items()
                ],
            )
        return len(aggregated), skipped_report_count

    def _is_workshop_manager(self, user: dict[str, Any] | None) -> bool:
        return str((user or {}).get("role_code") or "").strip().upper() == ROLE_WORKSHOP_MANAGER

    def _resolve_manager_user_id(self, user: dict[str, Any] | None) -> str | None:
        if not self._is_workshop_manager(user):
            return None
        user_id = str((user or {}).get("user_id") or "").strip()
        if not user_id:
            raise forbidden(code="WORKSHOP_MANAGER_USER_ID_REQUIRED", message="Current workshop manager user_id is missing.")
        return user_id

    def _list_user_line_scope_rows(self, user_id: str) -> list[dict[str, Any]]:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            return []
        return fetch_all(
            self.connection,
            "SELECT user_id, company_code, workshop_code, line_code FROM app_user_line_scopes WHERE user_id = ?",
            (normalized_user_id,),
        )

    def _assert_actor_can_access_line(
        self,
        actor: dict[str, Any],
        *,
        company_code: str,
        workshop_code: str,
        line_code: str,
        missing_user_error_code: str,
        forbidden_error_code: str,
        forbidden_message: str,
    ) -> None:
        if not self._is_workshop_manager(actor):
            return
        user_id = str(actor.get("user_id") or "").strip()
        if not user_id:
            raise forbidden(code=missing_user_error_code, message="Current workshop manager user_id is missing.")
        allowed = any(
            str(row.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper() == company_code
            and str(row.get("workshop_code") or "").strip().upper() == workshop_code
            and str(row.get("line_code") or "").strip().upper() == line_code
            for row in self._list_user_line_scope_rows(user_id)
        )
        if not allowed:
            raise forbidden(code=forbidden_error_code, message=forbidden_message)
