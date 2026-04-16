from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import sqlite3
from typing import Any
from uuid import uuid4

from ..db import fetch_all, fetch_one, transaction, utc_now
from ..errors import bad_request, forbidden, server_error


DEFAULT_COMPANY_CODE = "COMPANY-MAIN"
ROLE_WORKSHOP_MANAGER = "WORKSHOP_MANAGER"


def _normalize_date_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _to_number(value: object, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


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
            raise bad_request(
                code="CALENDAR_DATE_REQUIRED",
                message="calendar_date must be a valid YYYY-MM-DD date.",
            )
        previous_date = (date.fromisoformat(normalized_date) - timedelta(days=1)).isoformat()
        filters: list[str] = []
        filter_parameters: list[Any] = []
        if workshop_code:
            filters.append("lt.workshop_code = ?")
            filter_parameters.append(str(workshop_code).strip().upper())
        if line_code:
            filters.append("lt.line_code = ?")
            filter_parameters.append(str(line_code).strip().upper())
        if process_code:
            filters.append("lt.process_code = ?")
            filter_parameters.append(str(process_code).strip().upper())
        manager_user_id = self._resolve_manager_user_id(current_user)
        if manager_user_id is not None:
            filters.append(
                """
                EXISTS (
                    SELECT 1
                    FROM app_user_line_scopes scope
                    WHERE scope.user_id = ?
                      AND scope.company_code = lt.company_code
                      AND scope.workshop_code = lt.workshop_code
                      AND scope.line_code = lt.line_code
                )
                """
            )
            filter_parameters.append(manager_user_id)
        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        rows = fetch_all(
            self.connection,
            f"""
            SELECT
                ? AS calendar_date,
                lt.company_code,
                COALESCE(lt.workshop_name, lt.workshop_code) AS workshop_name,
                lt.workshop_code,
                COALESCE(lt.line_name, lt.line_code) AS line_name,
                lt.line_code,
                lt.process_code,
                lt.capacity_per_shift AS default_capacity_qty,
                lt.required_workers,
                lt.required_machines,
                plan.planned_capacity_qty AS today_planned_capacity_qty,
                plan.worker_count AS today_worker_count,
                plan.machine_count AS today_machine_count,
                plan.source_note AS today_source_note,
                prev_plan.planned_capacity_qty AS prev_planned_capacity_qty,
                prev_plan.worker_count AS prev_worker_count,
                prev_plan.machine_count AS prev_machine_count,
                actual.actual_capacity_qty,
                actual.report_count,
                actual.last_report_time,
                COALESCE(prev_report.previous_day_report_qty, 0) AS previous_day_report_qty
            FROM masterdata_line_topology lt
            LEFT JOIN daily_line_capacity_plan plan
              ON plan.calendar_date = ?
             AND plan.company_code = lt.company_code
             AND plan.workshop_code = lt.workshop_code
             AND plan.line_code = lt.line_code
             AND plan.process_code = lt.process_code
            LEFT JOIN daily_line_capacity_plan prev_plan
              ON prev_plan.calendar_date = ?
             AND prev_plan.company_code = lt.company_code
             AND prev_plan.workshop_code = lt.workshop_code
             AND prev_plan.line_code = lt.line_code
             AND prev_plan.process_code = lt.process_code
            LEFT JOIN daily_line_capacity_actual actual
              ON actual.calendar_date = ?
             AND actual.company_code = lt.company_code
             AND actual.workshop_code = lt.workshop_code
             AND actual.line_code = lt.line_code
             AND actual.process_code = lt.process_code
            LEFT JOIN (
                SELECT
                    COALESCE(top.company_code, ?) AS company_code,
                    UPPER(TRIM(COALESCE(reports.workshop_code, ''))) AS workshop_code,
                    UPPER(TRIM(COALESCE(reports.line_code, ''))) AS line_code,
                    UPPER(TRIM(COALESCE(reports.process_code, ''))) AS process_code,
                    SUM(COALESCE(reports.report_qty, 0)) AS previous_day_report_qty
                FROM work_reports reports
                LEFT JOIN masterdata_line_topology top
                  ON top.workshop_code = UPPER(TRIM(COALESCE(reports.workshop_code, '')))
                 AND top.line_code = UPPER(TRIM(COALESCE(reports.line_code, '')))
                 AND top.process_code = UPPER(TRIM(COALESCE(reports.process_code, '')))
                WHERE date(reports.report_time, '+8 hours') = ?
                GROUP BY
                    COALESCE(top.company_code, ?),
                    UPPER(TRIM(COALESCE(reports.workshop_code, ''))),
                    UPPER(TRIM(COALESCE(reports.line_code, ''))),
                    UPPER(TRIM(COALESCE(reports.process_code, '')))
            ) prev_report
              ON prev_report.company_code = lt.company_code
             AND prev_report.workshop_code = lt.workshop_code
             AND prev_report.line_code = lt.line_code
             AND prev_report.process_code = lt.process_code
            {where_sql}
            ORDER BY lt.workshop_code ASC, lt.line_code ASC, lt.process_code ASC
            """,
            tuple(
                [
                    normalized_date,
                    normalized_date,
                    previous_date,
                    normalized_date,
                    DEFAULT_COMPANY_CODE,
                    previous_date,
                    DEFAULT_COMPANY_CODE,
                    *filter_parameters,
                ]
            ),
        )
        return {
            "calendar_date": normalized_date,
            "items": [
                self._build_capacity_item(
                    row,
                    calendar_date=normalized_date,
                    previous_date=previous_date,
                )
                for row in rows
            ],
        }

    def save_line_daily_capacity(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_date = _normalize_date_text(payload.get("calendar_date"))
        if normalized_date is None:
            raise bad_request(
                code="CALENDAR_DATE_REQUIRED",
                message="calendar_date must be a valid YYYY-MM-DD date.",
            )
        items = payload.get("items")
        if not isinstance(items, list) or len(items) == 0:
            raise bad_request(
                code="DAILY_CAPACITY_ITEMS_REQUIRED",
                message="items must be a non-empty array.",
            )
        updated_at = utc_now()
        actor = payload.get("actor") if isinstance(payload.get("actor"), dict) else {}
        rows: list[tuple[Any, ...]] = []
        audit_rows: list[tuple[Any, ...]] = []
        for item in items:
            company_code = (
                str(item.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper()
                or DEFAULT_COMPANY_CODE
            )
            workshop_code = str(item.get("workshop_code") or "").strip().upper()
            line_code = str(item.get("line_code") or "").strip().upper()
            process_code = str(item.get("process_code") or "").strip().upper()
            worker_count = int(_to_number(item.get("worker_count"), -1))
            machine_count = int(_to_number(item.get("machine_count"), -1))
            if not workshop_code or not line_code or not process_code:
                raise bad_request(
                    code="DAILY_CAPACITY_KEY_REQUIRED",
                    message="workshop_code, line_code and process_code are required.",
                )
            if worker_count < 0 or machine_count < 0:
                raise bad_request(
                    code="DAILY_CAPACITY_COUNT_INVALID",
                    message="worker_count and machine_count must be >= 0.",
                )
            self._assert_actor_can_access_line(
                actor,
                company_code=company_code,
                workshop_code=workshop_code,
                line_code=line_code,
                missing_user_error_code="DAILY_CAPACITY_ACTOR_USER_REQUIRED",
                forbidden_error_code="DAILY_CAPACITY_LINE_SCOPE_FORBIDDEN",
                forbidden_message="Current workshop manager is not allowed to modify this line capacity row.",
            )
            topology_row = fetch_one(
                self.connection,
                """
                SELECT capacity_per_shift, required_workers, required_machines
                FROM masterdata_line_topology
                WHERE company_code = ?
                  AND workshop_code = ?
                  AND line_code = ?
                  AND process_code = ?
                LIMIT 1
                """,
                (company_code, workshop_code, line_code, process_code),
            )
            if topology_row is None:
                raise bad_request(
                    code="DAILY_CAPACITY_TOPOLOGY_MISSING",
                    message="The target line/process does not exist in masterdata_line_topology.",
                    details={
                        "company_code": company_code,
                        "workshop_code": workshop_code,
                        "line_code": line_code,
                        "process_code": process_code,
                    },
                )
            default_capacity_qty = _to_number(topology_row.get("capacity_per_shift"), 0)
            required_workers = int(_to_number(topology_row.get("required_workers"), 0))
            required_machines = int(_to_number(topology_row.get("required_machines"), 0))
            _, planned_capacity_qty = self._resolve_planned_capacity(
                default_capacity_qty=default_capacity_qty,
                required_workers=required_workers,
                required_machines=required_machines,
                worker_count=worker_count,
                machine_count=machine_count,
                error_factory=bad_request,
                details={
                    "company_code": company_code,
                    "workshop_code": workshop_code,
                    "line_code": line_code,
                    "process_code": process_code,
                    "required_workers": required_workers,
                    "required_machines": required_machines,
                },
            )
            existing_row = fetch_one(
                self.connection,
                """
                SELECT planned_capacity_qty, worker_count, machine_count
                FROM daily_line_capacity_plan
                WHERE calendar_date = ?
                  AND company_code = ?
                  AND workshop_code = ?
                  AND line_code = ?
                  AND process_code = ?
                LIMIT 1
                """,
                (
                    normalized_date,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                ),
            )
            old_planned_capacity_qty = (
                _to_number(existing_row.get("planned_capacity_qty"), 0)
                if existing_row is not None
                else None
            )
            old_worker_count = (
                int(_to_number(existing_row.get("worker_count"), 0))
                if existing_row is not None
                else None
            )
            old_machine_count = (
                int(_to_number(existing_row.get("machine_count"), 0))
                if existing_row is not None
                else None
            )
            values_changed = (
                existing_row is None
                or old_planned_capacity_qty != planned_capacity_qty
                or old_worker_count != worker_count
                or old_machine_count != machine_count
            )
            rows.append(
                (
                    normalized_date,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    planned_capacity_qty,
                    worker_count,
                    machine_count,
                    str(item.get("source_note") or "").strip() or None,
                    updated_at,
                )
            )
            if values_changed:
                audit_rows.append(
                    (
                        f"DLC-AUD-{uuid4().hex[:16].upper()}",
                        normalized_date,
                        company_code,
                        workshop_code,
                        line_code,
                        process_code,
                        old_planned_capacity_qty,
                        planned_capacity_qty,
                        old_worker_count,
                        worker_count,
                        old_machine_count,
                        machine_count,
                        str(actor.get("user_id") or "").strip() or None,
                        str(actor.get("username") or "").strip() or None,
                        str(actor.get("display_name") or "").strip() or None,
                        updated_at,
                    )
                )
        with transaction(self.connection):
            self.connection.executemany(
                """
                INSERT INTO daily_line_capacity_plan (
                    calendar_date,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    planned_capacity_qty,
                    worker_count,
                    machine_count,
                    source_note,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(calendar_date, company_code, workshop_code, line_code, process_code)
                DO UPDATE SET
                    planned_capacity_qty = excluded.planned_capacity_qty,
                    worker_count = excluded.worker_count,
                    machine_count = excluded.machine_count,
                    source_note = excluded.source_note,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
            if audit_rows:
                self.connection.executemany(
                    """
                    INSERT INTO daily_line_capacity_plan_audit (
                        audit_id,
                        calendar_date,
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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            raise bad_request(
                code="CALENDAR_DATE_REQUIRED",
                message="calendar_date must be a valid YYYY-MM-DD date.",
            )
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
            filters.append(
                "(COALESCE(operator_display_name, '') LIKE ? OR COALESCE(operator_username, '') LIKE ?)"
            )
            parameters.extend([keyword, keyword])
        if changed_only:
            filters.append(
                """
                (
                    COALESCE(old_planned_capacity_qty, 0) <> COALESCE(new_planned_capacity_qty, 0)
                    OR COALESCE(old_worker_count, 0) <> COALESCE(new_worker_count, 0)
                    OR COALESCE(old_machine_count, 0) <> COALESCE(new_machine_count, 0)
                )
                """
            )
        manager_user_id = self._resolve_manager_user_id(current_user)
        if manager_user_id is not None:
            filters.append(
                """
                EXISTS (
                    SELECT 1
                    FROM app_user_line_scopes scope
                    WHERE scope.user_id = ?
                      AND scope.company_code = daily_line_capacity_plan_audit.company_code
                      AND scope.workshop_code = daily_line_capacity_plan_audit.workshop_code
                      AND scope.line_code = daily_line_capacity_plan_audit.line_code
                )
                """
            )
            parameters.append(manager_user_id)
        where_sql = " AND ".join(filters)
        rows = fetch_all(
            self.connection,
            f"""
            SELECT
                audit_id,
                calendar_date,
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
            WHERE {where_sql}
            ORDER BY changed_at DESC, audit_id DESC
            """,
            tuple(parameters),
        )
        return {
            "calendar_date": normalized_date,
            "items": [
                {
                    **row,
                    "planned_capacity_delta": (
                        None
                        if row.get("old_planned_capacity_qty") is None
                        or row.get("new_planned_capacity_qty") is None
                        else _to_number(row.get("new_planned_capacity_qty"), 0)
                        - _to_number(row.get("old_planned_capacity_qty"), 0)
                    ),
                    "worker_count_delta": (
                        None
                        if row.get("old_worker_count") is None
                        or row.get("new_worker_count") is None
                        else int(
                            _to_number(row.get("new_worker_count"), 0)
                            - _to_number(row.get("old_worker_count"), 0)
                        )
                    ),
                    "machine_count_delta": (
                        None
                        if row.get("old_machine_count") is None
                        or row.get("new_machine_count") is None
                        else int(
                            _to_number(row.get("new_machine_count"), 0)
                            - _to_number(row.get("old_machine_count"), 0)
                        )
                    ),
                }
                for row in rows
            ],
        }

    def rebuild_line_daily_actual_capacity(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_date = _normalize_date_text(payload.get("calendar_date"))
        if normalized_date is None:
            raise bad_request(
                code="CALENDAR_DATE_REQUIRED",
                message="calendar_date must be a valid YYYY-MM-DD date.",
            )
        with transaction(self.connection):
            updated_row_count, skipped_report_count = self._rebuild_line_daily_actual_capacity_rows(
                normalized_date
            )
        return {
            "calendar_date": normalized_date,
            "updated_row_count": updated_row_count,
            "skipped_report_count": skipped_report_count,
            "items": self.list_line_daily_capacity(normalized_date)["items"],
        }

    def _build_capacity_item(
        self,
        row: dict[str, Any],
        *,
        calendar_date: str,
        previous_date: str,
    ) -> dict[str, Any]:
        default_capacity_qty = _to_number(row.get("default_capacity_qty"), 0)
        required_workers = int(_to_number(row.get("required_workers"), 0))
        required_machines = int(_to_number(row.get("required_machines"), 0))
        has_today_plan = row.get("today_planned_capacity_qty") is not None
        if has_today_plan:
            worker_count = int(_to_number(row.get("today_worker_count"), 0))
            machine_count = int(_to_number(row.get("today_machine_count"), 0))
            seeded_from_date = None
        elif row.get("prev_planned_capacity_qty") is not None:
            worker_count = int(_to_number(row.get("prev_worker_count"), 0))
            machine_count = int(_to_number(row.get("prev_machine_count"), 0))
            seeded_from_date = previous_date
        else:
            worker_count = required_workers
            machine_count = required_machines
            seeded_from_date = None
        if worker_count < 0 or machine_count < 0:
            raise server_error(
                code="DAILY_CAPACITY_COUNT_INVALID",
                message="worker_count and machine_count must be >= 0.",
                details={
                    "workshop_code": row.get("workshop_code"),
                    "line_code": row.get("line_code"),
                    "process_code": row.get("process_code"),
                    "worker_count": worker_count,
                    "machine_count": machine_count,
                },
            )
        capacity_driver, planned_capacity_qty = self._resolve_planned_capacity(
            default_capacity_qty=default_capacity_qty,
            required_workers=required_workers,
            required_machines=required_machines,
            worker_count=worker_count,
            machine_count=machine_count,
            error_factory=server_error,
            details={
                "workshop_code": row.get("workshop_code"),
                "line_code": row.get("line_code"),
                "process_code": row.get("process_code"),
                "required_workers": required_workers,
                "required_machines": required_machines,
            },
        )
        return {
            "calendar_date": calendar_date,
            "company_code": row.get("company_code"),
            "workshop_code": row.get("workshop_code"),
            "workshop_name": row.get("workshop_name"),
            "line_code": row.get("line_code"),
            "line_name": row.get("line_name"),
            "process_code": row.get("process_code"),
            "default_capacity_qty": default_capacity_qty,
            "planned_capacity_qty": planned_capacity_qty,
            "worker_count": worker_count,
            "machine_count": machine_count,
            "required_workers": required_workers,
            "required_machines": required_machines,
            "capacity_driver": capacity_driver,
            "seeded_from_date": seeded_from_date,
            "source_note": row.get("today_source_note"),
            "actual_capacity_qty": _to_number(row.get("actual_capacity_qty"), 0),
            "report_count": int(_to_number(row.get("report_count"), 0)),
            "last_report_time": row.get("last_report_time"),
            "previous_day_report_qty": round(_to_number(row.get("previous_day_report_qty"), 0)),
        }

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
        capacity_driver = "MACHINE" if required_machines > 0 else "WORKER"
        if capacity_driver == "MACHINE":
            planned_capacity_qty = round(default_capacity_qty * machine_count / required_machines)
            return capacity_driver, planned_capacity_qty
        if required_workers <= 0:
            raise error_factory(
                code="DAILY_CAPACITY_REQUIRED_WORKERS_INVALID",
                message="required_workers must be > 0 for worker-driven process.",
                details=details,
            )
        planned_capacity_qty = round(default_capacity_qty * worker_count / required_workers)
        return capacity_driver, planned_capacity_qty

    def _rebuild_line_daily_actual_capacity_rows(
        self,
        normalized_date: str,
    ) -> tuple[int, int]:
        report_rows = fetch_all(
            self.connection,
            """
            SELECT report_id, process_code, workshop_code, line_code, report_qty, report_time
            FROM work_reports
            """,
        )
        local_timezone = timezone(timedelta(hours=8))
        aggregated: dict[tuple[str, str, str, str], dict[str, Any]] = {}
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
                local_date = (
                    datetime.fromisoformat(report_time_text)
                    .astimezone(local_timezone)
                    .date()
                    .isoformat()
                )
            except ValueError:
                skipped_report_count += 1
                continue
            if local_date != normalized_date:
                continue
            topology_row = fetch_one(
                self.connection,
                """
                SELECT company_code
                FROM masterdata_line_topology
                WHERE workshop_code = ?
                  AND line_code = ?
                  AND process_code = ?
                LIMIT 1
                """,
                (workshop_code, line_code, process_code),
            )
            if topology_row is None:
                skipped_report_count += 1
                continue
            company_code = (
                str(topology_row.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper()
                or DEFAULT_COMPANY_CODE
            )
            key = (company_code, workshop_code, line_code, process_code)
            current = aggregated.get(key) or {
                "actual_capacity_qty": 0.0,
                "report_count": 0,
                "last_report_time": report_time_text,
            }
            current["actual_capacity_qty"] += _to_number(row.get("report_qty"), 0)
            current["report_count"] += 1
            if report_time_text > str(current["last_report_time"] or ""):
                current["last_report_time"] = report_time_text
            aggregated[key] = current
        updated_at = utc_now()
        self.connection.execute(
            "DELETE FROM daily_line_capacity_actual WHERE calendar_date = ?",
            (normalized_date,),
        )
        if aggregated:
            self.connection.executemany(
                """
                INSERT INTO daily_line_capacity_actual (
                    calendar_date,
                    company_code,
                    workshop_code,
                    line_code,
                    process_code,
                    actual_capacity_qty,
                    report_count,
                    last_report_time,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        normalized_date,
                        company_code,
                        workshop_code,
                        line_code,
                        process_code,
                        values["actual_capacity_qty"],
                        values["report_count"],
                        values["last_report_time"],
                        updated_at,
                    )
                    for (company_code, workshop_code, line_code, process_code), values in aggregated.items()
                ],
            )
        return len(aggregated), skipped_report_count

    def _is_workshop_manager(self, user: dict[str, Any] | None) -> bool:
        role_code = str((user or {}).get("role_code") or "").strip().upper()
        return role_code == ROLE_WORKSHOP_MANAGER

    def _resolve_manager_user_id(self, user: dict[str, Any] | None) -> str | None:
        if not self._is_workshop_manager(user):
            return None
        user_id = str((user or {}).get("user_id") or "").strip()
        if not user_id:
            raise forbidden(
                code="WORKSHOP_MANAGER_USER_ID_REQUIRED",
                message="Current workshop manager user_id is missing.",
            )
        return user_id

    def _list_user_line_scope_rows(self, user_id: str) -> list[dict[str, Any]]:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            return []
        return fetch_all(
            self.connection,
            """
            SELECT
                user_id,
                company_code,
                workshop_code,
                line_code
            FROM app_user_line_scopes
            WHERE user_id = ?
            """,
            (normalized_user_id,),
        )

    def _build_line_scope_key(
        self,
        *,
        company_code: str | None,
        workshop_code: str | None,
        line_code: str | None,
    ) -> tuple[str, str, str]:
        return (
            str(company_code or DEFAULT_COMPANY_CODE).strip().upper() or DEFAULT_COMPANY_CODE,
            str(workshop_code or "").strip().upper(),
            str(line_code or "").strip().upper(),
        )

    def _user_line_scope_key_set(self, user_id: str) -> set[tuple[str, str, str]]:
        rows = self._list_user_line_scope_rows(user_id)
        return {
            self._build_line_scope_key(
                company_code=row.get("company_code"),
                workshop_code=row.get("workshop_code"),
                line_code=row.get("line_code"),
            )
            for row in rows
        }

    def _assert_actor_can_access_line(
        self,
        actor: dict[str, Any] | None,
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
        actor_user_id = str((actor or {}).get("user_id") or "").strip()
        if not actor_user_id:
            raise bad_request(
                code=missing_user_error_code,
                message="workshop manager actor.user_id is required.",
            )
        scope_key = self._build_line_scope_key(
            company_code=company_code,
            workshop_code=workshop_code,
            line_code=line_code,
        )
        allowed_scope_keys = self._user_line_scope_key_set(actor_user_id)
        if scope_key not in allowed_scope_keys:
            raise forbidden(
                code=forbidden_error_code,
                message=forbidden_message,
                details={
                    "user_id": actor_user_id,
                    "company_code": scope_key[0],
                    "workshop_code": scope_key[1],
                    "line_code": scope_key[2],
                },
            )
