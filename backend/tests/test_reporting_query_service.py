from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service_provider import create_app_service
from backend.app.services.reporting_query_service import ReportingQueryService


class ReportingQueryServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "reporting-query-service.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.host = create_app_service(self.connection)
        self.service = ReportingQueryService(self.host)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_list_reporting_import_files_returns_empty_payload(self) -> None:
        payload = self.service.list_reporting_import_files(limit=20)
        self.assertEqual(payload, {"items": [], "total": 0})

    def test_list_mes_reportings_returns_empty_payload(self) -> None:
        payload = self.service.list_mes_reportings(
            start_time="2026-04-01T00:00:00+08:00",
            end_time="2026-04-30T23:59:59+08:00",
            current_user={"role_code": "SCHEDULER"},
        )
        self.assertEqual(payload, {"items": []})


if __name__ == "__main__":
    unittest.main()
