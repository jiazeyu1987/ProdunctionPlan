from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..db import ensure_database_exists, transaction, utc_now
from ..errors import bad_request, server_error
from ..repositories.backups import BackupRepository


BACKUP_TRIGGER_MANUAL = "MANUAL"
BACKUP_TRIGGER_AUTO = "AUTO"
SYSTEM_BACKUP_USERNAME = "system:auto"


def _parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _backup_filename(created_at: str, backup_id: str) -> str:
    timestamp = _parse_timestamp(created_at).strftime("%Y%m%dT%H%M%SZ")
    return f"production-plan-backup-{timestamp}-{backup_id}.db"


def _ensure_backup_dir() -> Path:
    backup_dir = get_settings().backup_dir
    if not backup_dir.exists():
        raise server_error(
            code="BACKUP_DIR_MISSING",
            message=f"Backup directory does not exist: {backup_dir}. Create it before retrying.",
            details={"backup_dir": str(backup_dir)},
        )
    if not backup_dir.is_dir():
        raise server_error(
            code="BACKUP_DIR_INVALID",
            message=f"Backup path is not a directory: {backup_dir}.",
            details={"backup_dir": str(backup_dir)},
        )
    if not os.access(backup_dir, os.W_OK):
        raise server_error(
            code="BACKUP_DIR_NOT_WRITABLE",
            message=f"Backup directory is not writable: {backup_dir}.",
            details={"backup_dir": str(backup_dir)},
        )
    return backup_dir


def _normalize_trigger(trigger: str) -> str:
    normalized = str(trigger or "").strip().upper()
    if normalized not in {BACKUP_TRIGGER_MANUAL, BACKUP_TRIGGER_AUTO}:
        raise bad_request(
            code="BACKUP_TRIGGER_INVALID",
            message="trigger must be MANUAL or AUTO.",
            details={"trigger": trigger},
        )
    return normalized


def _manual_actor(actor: dict[str, Any] | None) -> tuple[str | None, str]:
    normalized_actor = actor if isinstance(actor, dict) else {}
    user_id = str(normalized_actor.get("user_id") or "").strip() or None
    username = str(normalized_actor.get("username") or "").strip()
    if not username:
        username = str(normalized_actor.get("display_name") or "").strip()
    if not username:
        raise server_error(
            code="BACKUP_ACTOR_MISSING",
            message="Manual backup requires actor.username or actor.display_name.",
        )
    return user_id, username


def _delete_backup_file(path: Path, *, missing_code: str, delete_code: str) -> None:
    if not path.exists():
        raise server_error(
            code=missing_code,
            message=f"Backup file does not exist: {path}.",
            details={"backup_path": str(path)},
        )
    if not path.is_file():
        raise server_error(
            code="BACKUP_FILE_INVALID",
            message=f"Backup path is not a file: {path}.",
            details={"backup_path": str(path)},
        )
    try:
        path.unlink()
    except OSError as exc:
        raise server_error(
            code=delete_code,
            message=f"Failed to delete backup file: {path}. {exc}",
            details={"backup_path": str(path)},
        ) from exc


def restore_backup_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload") or {}
    backup_id = str(payload.get("backup_id") or "").strip()
    if not backup_id:
        raise bad_request(
            code="BACKUP_ID_REQUIRED",
            message="backup_id is required for restore.",
        )

    database_path = ensure_database_exists()
    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        connection.row_factory = sqlite3.Row
        repository = BackupRepository(connection)
        backup_record = repository.get_backup_record(backup_id)
        backup_records = repository.list_backup_records_detailed()
    finally:
        connection.close()

    backup_path = Path(str(backup_record["backup_path"]))
    if not backup_path.exists():
        raise server_error(
            code="BACKUP_FILE_MISSING",
            message=f"Backup file does not exist: {backup_path}.",
            details={"backup_id": backup_id, "backup_path": str(backup_path)},
        )
    if not backup_path.is_file():
        raise server_error(
            code="BACKUP_FILE_INVALID",
            message=f"Backup path is not a file: {backup_path}.",
            details={"backup_id": backup_id, "backup_path": str(backup_path)},
        )

    restore_temp_path = database_path.with_name(
        f"{database_path.name}.restore-{str(job['job_id'])}.tmp"
    )
    if restore_temp_path.exists():
        try:
            restore_temp_path.unlink()
        except OSError as exc:
            raise server_error(
                code="BACKUP_RESTORE_TEMP_DELETE_FAILED",
                message=f"Failed to remove stale restore temp file: {restore_temp_path}. {exc}",
                details={"restore_temp_path": str(restore_temp_path)},
            ) from exc
    try:
        shutil.copy2(backup_path, restore_temp_path)
    except OSError as exc:
        raise server_error(
            code="BACKUP_RESTORE_COPY_FAILED",
            message=f"Failed to copy backup to restore temp file: {backup_path}. {exc}",
            details={
                "backup_id": backup_id,
                "backup_path": str(backup_path),
                "restore_temp_path": str(restore_temp_path),
            },
        ) from exc

    try:
        os.replace(restore_temp_path, database_path)
    except OSError as exc:
        try:
            if restore_temp_path.exists():
                restore_temp_path.unlink()
        except OSError:
            pass
        raise server_error(
            code="BACKUP_RESTORE_REPLACE_FAILED",
            message=(
                f"Failed to replace SQLite database with backup {backup_id}. "
                f"Stop the backend service and retry. {exc}"
            ),
            details={
                "backup_id": backup_id,
                "backup_path": str(backup_path),
                "database_path": str(database_path),
            },
        ) from exc

    connection = sqlite3.connect(database_path, check_same_thread=False)
    try:
        connection.row_factory = sqlite3.Row
        repository = BackupRepository(connection)
        with transaction(connection):
            for record in backup_records:
                repository.upsert_backup_record(
                    backup_id=str(record["backup_id"]),
                    created_at=str(record["created_at"]),
                    trigger=str(record["trigger"]),
                    backup_path=str(record["backup_path"]),
                    size_bytes=int(record["size_bytes"] or 0),
                    created_by_user_id=(
                        str(record.get("created_by_user_id") or "").strip() or None
                    ),
                    created_by_username=str(record["created_by_username"]),
                )
    finally:
        connection.close()

    restored_at = utc_now()
    return {
        "restored_backup_id": backup_id,
        "restored_at": restored_at,
        "requires_restart": True,
    }


class BackupService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.repository = BackupRepository(connection)

    def _resolve_created_by_user_id(self, user_id: str | None) -> str | None:
        normalized_user_id = str(user_id or "").strip() or None
        if normalized_user_id is None:
            return None
        row = self.connection.execute(
            """
            SELECT user_id
            FROM app_users
            WHERE user_id = ?
            """,
            (normalized_user_id,),
        ).fetchone()
        return normalized_user_id if row is not None else None

    def create_backup(
        self,
        *,
        trigger: str,
        actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_trigger = _normalize_trigger(trigger)
        created_at = utc_now()
        backup_id = uuid.uuid4().hex
        database_path = ensure_database_exists()
        backup_dir = _ensure_backup_dir()
        filename = _backup_filename(created_at, backup_id)
        final_path = backup_dir / filename
        temp_path = backup_dir / f"{filename}.tmp"
        if final_path.exists() or temp_path.exists():
            raise server_error(
                code="BACKUP_FILE_ALREADY_EXISTS",
                message=f"Backup target already exists: {final_path}.",
                details={"backup_path": str(final_path)},
            )

        if normalized_trigger == BACKUP_TRIGGER_AUTO:
            created_by_user_id = None
            created_by_username = SYSTEM_BACKUP_USERNAME
        else:
            created_by_user_id, created_by_username = _manual_actor(actor)
            created_by_user_id = self._resolve_created_by_user_id(created_by_user_id)

        try:
            if temp_path.exists():
                temp_path.unlink()
            destination_connection = sqlite3.connect(temp_path, check_same_thread=False)
            try:
                self.connection.backup(destination_connection)
                destination_connection.commit()
            finally:
                destination_connection.close()
            os.replace(temp_path, final_path)
        except sqlite3.Error as exc:
            if temp_path.exists():
                temp_path.unlink()
            raise server_error(
                code="BACKUP_CREATE_FAILED",
                message=f"SQLite backup failed: {exc}",
                details={"database_path": str(database_path), "backup_path": str(final_path)},
            ) from exc
        except OSError as exc:
            if temp_path.exists():
                temp_path.unlink()
            raise server_error(
                code="BACKUP_WRITE_FAILED",
                message=f"Failed to write backup file: {final_path}. {exc}",
                details={"database_path": str(database_path), "backup_path": str(final_path)},
            ) from exc

        try:
            size_bytes = final_path.stat().st_size
        except OSError as exc:
            raise server_error(
                code="BACKUP_FILE_STAT_FAILED",
                message=f"Failed to stat backup file: {final_path}. {exc}",
                details={"backup_path": str(final_path)},
            ) from exc

        backup_config = self.repository.get_backup_config()
        max_backups = int(backup_config["max_backups"] or 0)
        existing_records = self.repository.list_backup_records_detailed()
        overflow_records = existing_records[max_backups - 1 :] if len(existing_records) >= max_backups else []
        purged_backup_ids: list[str] = []
        for record in overflow_records:
            _delete_backup_file(
                Path(str(record["backup_path"])),
                missing_code="BACKUP_RETENTION_FILE_MISSING",
                delete_code="BACKUP_RETENTION_DELETE_FAILED",
            )
            purged_backup_ids.append(str(record["backup_id"]))

        try:
            with transaction(self.connection):
                self.repository.create_backup_record(
                    backup_id=backup_id,
                    created_at=created_at,
                    trigger=normalized_trigger,
                    backup_path=str(final_path),
                    size_bytes=size_bytes,
                    created_by_user_id=created_by_user_id,
                    created_by_username=created_by_username,
                )
                for purged_backup_id in purged_backup_ids:
                    self.repository.delete_backup_record(purged_backup_id)
        except sqlite3.Error as exc:
            raise server_error(
                code="BACKUP_RECORD_WRITE_FAILED",
                message=f"Failed to persist backup record metadata. {exc}",
                details={"backup_id": backup_id, "backup_path": str(final_path)},
            ) from exc

        return {
            "backup_id": backup_id,
            "created_at": created_at,
            "trigger": normalized_trigger,
            "size_bytes": size_bytes,
            "created_by_username": created_by_username,
            "purged_backup_ids": purged_backup_ids,
        }
