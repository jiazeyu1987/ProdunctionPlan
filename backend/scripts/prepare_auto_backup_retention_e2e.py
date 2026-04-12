from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings
from app.db import managed_connection, prepare_database, transaction, utc_now
from app.repositories.backups import BackupRepository
from app.worker import JobWorker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare an isolated E2E database with auto-backup retention state.",
    )
    parser.add_argument("--db-path", required=True, help="SQLite database path.")
    parser.add_argument("--backup-dir", required=True, help="Backup directory path.")
    parser.add_argument(
        "--auto-backups",
        type=int,
        default=3,
        help="Number of auto backups to simulate. Defaults to 3.",
    )
    parser.add_argument(
        "--max-backups",
        type=int,
        default=2,
        help="Retention limit to persist. Defaults to 2.",
    )
    return parser.parse_args()


def to_iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def normalize_auto_backup_timestamps() -> None:
    with managed_connection() as connection:
        repository = BackupRepository(connection)
        records = repository.list_backup_records_detailed()
        base_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        with transaction(connection):
            for index, record in enumerate(records):
                created_at = to_iso_utc(base_time - timedelta(seconds=index))
                connection.execute(
                    """
                    UPDATE app_backup_records
                    SET created_at = ?
                    WHERE backup_id = ?
                    """,
                    (created_at, str(record["backup_id"])),
                )


def configure_backup_state(max_backups: int) -> None:
    updated_at = utc_now()
    with managed_connection() as connection:
        repository = BackupRepository(connection)
        with transaction(connection):
            connection.execute("DELETE FROM app_backup_records")
            connection.execute("DELETE FROM jobs")
            repository.upsert_backup_config(
                enabled_flag=1,
                frequency_minutes=1,
                max_backups=max_backups,
                updated_at=updated_at,
            )


def clear_auto_backup_jobs() -> None:
    with managed_connection() as connection:
        with transaction(connection):
            connection.execute(
                """
                DELETE FROM jobs
                WHERE job_type = 'DB_BACKUP_CREATE_AUTO'
                """
            )


def clear_backup_dir(backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for child in backup_dir.iterdir():
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


def main() -> int:
    args = parse_args()
    database_path = Path(args.db_path).resolve()
    backup_dir = Path(args.backup_dir).resolve()

    os.environ["PRODUCTION_PLAN_DB_PATH"] = str(database_path)
    os.environ["PRODUCTION_PLAN_BACKUP_DIR"] = str(backup_dir)
    get_settings.cache_clear()

    clear_backup_dir(backup_dir)
    prepare_database()
    configure_backup_state(max(args.max_backups, 1))

    worker = JobWorker()
    for _ in range(max(args.auto_backups, 1)):
        worker._last_auto_backup_check_at = 0.0
        worker._maybe_enqueue_auto_backup()
        processed = worker._process_next_job()
        if not processed:
            raise RuntimeError("Auto backup worker did not enqueue or process a backup job.")
        normalize_auto_backup_timestamps()
        clear_auto_backup_jobs()

    with managed_connection() as connection:
        records = BackupRepository(connection).list_backup_records_detailed()

    expected_count = min(max(args.auto_backups, 1), max(args.max_backups, 1))
    if len(records) != expected_count:
        raise RuntimeError(
            f"Expected {expected_count} retained backups, got {len(records)}."
        )
    if any(str(record["trigger"]).strip().upper() != "AUTO" for record in records):
        raise RuntimeError("Prepared backup records must all be AUTO-triggered.")

    print(
        {
            "database_path": str(database_path),
            "backup_dir": str(backup_dir),
            "retained_backup_ids": [str(record["backup_id"]) for record in records],
            "retained_created_at": [str(record["created_at"]) for record in records],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
