from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database, load_init_sql, migrate_database_schema
from backend.app.repositories.jobs import JobRepository


class JobRepositoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "jobs.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        super().tearDown()

    def test_initialize_database_adds_error_details_column_for_legacy_jobs_table(self) -> None:
        legacy_sql = load_init_sql().replace("    error_details_json TEXT,\n", "")
        connection = sqlite3.connect(self.database_path)
        try:
            connection.executescript(legacy_sql)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")

            migrate_database_schema(connection)
            connection.commit()

            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
            }
        finally:
            connection.close()

        self.assertIn("error_details_json", columns)

    def test_mark_failed_persists_error_details(self) -> None:
        initialize_database(self.database_path)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            repository = JobRepository(connection)
            job = repository.enqueue(
                job_type="SCHEDULE_GENERATE",
                target_type="SCHEDULE_VERSION",
                target_key="NEW",
                request_id="job-request-001",
                payload={"request_id": "job-request-001"},
            )

            repository.mark_failed(
                str(job["job_id"]),
                "SCHEDULE_GENERATE_FAILED",
                "存在锁定或冻结订单未出现在基准版本中，已禁止继续重排。",
                {"order_nos": ["MO-LOCK-001", "MO-LOCK-002"]},
            )

            stored = repository.get(str(job["job_id"]))
        finally:
            connection.close()

        self.assertIsNotNone(stored)
        self.assertEqual(stored["status"], "FAILED")
        self.assertEqual(
            stored["error_details"],
            {"order_nos": ["MO-LOCK-001", "MO-LOCK-002"]},
        )


if __name__ == "__main__":
    unittest.main()
