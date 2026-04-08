from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BACKEND_ROOT, get_settings
from .errors import server_error


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


def open_connection() -> sqlite3.Connection:
    database_path = ensure_database_exists()
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    migrate_database_schema(connection)
    connection.commit()
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
        migrate_database_schema(connection)
        connection.commit()
    finally:
        connection.close()
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
        """
    )
    _ensure_masterdata_process_routes_schema(connection)
    _ensure_work_reports_schema(connection)


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


def _ensure_work_reports_schema(connection: sqlite3.Connection) -> None:
    table_info = _table_info(connection, "work_reports")
    if not table_info:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS work_reports (
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
                updated_at TEXT NOT NULL,
                FOREIGN KEY (production_order_no) REFERENCES production_orders (production_order_no) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_work_reports_order_no
                ON work_reports (production_order_no, report_time DESC);
            """
        )
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
    if not is_not_null:
        return

    connection.executescript(
        """
        ALTER TABLE work_reports RENAME TO work_reports__legacy_order_required;
        CREATE TABLE work_reports (
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
            updated_at TEXT NOT NULL,
            FOREIGN KEY (production_order_no) REFERENCES production_orders (production_order_no) ON DELETE CASCADE
        );
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
        CREATE INDEX IF NOT EXISTS idx_work_reports_order_no
            ON work_reports (production_order_no, report_time DESC);
        """
    )
