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


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
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
