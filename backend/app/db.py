from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .config import BACKEND_ROOT, get_settings
from .errors import server_error


_schema_ready = False
_schema_lock = Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_database_exists() -> Path:
    database_path = get_settings().database_path
    if not database_path.exists():
        raise server_error(
            code="SQLITE_DATABASE_MISSING",
            message=(
                f"SQLite database does not exist: {database_path}. "
                "Run backend/scripts/init_db.py first."
            ),
        )
    return database_path


def _configure_connection(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")


def _mark_schema_ready() -> None:
    global _schema_ready
    _schema_ready = True


def prepare_database() -> Path:
    database_path = ensure_database_exists()
    global _schema_ready
    if _schema_ready:
        return database_path

    with _schema_lock:
        if _schema_ready:
            return database_path

        connection = sqlite3.connect(database_path, check_same_thread=False)
        try:
            _configure_connection(connection)
            migrate_database_schema(connection)
            connection.commit()
        finally:
            connection.close()

        _mark_schema_ready()
    return database_path


def open_connection() -> sqlite3.Connection:
    database_path = prepare_database()
    connection = sqlite3.connect(database_path, check_same_thread=False)
    _configure_connection(connection)
    return connection


def get_db() -> Iterator[sqlite3.Connection]:
    connection = open_connection()
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def managed_connection() -> Iterator[sqlite3.Connection]:
    connection = open_connection()
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN")
    try:
        yield
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


def fetch_all(
    connection: sqlite3.Connection,
    sql: str,
    parameters: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    rows = connection.execute(sql, parameters).fetchall()
    return [dict(row) for row in rows]


def fetch_one(
    connection: sqlite3.Connection,
    sql: str,
    parameters: tuple[Any, ...] = (),
) -> dict[str, Any] | None:
    row = connection.execute(sql, parameters).fetchone()
    return dict(row) if row else None


def load_init_sql() -> str:
    sql_path = BACKEND_ROOT / "sqlite" / "001_init.sql"
    return sql_path.read_text(encoding="utf-8")


def initialize_database(database_path: Path | None = None) -> Path:
    target_path = database_path or get_settings().database_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target_path)
    try:
        connection.executescript(load_init_sql())
        _configure_connection(connection)
        migrate_database_schema(connection)
        connection.commit()
    finally:
        connection.close()
    if target_path.resolve() == get_settings().database_path.resolve():
        _mark_schema_ready()
    return target_path


def _table_info(connection: sqlite3.Connection, table_name: str) -> list[sqlite3.Row]:
    return connection.execute(f"PRAGMA table_info({table_name})").fetchall()


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = _table_info(connection, table_name)
    return {str(row[1]) for row in rows}


def migrate_database_schema(connection: sqlite3.Connection) -> None:
    order_pool_columns = _table_columns(connection, "order_pool_state")
    if "priority_level" not in order_pool_columns:
        connection.execute(
            """
            ALTER TABLE order_pool_state
            ADD COLUMN priority_level INTEGER NOT NULL DEFAULT 5
            """
        )
    connection.execute(
        """
        UPDATE order_pool_state
        SET priority_level = CASE
            WHEN COALESCE(urgent_flag, 0) = 1 THEN 1
            ELSE 5
        END
        WHERE priority_level IS NULL OR priority_level < 1 OR priority_level > 5
        """
    )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            role_code TEXT NOT NULL,
            enabled_flag INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_app_users_role
            ON app_users (role_code, enabled_flag);
        CREATE TABLE IF NOT EXISTS masterdata_workshop_manager_visibility (
            user_id TEXT PRIMARY KEY,
            visible_flag INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES app_users(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_masterdata_workshop_manager_visibility_flag
            ON masterdata_workshop_manager_visibility (visible_flag);
        CREATE TABLE IF NOT EXISTS app_sessions (
            session_token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            FOREIGN KEY (user_id) REFERENCES app_users(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_app_sessions_user
            ON app_sessions (user_id, revoked_at, expires_at);
        CREATE TABLE IF NOT EXISTS daily_line_capacity_plan (
            calendar_date TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            process_code TEXT NOT NULL,
            planned_capacity_qty REAL NOT NULL,
            worker_count INTEGER,
            machine_count INTEGER,
            source_note TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (calendar_date, company_code, workshop_code, line_code, process_code)
        );
        CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_plan_date
            ON daily_line_capacity_plan (calendar_date, workshop_code, line_code, process_code);
        CREATE TABLE IF NOT EXISTS daily_line_capacity_actual (
            calendar_date TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            process_code TEXT NOT NULL,
            actual_capacity_qty REAL NOT NULL,
            report_count INTEGER NOT NULL DEFAULT 0,
            last_report_time TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (calendar_date, company_code, workshop_code, line_code, process_code)
        );
        CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_actual_date
            ON daily_line_capacity_actual (calendar_date, workshop_code, line_code, process_code);
        CREATE TABLE IF NOT EXISTS daily_line_capacity_plan_audit (
            audit_id TEXT PRIMARY KEY,
            calendar_date TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            process_code TEXT NOT NULL,
            old_planned_capacity_qty REAL,
            new_planned_capacity_qty REAL,
            old_worker_count INTEGER,
            new_worker_count INTEGER,
            old_machine_count INTEGER,
            new_machine_count INTEGER,
            operator_user_id TEXT,
            operator_username TEXT,
            operator_display_name TEXT,
            changed_at TEXT NOT NULL,
            FOREIGN KEY (operator_user_id) REFERENCES app_users(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_plan_audit_date
            ON daily_line_capacity_plan_audit (calendar_date, changed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_plan_audit_line
            ON daily_line_capacity_plan_audit (workshop_code, line_code, process_code, changed_at DESC);
        CREATE TABLE IF NOT EXISTS simulation_restore_snapshot_meta (
            singleton_key TEXT PRIMARY KEY,
            snapshot_current_date TEXT NOT NULL,
            snapshot_created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS simulation_restore_snapshot_daily_line_capacity_plan (
            calendar_date TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            process_code TEXT NOT NULL,
            planned_capacity_qty REAL NOT NULL,
            worker_count INTEGER,
            machine_count INTEGER,
            source_note TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (calendar_date, company_code, workshop_code, line_code, process_code)
        );
        CREATE TABLE IF NOT EXISTS simulation_restore_snapshot_daily_line_capacity_actual (
            calendar_date TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            process_code TEXT NOT NULL,
            actual_capacity_qty REAL NOT NULL,
            report_count INTEGER NOT NULL DEFAULT 0,
            last_report_time TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (calendar_date, company_code, workshop_code, line_code, process_code)
        );
        CREATE TABLE IF NOT EXISTS simulation_restore_snapshot_daily_line_capacity_plan_audit (
            audit_id TEXT PRIMARY KEY,
            calendar_date TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            process_code TEXT NOT NULL,
            old_planned_capacity_qty REAL,
            new_planned_capacity_qty REAL,
            old_worker_count INTEGER,
            new_worker_count INTEGER,
            old_machine_count INTEGER,
            new_machine_count INTEGER,
            operator_user_id TEXT,
            operator_username TEXT,
            operator_display_name TEXT,
            changed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS simulation_restore_snapshot_work_reports (
            report_id TEXT PRIMARY KEY,
            production_order_no TEXT,
            process_code TEXT,
            process_name TEXT,
            workshop_code TEXT,
            workshop_name TEXT,
            line_code TEXT,
            line_name TEXT,
            report_qty REAL NOT NULL,
            report_time TEXT NOT NULL,
            operator_name TEXT,
            daily_capacity_compare_audit_id TEXT,
            daily_capacity_compare_qty REAL,
            daily_capacity_compare_selected_at TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sim_snapshot_work_reports_time
            ON simulation_restore_snapshot_work_reports (report_time DESC);
        CREATE TABLE IF NOT EXISTS masterdata_line_skeletons (
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            workshop_name TEXT,
            line_code TEXT NOT NULL,
            line_name TEXT,
            enabled_flag INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (company_code, workshop_code, line_code)
        );
        CREATE TABLE IF NOT EXISTS app_user_line_scopes (
            user_id TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, company_code, workshop_code, line_code),
            FOREIGN KEY (user_id) REFERENCES app_users(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_app_user_line_scopes_user
            ON app_user_line_scopes (user_id);
        CREATE INDEX IF NOT EXISTS idx_app_user_line_scopes_line
            ON app_user_line_scopes (company_code, workshop_code, line_code);

        -- Backup config / records (P1)
        CREATE TABLE IF NOT EXISTS app_backup_config (
            singleton_key TEXT PRIMARY KEY,
            enabled_flag INTEGER NOT NULL DEFAULT 0 CHECK (enabled_flag IN (0, 1)),
            frequency_minutes INTEGER NOT NULL DEFAULT 1440 CHECK (frequency_minutes BETWEEN 1 AND 525600),
            max_backups INTEGER NOT NULL DEFAULT 30 CHECK (max_backups BETWEEN 1 AND 1000),
            updated_at TEXT NOT NULL
        );
        INSERT OR IGNORE INTO app_backup_config (
            singleton_key,
            enabled_flag,
            frequency_minutes,
            max_backups,
            updated_at
        ) VALUES (
            'default',
            0,
            1440,
            30,
            datetime('now')
        );
        CREATE TABLE IF NOT EXISTS app_backup_records (
            backup_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            trigger TEXT NOT NULL,
            backup_path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
            created_by_user_id TEXT,
            created_by_username TEXT NOT NULL,
            FOREIGN KEY (created_by_user_id) REFERENCES app_users(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_app_backup_records_created_at
            ON app_backup_records (created_at DESC, backup_id DESC);
        """
    )
    _ensure_masterdata_process_routes_schema(connection)
    _ensure_jobs_schema(connection)
    _ensure_schedule_versions_schema(connection)
    _ensure_current_schedule_schema(connection)
    _ensure_reporting_resource_mappings_schema(connection)
    _ensure_work_reports_schema(connection)
    _ensure_schedule_tasks_schema(connection)
    _ensure_schedule_snapshots_schema(connection)
    _ensure_shift_capacity_schema(connection)
    _ensure_reporting_import_files_schema(connection)
    _ensure_simulation_restore_snapshot_work_reports_schema(connection)


def _ensure_jobs_schema(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "jobs")
    if "error_details_json" not in columns:
        connection.execute(
            """
            ALTER TABLE jobs
            ADD COLUMN error_details_json TEXT
            """
        )


def _ensure_masterdata_process_routes_schema(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "masterdata_process_routes")
    if "is_final_process" not in columns:
        connection.execute(
            """
            ALTER TABLE masterdata_process_routes
            ADD COLUMN is_final_process INTEGER NOT NULL DEFAULT 0
            """
        )
    connection.execute(
        """
        UPDATE masterdata_process_routes
        SET is_final_process = CASE
            WHEN COALESCE(is_final_process, 0) <> 0 THEN 1
            ELSE 0
        END
        """
    )


def _ensure_schedule_versions_schema(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "schedule_versions")
    for column_name, column_type in {
        "result_status": "TEXT NOT NULL DEFAULT 'FEASIBLE'",
        "result_summary": "TEXT",
    }.items():
        if column_name in columns:
            continue
        connection.execute(
            f"""
            ALTER TABLE schedule_versions
            ADD COLUMN {column_name} {column_type}
            """
        )
    connection.execute(
        """
        UPDATE masterdata_process_routes
        SET is_final_process = CASE
            WHEN sequence_no = (
                SELECT MAX(inner_route.sequence_no)
                FROM masterdata_process_routes AS inner_route
                WHERE inner_route.product_code = masterdata_process_routes.product_code
            ) THEN 1
            ELSE 0
        END
        WHERE product_code IN (
            SELECT product_code
            FROM masterdata_process_routes
            GROUP BY product_code
            HAVING SUM(CASE WHEN COALESCE(is_final_process, 0) = 1 THEN 1 ELSE 0 END) = 0
        )
        """
    )
    _normalize_schedule_version_statuses(connection)


def _normalize_schedule_version_statuses(connection: sqlite3.Connection) -> None:
    rows = fetch_all(
        connection,
        """
        SELECT version_no, status, created_at, published_at
        FROM schedule_versions
        ORDER BY
            COALESCE(NULLIF(TRIM(COALESCE(published_at, '')), ''), created_at) DESC,
            created_at DESC,
            version_no DESC
        """,
    )
    if not rows:
        return

    current_rows = [
        row for row in rows if str(row.get("status") or "").strip().upper() == "CURRENT"
    ]
    if current_rows:
        keep_current_version_no = str(current_rows[0].get("version_no") or "").strip()
    else:
        keep_current_version_no = str(rows[0].get("version_no") or "").strip()

    for row in rows:
        version_no = str(row.get("version_no") or "").strip()
        if not version_no:
            continue
        target_status = "CURRENT" if version_no == keep_current_version_no else "SAVED"
        target_label = "当前方案" if target_status == "CURRENT" else "已保存"
        connection.execute(
            """
            UPDATE schedule_versions
            SET status = ?, status_name_cn = ?
            WHERE version_no = ?
            """,
            (target_status, target_label, version_no),
        )


def _ensure_current_schedule_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS current_schedule_meta (
            singleton_key TEXT PRIMARY KEY,
            strategy_code TEXT NOT NULL,
            result_status TEXT NOT NULL DEFAULT 'FEASIBLE',
            result_summary TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS current_schedule_tasks (
            task_no INTEGER PRIMARY KEY,
            production_order_no TEXT NOT NULL,
            process_code TEXT NOT NULL,
            process_name_cn TEXT,
            workshop_code TEXT,
            line_code TEXT,
            calendar_date TEXT NOT NULL,
            shift_code TEXT NOT NULL,
            plan_qty REAL NOT NULL,
            plan_start_time TEXT,
            FOREIGN KEY (production_order_no) REFERENCES production_orders (production_order_no) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_current_schedule_tasks_date_process
            ON current_schedule_tasks (calendar_date, process_code);
        CREATE INDEX IF NOT EXISTS idx_current_schedule_tasks_order_no
            ON current_schedule_tasks (production_order_no, calendar_date);
        """
    )
    task_count_row = fetch_one(connection, "SELECT COUNT(1) AS total FROM current_schedule_tasks")
    if int((task_count_row or {}).get("total") or 0) > 0:
        return
    current_row = fetch_one(
        connection,
        """
        SELECT version_no, strategy_code, result_status, result_summary, created_at
        FROM schedule_versions
        WHERE UPPER(TRIM(COALESCE(status, ''))) = 'CURRENT'
        ORDER BY created_at DESC, version_no DESC
        LIMIT 1
        """,
    )
    if current_row is None:
        return
    version_no = str(current_row.get("version_no") or "").strip()
    if not version_no:
        return
    with connection:
        connection.execute(
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
                str(current_row.get("strategy_code") or ""),
                str(current_row.get("result_status") or "FEASIBLE"),
                current_row.get("result_summary"),
                str(current_row.get("created_at") or utc_now()),
            ),
        )
        connection.execute(
            "DELETE FROM current_schedule_tasks"
        )
        connection.execute(
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
            )
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
            (version_no,),
        )


def _ensure_schedule_snapshots_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schedule_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            snapshot_name TEXT NOT NULL,
            strategy_code TEXT NOT NULL,
            result_status TEXT NOT NULL DEFAULT 'FEASIBLE',
            result_summary TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_schedule_snapshots_created
            ON schedule_snapshots (created_at DESC, snapshot_id DESC);
        CREATE TABLE IF NOT EXISTS schedule_snapshot_tasks (
            snapshot_id TEXT NOT NULL,
            task_no INTEGER NOT NULL,
            production_order_no TEXT NOT NULL,
            process_code TEXT NOT NULL,
            process_name_cn TEXT,
            workshop_code TEXT,
            line_code TEXT,
            calendar_date TEXT NOT NULL,
            shift_code TEXT NOT NULL,
            plan_qty REAL NOT NULL,
            plan_start_time TEXT,
            PRIMARY KEY (snapshot_id, task_no),
            FOREIGN KEY (snapshot_id) REFERENCES schedule_snapshots (snapshot_id) ON DELETE CASCADE,
            FOREIGN KEY (production_order_no) REFERENCES production_orders (production_order_no) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_schedule_snapshot_tasks_order_no
            ON schedule_snapshot_tasks (production_order_no, calendar_date);
        """
    )
    snapshot_count_row = fetch_one(connection, "SELECT COUNT(1) AS total FROM schedule_snapshots")
    if int((snapshot_count_row or {}).get("total") or 0) > 0:
        return
    snapshot_rows = fetch_all(
        connection,
        """
        SELECT version_no, strategy_code, result_status, result_summary, created_at
        FROM schedule_versions
        WHERE UPPER(TRIM(COALESCE(status, ''))) = 'SAVED'
        ORDER BY created_at DESC, version_no DESC
        """,
    )
    if not snapshot_rows:
        return
    with connection:
        for row in snapshot_rows:
            snapshot_id = str(row.get("version_no") or "").strip()
            if not snapshot_id:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO schedule_snapshots (
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
                    str(row.get("strategy_code") or ""),
                    str(row.get("result_status") or "FEASIBLE"),
                    row.get("result_summary"),
                    str(row.get("created_at") or utc_now()),
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO schedule_snapshot_tasks (
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
                )
                SELECT
                    ?,
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
                (snapshot_id, snapshot_id),
            )


def _ensure_reporting_resource_mappings_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS masterdata_reporting_resource_mappings (
            mapping_id TEXT PRIMARY KEY,
            company_code TEXT NOT NULL,
            source_resource_group_name TEXT NOT NULL,
            source_resource_name TEXT NOT NULL,
            source_process_code TEXT NOT NULL,
            source_process_name TEXT,
            source_department_name TEXT,
            workshop_code TEXT NOT NULL,
            workshop_name TEXT,
            line_code TEXT NOT NULL,
            line_name TEXT,
            process_code TEXT NOT NULL,
            enabled_flag INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reporting_resource_mappings_source
            ON masterdata_reporting_resource_mappings (
                company_code,
                source_resource_group_name,
                source_resource_name,
                source_process_code,
                enabled_flag
            );
        """
    )


def _ensure_work_reports_schema(connection: sqlite3.Connection) -> None:
    create_table_sql = """
        CREATE TABLE IF NOT EXISTS work_reports (
            report_id TEXT PRIMARY KEY,
            production_order_no TEXT,
            report_scope TEXT NOT NULL DEFAULT 'ORDER',
            process_code TEXT,
            process_name TEXT,
            company_code TEXT,
            workshop_code TEXT,
            workshop_name TEXT,
            line_code TEXT,
            line_name TEXT,
            report_qty REAL NOT NULL,
            report_time TEXT NOT NULL,
            operator_code TEXT,
            operator_name TEXT,
            section_leader_name TEXT,
            dispatch_no TEXT,
            product_code TEXT,
            product_name TEXT,
            product_specification TEXT,
            resource_group_name TEXT,
            resource_name TEXT,
            department_name TEXT,
            source_process_code TEXT,
            source_process_name TEXT,
            mold_code TEXT,
            support_count REAL,
            weight_kg REAL,
            cavity_count REAL,
            total_cycle_time REAL,
            production_quota REAL,
            work_duration REAL,
            clamp_or_assembly_weight REAL,
            unit_weight REAL,
            source_sheet_name TEXT,
            source_row_no INTEGER,
            source_file_name TEXT,
            daily_capacity_compare_audit_id TEXT,
            daily_capacity_compare_qty REAL,
            daily_capacity_compare_selected_at TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (production_order_no) REFERENCES production_orders (production_order_no) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_work_reports_order_no
            ON work_reports (production_order_no, report_time DESC);
        CREATE INDEX IF NOT EXISTS idx_work_reports_scope
            ON work_reports (report_scope, report_time DESC);
        CREATE INDEX IF NOT EXISTS idx_work_reports_line_scope
            ON work_reports (company_code, workshop_code, line_code, process_code, report_time DESC);
        CREATE INDEX IF NOT EXISTS idx_work_reports_source_sheet
            ON work_reports (source_file_name, source_sheet_name, source_row_no);
    """
    table_info = _table_info(connection, "work_reports")
    if not table_info:
        connection.executescript(create_table_sql)
        return

    production_order_column = next(
        (row for row in table_info if str(row[1]) == "production_order_no"),
        None,
    )
    if production_order_column is None:
        raise server_error(
            code="WORK_REPORTS_ORDER_COLUMN_MISSING",
            message="work_reports.production_order_no column is missing.",
        )
    is_not_null = int(production_order_column[3] or 0) == 1
    if is_not_null:
        connection.executescript(
            """
            ALTER TABLE work_reports RENAME TO work_reports__legacy_order_required;
            """
        )
        connection.executescript(create_table_sql)
        connection.executescript(
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
                updated_at
            FROM work_reports__legacy_order_required;
            DROP TABLE work_reports__legacy_order_required;
            """
        )

    columns = _table_columns(connection, "work_reports")
    extra_columns = {
        "report_scope": "TEXT NOT NULL DEFAULT 'ORDER'",
        "company_code": "TEXT",
        "operator_code": "TEXT",
        "section_leader_name": "TEXT",
        "dispatch_no": "TEXT",
        "product_code": "TEXT",
        "product_name": "TEXT",
        "product_specification": "TEXT",
        "resource_group_name": "TEXT",
        "resource_name": "TEXT",
        "department_name": "TEXT",
        "source_process_code": "TEXT",
        "source_process_name": "TEXT",
        "mold_code": "TEXT",
        "support_count": "REAL",
        "weight_kg": "REAL",
        "cavity_count": "REAL",
        "total_cycle_time": "REAL",
        "production_quota": "REAL",
        "work_duration": "REAL",
        "clamp_or_assembly_weight": "REAL",
        "unit_weight": "REAL",
        "source_sheet_name": "TEXT",
        "source_row_no": "INTEGER",
        "source_file_name": "TEXT",
        "daily_capacity_compare_audit_id": "TEXT",
        "daily_capacity_compare_qty": "REAL",
        "daily_capacity_compare_selected_at": "TEXT",
    }
    for column_name, column_type in extra_columns.items():
        if column_name in columns:
            continue
        connection.execute(
            f"""
            ALTER TABLE work_reports
            ADD COLUMN {column_name} {column_type}
            """
        )
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_work_reports_order_no
            ON work_reports (production_order_no, report_time DESC);
        CREATE INDEX IF NOT EXISTS idx_work_reports_scope
            ON work_reports (report_scope, report_time DESC);
        CREATE INDEX IF NOT EXISTS idx_work_reports_line_scope
            ON work_reports (company_code, workshop_code, line_code, process_code, report_time DESC);
        CREATE INDEX IF NOT EXISTS idx_work_reports_source_sheet
            ON work_reports (source_file_name, source_sheet_name, source_row_no);
        """
    )


def _ensure_schedule_tasks_schema(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "schedule_tasks")
    extra_columns = {
        "workshop_code": "TEXT",
        "line_code": "TEXT",
    }
    for column_name, column_type in extra_columns.items():
        if column_name in columns:
            continue
        connection.execute(
            f"""
            ALTER TABLE schedule_tasks
            ADD COLUMN {column_name} {column_type}
            """
        )
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_tasks_line_scope
            ON schedule_tasks (version_no, workshop_code, line_code, process_code, calendar_date);
        """
    )


def _rebuild_table_with_shift_capacity(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    create_sql: str,
    copy_sql: str,
    index_sql: str = "",
) -> None:
    columns = _table_columns(connection, table_name)
    if "shift_code" in columns:
        return
    legacy_table_name = f"{table_name}__legacy_shift_upgrade"
    connection.execute(f"ALTER TABLE {table_name} RENAME TO {legacy_table_name}")
    connection.executescript(create_sql)
    connection.execute(copy_sql.replace("{legacy_table_name}", legacy_table_name))
    connection.execute(f"DROP TABLE {legacy_table_name}")
    if index_sql:
        connection.executescript(index_sql)


def _ensure_shift_capacity_schema(connection: sqlite3.Connection) -> None:
    _rebuild_table_with_shift_capacity(
        connection,
        table_name="daily_line_capacity_plan",
        create_sql="""
        CREATE TABLE IF NOT EXISTS daily_line_capacity_plan (
            calendar_date TEXT NOT NULL,
            shift_code TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            process_code TEXT NOT NULL,
            planned_capacity_qty REAL NOT NULL,
            worker_count INTEGER,
            machine_count INTEGER,
            split_rule TEXT NOT NULL DEFAULT 'DAY_ONLY',
            split_day_ratio REAL,
            split_night_ratio REAL,
            capacity_change_type TEXT,
            capacity_change_reason TEXT,
            source_note TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (calendar_date, shift_code, company_code, workshop_code, line_code, process_code)
        );
        """,
        copy_sql="""
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
            split_rule,
            split_day_ratio,
            split_night_ratio,
            capacity_change_type,
            capacity_change_reason,
            source_note,
            updated_at
        )
        SELECT
            legacy.calendar_date,
            'DAY',
            legacy.company_code,
            legacy.workshop_code,
            legacy.line_code,
            legacy.process_code,
            legacy.planned_capacity_qty,
            legacy.worker_count,
            legacy.machine_count,
            'DAY_ONLY',
            1.0,
            0.0,
            NULL,
            NULL,
            legacy.source_note,
            legacy.updated_at
        FROM {legacy_table_name} legacy
        """,
        index_sql="""
        CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_plan_date
            ON daily_line_capacity_plan (calendar_date, shift_code, workshop_code, line_code, process_code);
        """,
    )
    for column_name, column_type in {
        "split_rule": "TEXT NOT NULL DEFAULT 'DAY_ONLY'",
        "split_day_ratio": "REAL",
        "split_night_ratio": "REAL",
        "capacity_change_type": "TEXT",
        "capacity_change_reason": "TEXT",
    }.items():
        if column_name not in _table_columns(connection, "daily_line_capacity_plan"):
            connection.execute(
                f"ALTER TABLE daily_line_capacity_plan ADD COLUMN {column_name} {column_type}"
            )
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_plan_date
            ON daily_line_capacity_plan (calendar_date, shift_code, workshop_code, line_code, process_code);
        """
    )

    _rebuild_table_with_shift_capacity(
        connection,
        table_name="daily_line_capacity_actual",
        create_sql="""
        CREATE TABLE IF NOT EXISTS daily_line_capacity_actual (
            calendar_date TEXT NOT NULL,
            shift_code TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            process_code TEXT NOT NULL,
            actual_capacity_qty REAL NOT NULL,
            report_count INTEGER NOT NULL DEFAULT 0,
            last_report_time TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (calendar_date, shift_code, company_code, workshop_code, line_code, process_code)
        );
        """,
        copy_sql="""
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
            'DAY',
            company_code,
            workshop_code,
            line_code,
            process_code,
            actual_capacity_qty,
            report_count,
            last_report_time,
            updated_at
        FROM {legacy_table_name}
        """,
        index_sql="""
        CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_actual_date
            ON daily_line_capacity_actual (calendar_date, shift_code, workshop_code, line_code, process_code);
        """,
    )
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_actual_date
            ON daily_line_capacity_actual (calendar_date, shift_code, workshop_code, line_code, process_code);
        """
    )

    _rebuild_table_with_shift_capacity(
        connection,
        table_name="daily_line_capacity_plan_audit",
        create_sql="""
        CREATE TABLE IF NOT EXISTS daily_line_capacity_plan_audit (
            audit_id TEXT PRIMARY KEY,
            calendar_date TEXT NOT NULL,
            shift_code TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            process_code TEXT NOT NULL,
            old_planned_capacity_qty REAL,
            new_planned_capacity_qty REAL,
            old_worker_count INTEGER,
            new_worker_count INTEGER,
            old_machine_count INTEGER,
            new_machine_count INTEGER,
            capacity_change_type TEXT,
            capacity_change_reason TEXT,
            operator_user_id TEXT,
            operator_username TEXT,
            operator_display_name TEXT,
            changed_at TEXT NOT NULL,
            FOREIGN KEY (operator_user_id) REFERENCES app_users(user_id)
        );
        """,
        copy_sql="""
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
            capacity_change_type,
            capacity_change_reason,
            operator_user_id,
            operator_username,
            operator_display_name,
            changed_at
        )
        SELECT
            audit_id,
            calendar_date,
            'DAY',
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
            NULL,
            NULL,
            operator_user_id,
            operator_username,
            operator_display_name,
            changed_at
        FROM {legacy_table_name}
        """,
        index_sql="""
        CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_plan_audit_date
            ON daily_line_capacity_plan_audit (calendar_date, shift_code, changed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_plan_audit_line
            ON daily_line_capacity_plan_audit (workshop_code, line_code, process_code, shift_code, changed_at DESC);
        """,
    )
    for column_name, column_type in {
        "capacity_change_type": "TEXT",
        "capacity_change_reason": "TEXT",
    }.items():
        if column_name not in _table_columns(connection, "daily_line_capacity_plan_audit"):
            connection.execute(
                f"ALTER TABLE daily_line_capacity_plan_audit ADD COLUMN {column_name} {column_type}"
            )
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_plan_audit_date
            ON daily_line_capacity_plan_audit (calendar_date, shift_code, changed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_plan_audit_line
            ON daily_line_capacity_plan_audit (workshop_code, line_code, process_code, shift_code, changed_at DESC);
        """
    )

    _rebuild_table_with_shift_capacity(
        connection,
        table_name="simulation_restore_snapshot_daily_line_capacity_plan",
        create_sql="""
        CREATE TABLE IF NOT EXISTS simulation_restore_snapshot_daily_line_capacity_plan (
            calendar_date TEXT NOT NULL,
            shift_code TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            process_code TEXT NOT NULL,
            planned_capacity_qty REAL NOT NULL,
            worker_count INTEGER,
            machine_count INTEGER,
            split_rule TEXT NOT NULL DEFAULT 'DAY_ONLY',
            split_day_ratio REAL,
            split_night_ratio REAL,
            capacity_change_type TEXT,
            capacity_change_reason TEXT,
            source_note TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (calendar_date, shift_code, company_code, workshop_code, line_code, process_code)
        );
        """,
        copy_sql="""
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
            split_rule,
            split_day_ratio,
            split_night_ratio,
            capacity_change_type,
            capacity_change_reason,
            source_note,
            updated_at
        )
        SELECT
            calendar_date,
            'DAY',
            company_code,
            workshop_code,
            line_code,
            process_code,
            planned_capacity_qty,
            worker_count,
            machine_count,
            'DAY_ONLY',
            1.0,
            0.0,
            NULL,
            NULL,
            source_note,
            updated_at
        FROM {legacy_table_name}
        """,
    )
    for column_name, column_type in {
        "split_rule": "TEXT NOT NULL DEFAULT 'DAY_ONLY'",
        "split_day_ratio": "REAL",
        "split_night_ratio": "REAL",
        "capacity_change_type": "TEXT",
        "capacity_change_reason": "TEXT",
    }.items():
        if column_name not in _table_columns(connection, "simulation_restore_snapshot_daily_line_capacity_plan"):
            connection.execute(
                f"ALTER TABLE simulation_restore_snapshot_daily_line_capacity_plan ADD COLUMN {column_name} {column_type}"
            )

    _rebuild_table_with_shift_capacity(
        connection,
        table_name="simulation_restore_snapshot_daily_line_capacity_actual",
        create_sql="""
        CREATE TABLE IF NOT EXISTS simulation_restore_snapshot_daily_line_capacity_actual (
            calendar_date TEXT NOT NULL,
            shift_code TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            process_code TEXT NOT NULL,
            actual_capacity_qty REAL NOT NULL,
            report_count INTEGER NOT NULL DEFAULT 0,
            last_report_time TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (calendar_date, shift_code, company_code, workshop_code, line_code, process_code)
        );
        """,
        copy_sql="""
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
            'DAY',
            company_code,
            workshop_code,
            line_code,
            process_code,
            actual_capacity_qty,
            report_count,
            last_report_time,
            updated_at
        FROM {legacy_table_name}
        """,
    )

    _rebuild_table_with_shift_capacity(
        connection,
        table_name="simulation_restore_snapshot_daily_line_capacity_plan_audit",
        create_sql="""
        CREATE TABLE IF NOT EXISTS simulation_restore_snapshot_daily_line_capacity_plan_audit (
            audit_id TEXT PRIMARY KEY,
            calendar_date TEXT NOT NULL,
            shift_code TEXT NOT NULL,
            company_code TEXT NOT NULL,
            workshop_code TEXT NOT NULL,
            line_code TEXT NOT NULL,
            process_code TEXT NOT NULL,
            old_planned_capacity_qty REAL,
            new_planned_capacity_qty REAL,
            old_worker_count INTEGER,
            new_worker_count INTEGER,
            old_machine_count INTEGER,
            new_machine_count INTEGER,
            capacity_change_type TEXT,
            capacity_change_reason TEXT,
            operator_user_id TEXT,
            operator_username TEXT,
            operator_display_name TEXT,
            changed_at TEXT NOT NULL
        );
        """,
        copy_sql="""
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
            capacity_change_type,
            capacity_change_reason,
            operator_user_id,
            operator_username,
            operator_display_name,
            changed_at
        )
        SELECT
            audit_id,
            calendar_date,
            'DAY',
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
            NULL,
            NULL,
            operator_user_id,
            operator_username,
            operator_display_name,
            changed_at
        FROM {legacy_table_name}
        """,
    )
    for column_name, column_type in {
        "capacity_change_type": "TEXT",
        "capacity_change_reason": "TEXT",
    }.items():
        if column_name not in _table_columns(connection, "simulation_restore_snapshot_daily_line_capacity_plan_audit"):
            connection.execute(
                f"ALTER TABLE simulation_restore_snapshot_daily_line_capacity_plan_audit ADD COLUMN {column_name} {column_type}"
            )


def _ensure_reporting_import_files_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS reporting_import_files (
            file_sha256 TEXT PRIMARY KEY,
            source_file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            original_file_name TEXT,
            file_size_bytes INTEGER NOT NULL DEFAULT 0,
            sheet_names_json TEXT,
            imported_by_user_id TEXT,
            imported_by_username TEXT,
            imported_by_display_name TEXT,
            total_row_count INTEGER NOT NULL DEFAULT 0,
            imported_count INTEGER NOT NULL DEFAULT 0,
            skipped_existing_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            created_missing_order_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_imported_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reporting_import_files_last_imported
            ON reporting_import_files (last_imported_at DESC, file_sha256 DESC);
        """
    )


def _ensure_simulation_restore_snapshot_work_reports_schema(
    connection: sqlite3.Connection,
) -> None:
    columns = _table_columns(connection, "simulation_restore_snapshot_work_reports")
    extra_columns = {
        "report_scope": "TEXT NOT NULL DEFAULT 'ORDER'",
        "company_code": "TEXT",
        "operator_code": "TEXT",
        "section_leader_name": "TEXT",
        "dispatch_no": "TEXT",
        "product_code": "TEXT",
        "product_name": "TEXT",
        "product_specification": "TEXT",
        "resource_group_name": "TEXT",
        "resource_name": "TEXT",
        "department_name": "TEXT",
        "source_process_code": "TEXT",
        "source_process_name": "TEXT",
        "mold_code": "TEXT",
        "support_count": "REAL",
        "weight_kg": "REAL",
        "cavity_count": "REAL",
        "total_cycle_time": "REAL",
        "production_quota": "REAL",
        "work_duration": "REAL",
        "clamp_or_assembly_weight": "REAL",
        "unit_weight": "REAL",
        "source_sheet_name": "TEXT",
        "source_row_no": "INTEGER",
        "source_file_name": "TEXT",
        "daily_capacity_compare_audit_id": "TEXT",
        "daily_capacity_compare_qty": "REAL",
        "daily_capacity_compare_selected_at": "TEXT",
    }
    for column_name, column_type in extra_columns.items():
        if column_name in columns:
            continue
        connection.execute(
            f"""
            ALTER TABLE simulation_restore_snapshot_work_reports
            ADD COLUMN {column_name} {column_type}
            """
        )
