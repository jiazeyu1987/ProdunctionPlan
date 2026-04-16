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
    _ensure_reporting_resource_mappings_schema(connection)
    _ensure_work_reports_schema(connection)
    _ensure_schedule_tasks_schema(connection)
    _ensure_reporting_import_files_schema(connection)
    _ensure_simulation_restore_snapshot_work_reports_schema(connection)


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
