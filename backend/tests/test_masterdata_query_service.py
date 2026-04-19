from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service_provider import create_app_service
from backend.app.services.masterdata_query_service import MasterdataQueryService


class MasterdataQueryServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "masterdata-query-service.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.host = create_app_service(self.connection)
        self.host._ensure_masterdata_seeded = lambda: None  # type: ignore[method-assign]
        self.service = MasterdataQueryService(self.host)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_list_line_daily_capacity_returns_empty_items(self) -> None:
        payload = self.service.list_line_daily_capacity("2026-04-19")
        self.assertEqual(payload["items"], [])

    def test_list_line_daily_capacity_audits_returns_empty_items(self) -> None:
        payload = self.service.list_line_daily_capacity_audits("2026-04-19")
        self.assertEqual(payload["items"], [])


if __name__ == "__main__":
    unittest.main()
