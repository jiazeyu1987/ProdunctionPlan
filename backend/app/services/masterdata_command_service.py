from __future__ import annotations

from typing import Any

from ..db import fetch_one, transaction, utc_now
from ..errors import bad_request
from ..repositories.backups import BackupRepository
from ..json_utils import dumps, loads
from .masterdata_support import list_enabled_workshop_manager_users


RULES_SINGLETON_KEY = "default"
DEFAULT_COMPANY_CODE = "COMPANY-MAIN"


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


def _today_text() -> str:
    from datetime import date

    return date.today().isoformat()


class MasterdataCommandService:
    def __init__(self, host: Any) -> None:
        self.host = host
        self.connection = host.connection

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

    def save_masterdata_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        line_skeletons = payload.get("line_skeletons")
        if not isinstance(line_skeletons, list) or len(line_skeletons) == 0:
            raise bad_request(
                code="LINE_SKELETONS_REQUIRED",
                message="line_skeletons must be a non-empty array.",
            )
        line_topology = payload.get("line_topology")
        if line_topology is None:
            line_topology = []
        if not isinstance(line_topology, list):
            raise bad_request(
                code="LINE_TOPOLOGY_REQUIRED",
                message="line_topology must be an array.",
            )
        workshop_manager_line_scopes = payload.get("workshop_manager_line_scopes")
        if not isinstance(workshop_manager_line_scopes, list):
            raise bad_request(
                code="WORKSHOP_MANAGER_LINE_SCOPES_REQUIRED",
                message="workshop_manager_line_scopes must be an array.",
            )
        workshop_manager_users_payload = payload.get("workshop_manager_users")
        if not isinstance(workshop_manager_users_payload, list):
            raise bad_request(
                code="WORKSHOP_MANAGER_USERS_REQUIRED",
                message="workshop_manager_users must be an array.",
            )
        workshop_manager_users = list_enabled_workshop_manager_users(self.connection)
        workshop_manager_user_ids = {
            str(row.get("user_id") or "").strip()
            for row in workshop_manager_users
            if str(row.get("user_id") or "").strip()
        }
        updated_at = utc_now()
        backup_config_payload = payload.get("backup_config")
        backup_config_update: tuple[int, int, int] | None = None
        if backup_config_payload is not None:
            if not isinstance(backup_config_payload, dict):
                raise bad_request(
                    code="BACKUP_CONFIG_INVALID",
                    message="backup_config must be an object.",
                )
            try:
                enabled_flag = _parse_enabled_flag(backup_config_payload.get("enabled_flag"))
            except ValueError as exc:
                raise bad_request(
                    code="BACKUP_CONFIG_ENABLED_FLAG_INVALID",
                    message=str(exc),
                )
            try:
                frequency_minutes = _parse_int_in_range(
                    backup_config_payload.get("frequency_minutes"),
                    field_name="frequency_minutes",
                    min_value=1,
                    max_value=525600,
                )
            except ValueError as exc:
                raise bad_request(
                    code="BACKUP_CONFIG_FREQUENCY_INVALID",
                    message=str(exc),
                )
            try:
                max_backups = _parse_int_in_range(
                    backup_config_payload.get("max_backups"),
                    field_name="max_backups",
                    min_value=1,
                    max_value=1000,
                )
            except ValueError as exc:
                raise bad_request(
                    code="BACKUP_CONFIG_MAX_BACKUPS_INVALID",
                    message=str(exc),
                )
            backup_config_update = (enabled_flag, frequency_minutes, max_backups)

        payload_workshop_manager_user_ids: set[str] = set()
        workshop_manager_visibility_rows: list[tuple[Any, ...]] = []
        for item in workshop_manager_users_payload:
            user_id = str(item.get("user_id") or "").strip()
            if not user_id:
                raise bad_request(
                    code="WORKSHOP_MANAGER_USER_ROW_INVALID",
                    message="workshop_manager_users row must include user_id.",
                )
            if user_id not in workshop_manager_user_ids:
                raise bad_request(
                    code="WORKSHOP_MANAGER_USER_INVALID",
                    message="workshop_manager_users contains unknown or disabled workshop manager user.",
                    details={"user_id": user_id},
                )
            if user_id in payload_workshop_manager_user_ids:
                raise bad_request(
                    code="WORKSHOP_MANAGER_USER_DUPLICATE",
                    message="workshop_manager_users contains duplicate rows.",
                    details={"user_id": user_id},
                )
            payload_workshop_manager_user_ids.add(user_id)
            workshop_manager_visibility_rows.append(
                (user_id, 1 if int(item.get("visible_flag") or 0) == 1 else 0, updated_at)
            )
        if payload_workshop_manager_user_ids != workshop_manager_user_ids:
            raise bad_request(
                code="WORKSHOP_MANAGER_USERS_MISMATCH",
                message="workshop_manager_users must include every enabled workshop manager exactly once.",
                details={
                    "missing_user_ids": sorted(workshop_manager_user_ids - payload_workshop_manager_user_ids),
                    "extra_user_ids": sorted(payload_workshop_manager_user_ids - workshop_manager_user_ids),
                },
            )

        skeleton_rows: list[tuple[Any, ...]] = []
        skeleton_map: dict[tuple[str, str, str], dict[str, Any]] = {}
        for item in line_skeletons:
            company_code = str(item.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper() or DEFAULT_COMPANY_CODE
            workshop_code = str(item.get("workshop_code") or "").strip().upper()
            line_code = str(item.get("line_code") or "").strip().upper()
            if not workshop_code or not line_code:
                raise bad_request(
                    code="LINE_SKELETON_ROW_INVALID",
                    message="workshop_code and line_code are required in line_skeletons.",
                )
            key = (company_code, workshop_code, line_code)
            if key in skeleton_map:
                raise bad_request(
                    code="LINE_SKELETON_DUPLICATE",
                    message="line_skeletons contains duplicate workshop/line rows.",
                    details={
                        "company_code": company_code,
                        "workshop_code": workshop_code,
                        "line_code": line_code,
                    },
                )
            skeleton_row = {
                "company_code": company_code,
                "workshop_code": workshop_code,
                "workshop_name": str(item.get("workshop_name") or workshop_code).strip() or workshop_code,
                "line_code": line_code,
                "line_name": str(item.get("line_name") or line_code).strip() or line_code,
                "enabled_flag": 1 if int(item.get("enabled_flag") or 0) == 1 else 0,
            }
            skeleton_map[key] = skeleton_row
            skeleton_rows.append(
                (
                    company_code,
                    skeleton_row["workshop_code"],
                    skeleton_row["workshop_name"],
                    skeleton_row["line_code"],
                    skeleton_row["line_name"],
                    skeleton_row["enabled_flag"],
                    updated_at,
                )
            )

        rows = []
        for item in line_topology:
            company_code = str(item.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper() or DEFAULT_COMPANY_CODE
            workshop_code = str(item.get("workshop_code") or "").strip().upper()
            line_code = str(item.get("line_code") or "").strip().upper()
            process_code = str(item.get("process_code") or "").strip().upper()
            if not workshop_code or not line_code or not process_code:
                raise bad_request(
                    code="LINE_TOPOLOGY_ROW_INVALID",
                    message="workshop_code, line_code and process_code are required.",
                )
            skeleton_row = skeleton_map.get((company_code, workshop_code, line_code))
            if skeleton_row is None:
                raise bad_request(
                    code="LINE_TOPOLOGY_SKELETON_MISSING",
                    message="line_topology row must reference an existing line_skeleton.",
                    details={
                        "company_code": company_code,
                        "workshop_code": workshop_code,
                        "line_code": line_code,
                        "process_code": process_code,
                    },
                )
            capacity_per_shift = _to_number(item.get("capacity_per_shift"), 0)
            required_workers = int(_to_number(item.get("required_workers"), 0))
            required_machines = int(_to_number(item.get("required_machines"), 0))
            if capacity_per_shift <= 0 or required_workers <= 0 or required_machines < 0:
                raise bad_request(
                    code="LINE_TOPOLOGY_CAPACITY_INVALID",
                    message="capacity_per_shift and required_workers must be greater than 0, required_machines must be >= 0.",
                    details={
                        "company_code": company_code,
                        "workshop_code": workshop_code,
                        "line_code": line_code,
                        "process_code": process_code,
                    },
                )
            rows.append(
                (
                    company_code,
                    workshop_code,
                    skeleton_row["workshop_name"],
                    line_code,
                    skeleton_row["line_name"],
                    process_code,
                    capacity_per_shift,
                    required_workers,
                    required_machines,
                    int(item.get("enabled_flag") or 0),
                    updated_at,
                )
            )

        scope_rows: list[tuple[Any, ...]] = []
        scope_seen: set[tuple[str, str, str, str]] = set()
        for item in workshop_manager_line_scopes:
            user_id = str(item.get("user_id") or "").strip()
            company_code = str(item.get("company_code") or DEFAULT_COMPANY_CODE).strip().upper() or DEFAULT_COMPANY_CODE
            workshop_code = str(item.get("workshop_code") or "").strip().upper()
            line_code = str(item.get("line_code") or "").strip().upper()
            if not user_id or not workshop_code or not line_code:
                raise bad_request(
                    code="WORKSHOP_MANAGER_LINE_SCOPE_ROW_INVALID",
                    message="user_id, workshop_code and line_code are required in workshop_manager_line_scopes.",
                )
            if user_id not in workshop_manager_user_ids:
                raise bad_request(
                    code="WORKSHOP_MANAGER_USER_INVALID",
                    message="workshop_manager_line_scopes contains unknown or disabled workshop manager user.",
                    details={"user_id": user_id},
                )
            scope_key = (user_id, company_code, workshop_code, line_code)
            if scope_key in scope_seen:
                raise bad_request(
                    code="WORKSHOP_MANAGER_LINE_SCOPE_DUPLICATE",
                    message="workshop_manager_line_scopes contains duplicate rows.",
                    details={
                        "user_id": user_id,
                        "company_code": company_code,
                        "workshop_code": workshop_code,
                        "line_code": line_code,
                    },
                )
            scope_seen.add(scope_key)
            if (company_code, workshop_code, line_code) not in skeleton_map:
                raise bad_request(
                    code="WORKSHOP_MANAGER_LINE_SCOPE_SKELETON_MISSING",
                    message="workshop_manager_line_scopes row must reference an existing line_skeleton.",
                    details={
                        "user_id": user_id,
                        "company_code": company_code,
                        "workshop_code": workshop_code,
                        "line_code": line_code,
                    },
                )
            scope_rows.append((user_id, company_code, workshop_code, line_code, updated_at))

        with transaction(self.connection):
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
                skeleton_rows,
            )
            self.connection.execute("DELETE FROM masterdata_line_topology")
            if rows:
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
            self.connection.execute("DELETE FROM app_user_line_scopes")
            if scope_rows:
                self.connection.executemany(
                    """
                    INSERT INTO app_user_line_scopes (
                        user_id,
                        company_code,
                        workshop_code,
                        line_code,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    scope_rows,
                )
            self.connection.execute("DELETE FROM masterdata_workshop_manager_visibility")
            if workshop_manager_visibility_rows:
                self.connection.executemany(
                    """
                    INSERT INTO masterdata_workshop_manager_visibility (
                        user_id,
                        visible_flag,
                        updated_at
                    ) VALUES (?, ?, ?)
                    """,
                    workshop_manager_visibility_rows,
                )
            if backup_config_update is not None:
                enabled_flag, frequency_minutes, max_backups = backup_config_update
                BackupRepository(self.connection).upsert_backup_config(
                    enabled_flag=enabled_flag,
                    frequency_minutes=frequency_minutes,
                    max_backups=max_backups,
                    updated_at=updated_at,
                )
        return self.host.get_masterdata_config()

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

    def save_schedule_calendar_rules(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.host._get_rules_row()
        weekend_rest_mode = self.host._normalize_weekend_rest_mode(
            payload.get("weekend_rest_mode")
            if "weekend_rest_mode" in payload
            else current["weekend_rest_mode"]
        )
        date_shift_mode_by_date = self.host._normalize_date_shift_mode_by_date(
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
        return self.host.get_schedule_calendar_rules()

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
        process_name_by_code = self.host._process_name_by_code()
        updated_at = utc_now()
        rows_to_insert: list[dict[str, Any]] = []
        marked_final_count = 0
        for index, step in enumerate(normalized_steps):
            process_code = str(step.get("process_code") or "").strip().upper()
            if not process_code:
                raise bad_request(
                    code="ROUTE_STEP_INVALID",
                    message="Each route step requires process_code.",
                )
            dependency_type = str(step.get("dependency_type") or "FS").strip().upper() or "FS"
            raw_final_process_flag = step.get("is_final_process")
            if raw_final_process_flag is None:
                is_final_process = 0
            elif isinstance(raw_final_process_flag, bool):
                is_final_process = 1 if raw_final_process_flag else 0
            else:
                normalized_final_process_flag = str(raw_final_process_flag).strip().lower()
                if normalized_final_process_flag in {"1", "true"}:
                    is_final_process = 1
                elif normalized_final_process_flag in {"0", "false", ""}:
                    is_final_process = 0
                else:
                    raise bad_request(
                        code="ROUTE_STEP_INVALID",
                        message="is_final_process must be 0 or 1.",
                    )
            if is_final_process == 1:
                marked_final_count += 1
            rows_to_insert.append(
                {
                    "product_code": product_code,
                    "sequence_no": index + 1,
                    "process_code": process_code,
                    "process_name_cn": process_name_by_code.get(process_code, process_code),
                    "dependency_type": dependency_type,
                    "route_no": f"ROUTE-{product_code}",
                    "route_name_cn": product_name,
                    "product_name_cn": product_name,
                    "is_final_process": is_final_process,
                    "updated_at": updated_at,
                }
            )
        if marked_final_count > 1:
            raise bad_request(
                code="ROUTE_FINAL_PROCESS_INVALID",
                message="Only one step can be marked as final process.",
            )
        if marked_final_count == 0 and rows_to_insert:
            rows_to_insert[-1]["is_final_process"] = 1
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
                        row["is_final_process"],
                        row["updated_at"],
                    )
                    for row in rows_to_insert
                ],
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
