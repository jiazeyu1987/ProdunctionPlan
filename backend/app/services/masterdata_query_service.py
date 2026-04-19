from __future__ import annotations

from typing import Any

from ..json_utils import loads
from ..repositories.backups import BackupRepository
from .masterdata_support import (
    list_enabled_workshop_manager_users,
    list_line_skeleton_rows,
    list_workshop_manager_line_scope_rows,
    list_workshop_manager_visibility_rows,
)


class MasterdataQueryService:
    def __init__(self, host: Any) -> None:
        self.host = host
        self.line_daily_capacity_service = host.line_daily_capacity_service

    def get_masterdata_config(self) -> dict[str, Any]:
        self.host._ensure_masterdata_seeded()
        rules = self.get_schedule_calendar_rules()["data"]
        line_skeletons = list_line_skeleton_rows(self.host.connection)
        line_topology = self.host._list_line_topology_rows()
        workshop_manager_users = list_enabled_workshop_manager_users(self.host.connection)
        workshop_manager_visible_by_user_id = {
            str(row.get("user_id") or "").strip(): (
                1 if int(row.get("visible_flag") or 0) == 1 else 0
            )
            for row in list_workshop_manager_visibility_rows(self.host.connection)
            if str(row.get("user_id") or "").strip()
        }
        workshop_manager_users = [
            {
                **row,
                "visible_flag": workshop_manager_visible_by_user_id.get(
                    str(row.get("user_id") or "").strip(),
                    1,
                ),
            }
            for row in workshop_manager_users
        ]
        workshop_manager_line_scopes = list_workshop_manager_line_scope_rows(
            self.host.connection
        )
        route_rows = self.host._list_route_rows()
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
        backup_repository = BackupRepository(self.host.connection)
        backup_config = backup_repository.get_backup_config()
        backup_records = backup_repository.list_backup_records()
        return {
            "data": {
                "horizon_start_date": rules["horizon_start_date"],
                "horizon_days": rules["horizon_days"],
                "skip_statutory_holidays": rules["skip_statutory_holidays"],
                "weekend_rest_mode": rules["weekend_rest_mode"],
                "date_shift_mode_by_date": rules["date_shift_mode_by_date"],
                "process_configs": process_configs,
                "line_skeletons": line_skeletons,
                "line_topology": line_topology,
                "workshop_manager_users": workshop_manager_users,
                "workshop_manager_line_scopes": workshop_manager_line_scopes,
                "resource_pool": [],
                "material_availability": [],
                "backup_config": backup_config,
                "backup_records": backup_records,
            }
        }

    def get_schedule_calendar_rules(self) -> dict[str, Any]:
        row = self.host._get_rules_row()
        simulation_state = self.host._get_simulation_state()
        return {
            "data": {
                "horizon_start_date": row["horizon_start_date"],
                "horizon_days": row["horizon_days"],
                "skip_statutory_holidays": bool(row["skip_statutory_holidays"]),
                "weekend_rest_mode": row["weekend_rest_mode"],
                "date_shift_mode_by_date": loads(row["date_shift_mode_by_date_json"]) or {},
                "current_date": simulation_state["current_date"],
            }
        }

    def list_process_routes(self) -> dict[str, Any]:
        self.host._ensure_masterdata_seeded()
        return {"items": self.host._list_route_rows()}

    def list_line_daily_capacity(
        self,
        calendar_date: str,
        *,
        workshop_code: str | None = None,
        line_code: str | None = None,
        process_code: str | None = None,
        current_user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.line_daily_capacity_service.list_line_daily_capacity(
            calendar_date,
            workshop_code=workshop_code,
            line_code=line_code,
            process_code=process_code,
            current_user=current_user,
        )

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
        return self.line_daily_capacity_service.list_line_daily_capacity_audits(
            calendar_date,
            workshop_code=workshop_code,
            line_code=line_code,
            process_code=process_code,
            operator_keyword=operator_keyword,
            changed_only=changed_only,
            current_user=current_user,
        )
