from __future__ import annotations

import sqlite3
from typing import Any

from ..db import fetch_all, fetch_one
from ..errors import not_found
from ..errors import server_error


BACKUP_CONFIG_SINGLETON_KEY = "default"


class BackupRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get_backup_config(self) -> dict[str, Any]:
        row = fetch_one(
            self.connection,
            """
            SELECT
                enabled_flag,
                frequency_minutes,
                max_backups,
                updated_at
            FROM app_backup_config
            WHERE singleton_key = ?
            """,
            (BACKUP_CONFIG_SINGLETON_KEY,),
        )
        if row is None:
            raise server_error(
                code="BACKUP_CONFIG_MISSING",
                message="Backup config row is missing (expected singleton row).",
                details={"singleton_key": BACKUP_CONFIG_SINGLETON_KEY},
            )
        return {
            "enabled_flag": int(row["enabled_flag"] or 0),
            "frequency_minutes": int(row["frequency_minutes"] or 0),
            "max_backups": int(row["max_backups"] or 0),
            "updated_at": str(row["updated_at"] or "").strip(),
        }

    def upsert_backup_config(
        self,
        *,
        enabled_flag: int,
        frequency_minutes: int,
        max_backups: int,
        updated_at: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO app_backup_config (
                singleton_key,
                enabled_flag,
                frequency_minutes,
                max_backups,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(singleton_key) DO UPDATE SET
                enabled_flag = excluded.enabled_flag,
                frequency_minutes = excluded.frequency_minutes,
                max_backups = excluded.max_backups,
                updated_at = excluded.updated_at
            """,
            (
                BACKUP_CONFIG_SINGLETON_KEY,
                enabled_flag,
                frequency_minutes,
                max_backups,
                updated_at,
            ),
        )

    def list_backup_records(self) -> list[dict[str, Any]]:
        return fetch_all(
            self.connection,
            """
            SELECT
                backup_id,
                created_at,
                trigger,
                size_bytes,
                created_by_username
            FROM app_backup_records
            ORDER BY created_at DESC, backup_id DESC
            """,
        )

    def list_backup_records_detailed(self) -> list[dict[str, Any]]:
        return fetch_all(
            self.connection,
            """
            SELECT
                backup_id,
                created_at,
                trigger,
                backup_path,
                size_bytes,
                created_by_user_id,
                created_by_username
            FROM app_backup_records
            ORDER BY created_at DESC, backup_id DESC
            """,
        )

    def get_backup_record(self, backup_id: str) -> dict[str, Any]:
        row = fetch_one(
            self.connection,
            """
            SELECT
                backup_id,
                created_at,
                trigger,
                backup_path,
                size_bytes,
                created_by_user_id,
                created_by_username
            FROM app_backup_records
            WHERE backup_id = ?
            """,
            (backup_id,),
        )
        if row is None:
            raise not_found(
                code="BACKUP_RECORD_NOT_FOUND",
                message=f"Backup record does not exist: {backup_id}.",
                details={"backup_id": backup_id},
            )
        return row

    def get_latest_backup_record(self, *, trigger: str | None = None) -> dict[str, Any] | None:
        if trigger:
            return fetch_one(
                self.connection,
                """
                SELECT
                    backup_id,
                    created_at,
                    trigger,
                    backup_path,
                    size_bytes,
                    created_by_user_id,
                    created_by_username
                FROM app_backup_records
                WHERE trigger = ?
                ORDER BY created_at DESC, backup_id DESC
                LIMIT 1
                """,
                (trigger,),
            )
        return fetch_one(
            self.connection,
            """
            SELECT
                backup_id,
                created_at,
                trigger,
                backup_path,
                size_bytes,
                created_by_user_id,
                created_by_username
            FROM app_backup_records
            ORDER BY created_at DESC, backup_id DESC
            LIMIT 1
            """,
        )

    def create_backup_record(
        self,
        *,
        backup_id: str,
        created_at: str,
        trigger: str,
        backup_path: str,
        size_bytes: int,
        created_by_user_id: str | None,
        created_by_username: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO app_backup_records (
                backup_id,
                created_at,
                trigger,
                backup_path,
                size_bytes,
                created_by_user_id,
                created_by_username
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                backup_id,
                created_at,
                trigger,
                backup_path,
                size_bytes,
                created_by_user_id,
                created_by_username,
            ),
        )

    def upsert_backup_record(
        self,
        *,
        backup_id: str,
        created_at: str,
        trigger: str,
        backup_path: str,
        size_bytes: int,
        created_by_user_id: str | None,
        created_by_username: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO app_backup_records (
                backup_id,
                created_at,
                trigger,
                backup_path,
                size_bytes,
                created_by_user_id,
                created_by_username
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(backup_id) DO UPDATE SET
                created_at = excluded.created_at,
                trigger = excluded.trigger,
                backup_path = excluded.backup_path,
                size_bytes = excluded.size_bytes,
                created_by_user_id = excluded.created_by_user_id,
                created_by_username = excluded.created_by_username
            """,
            (
                backup_id,
                created_at,
                trigger,
                backup_path,
                size_bytes,
                created_by_user_id,
                created_by_username,
            ),
        )

    def delete_backup_record(self, backup_id: str) -> None:
        deleted = self.connection.execute(
            """
            DELETE FROM app_backup_records
            WHERE backup_id = ?
            """,
            (backup_id,),
        )
        if deleted.rowcount != 1:
            raise server_error(
                code="BACKUP_RECORD_DELETE_FAILED",
                message=f"Backup record could not be deleted: {backup_id}.",
                details={"backup_id": backup_id},
            )
