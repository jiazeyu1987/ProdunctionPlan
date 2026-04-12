from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from ..db import fetch_all, fetch_one, utc_now
from ..json_utils import dumps, loads


def _to_job(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": row["job_id"],
        "job_type": row["job_type"],
        "target_type": row["target_type"],
        "target_key": row["target_key"],
        "request_id": row["request_id"],
        "status": row["status"],
        "progress": row["progress"],
        "payload": loads(row["payload_json"]),
        "result": loads(row["result_json"]),
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


class JobRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def ensure_exists(self, job: dict[str, Any]) -> None:
        existing = self.get(str(job["job_id"]))
        if existing is not None:
            return
        self.connection.execute(
            """
            INSERT INTO jobs (
                job_id,
                job_type,
                target_type,
                target_key,
                request_id,
                status,
                progress,
                payload_json,
                result_json,
                error_code,
                error_message,
                created_at,
                started_at,
                finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(job["job_id"]),
                str(job["job_type"]),
                str(job["target_type"]),
                str(job["target_key"]),
                str(job.get("request_id") or "").strip() or None,
                str(job.get("status") or "RUNNING"),
                int(job.get("progress") or 5),
                dumps(job.get("payload") or {}),
                dumps(job.get("result") or {}) if job.get("result") is not None else None,
                str(job.get("error_code") or "").strip() or None,
                str(job.get("error_message") or "").strip() or None,
                str(job.get("created_at") or utc_now()),
                str(job.get("started_at") or utc_now()),
                str(job.get("finished_at") or "").strip() or None,
            ),
        )
        self.connection.commit()

    def enqueue(
        self,
        *,
        job_type: str,
        target_type: str,
        target_key: str,
        request_id: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if request_id:
            existing = self.get_by_request_id(request_id)
            if existing is not None:
                return existing

        job_id = uuid.uuid4().hex
        created_at = utc_now()
        self.connection.execute(
            """
            INSERT INTO jobs (
                job_id,
                job_type,
                target_type,
                target_key,
                request_id,
                status,
                progress,
                payload_json,
                result_json,
                error_code,
                error_message,
                created_at,
                started_at,
                finished_at
            ) VALUES (?, ?, ?, ?, ?, 'PENDING', 0, ?, NULL, NULL, NULL, ?, NULL, NULL)
            """,
            (
                job_id,
                job_type,
                target_type,
                target_key,
                request_id,
                dumps(payload),
                created_at,
            ),
        )
        self.connection.commit()
        return self.get(job_id)

    def get_by_request_id(self, request_id: str) -> dict[str, Any] | None:
        row = fetch_one(
            self.connection,
            """
            SELECT
                job_id,
                job_type,
                target_type,
                target_key,
                request_id,
                status,
                progress,
                payload_json,
                result_json,
                error_code,
                error_message,
                created_at,
                started_at,
                finished_at
            FROM jobs
            WHERE request_id = ?
            """,
            (request_id,),
        )
        return _to_job(row) if row else None

    def get(self, job_id: str) -> dict[str, Any] | None:
        row = fetch_one(
            self.connection,
            """
            SELECT
                job_id,
                job_type,
                target_type,
                target_key,
                request_id,
                status,
                progress,
                payload_json,
                result_json,
                error_code,
                error_message,
                created_at,
                started_at,
                finished_at
            FROM jobs
            WHERE job_id = ?
            """,
            (job_id,),
        )
        return _to_job(row) if row else None

    def list(
        self,
        *,
        status: str | None,
        job_type: str | None,
        target_key: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        where_clauses: list[str] = []
        parameters: list[object] = []

        if status:
            where_clauses.append("status = ?")
            parameters.append(status)
        if job_type:
            where_clauses.append("job_type = ?")
            parameters.append(job_type)
        if target_key:
            where_clauses.append("target_key = ?")
            parameters.append(target_key)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        rows = fetch_all(
            self.connection,
            f"""
            SELECT
                job_id,
                job_type,
                target_type,
                target_key,
                request_id,
                status,
                progress,
                payload_json,
                result_json,
                error_code,
                error_message,
                created_at,
                started_at,
                finished_at
            FROM jobs
            {where_sql}
            ORDER BY created_at DESC, job_id DESC
            LIMIT ?
            """,
            tuple(parameters + [limit]),
        )
        return [_to_job(row) for row in rows]

    def claim_next_pending(self) -> dict[str, Any] | None:
        self.connection.execute("BEGIN IMMEDIATE")
        row = fetch_one(
            self.connection,
            """
            SELECT
                job_id,
                job_type,
                target_type,
                target_key,
                request_id,
                status,
                progress,
                payload_json,
                result_json,
                error_code,
                error_message,
                created_at,
                started_at,
                finished_at
            FROM jobs
            WHERE status = 'PENDING'
            ORDER BY created_at ASC, job_id ASC
            LIMIT 1
            """,
        )
        if row is None:
            self.connection.rollback()
            return None

        started_at = utc_now()
        updated = self.connection.execute(
            """
            UPDATE jobs
            SET status = 'RUNNING', progress = 5, started_at = ?
            WHERE job_id = ? AND status = 'PENDING'
            """,
            (started_at, row["job_id"]),
        )
        if updated.rowcount != 1:
            self.connection.rollback()
            return None

        self.connection.commit()
        return self.get(str(row["job_id"]))

    def mark_succeeded(self, job_id: str, result: dict[str, Any]) -> None:
        self.connection.execute(
            """
            UPDATE jobs
            SET status = 'SUCCEEDED',
                progress = 100,
                result_json = ?,
                error_code = NULL,
                error_message = NULL,
                finished_at = ?
            WHERE job_id = ?
            """,
            (dumps(result), utc_now(), job_id),
        )
        self.connection.commit()

    def mark_failed(self, job_id: str, error_code: str, error_message: str) -> None:
        self.connection.execute(
            """
            UPDATE jobs
            SET status = 'FAILED',
                result_json = NULL,
                error_code = ?,
                error_message = ?,
                finished_at = ?
            WHERE job_id = ?
            """,
            (error_code, error_message, utc_now(), job_id),
        )
        self.connection.commit()
