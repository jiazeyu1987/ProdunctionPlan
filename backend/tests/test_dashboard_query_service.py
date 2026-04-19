from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service_provider import create_app_service
from backend.app.services.dashboard_query_service import DashboardQueryService
from backend.app.services.order_summary_query_service import OrderSummaryQueryService


class DashboardQueryServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "dashboard-query-service.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.host = create_app_service(self.connection)
        self.service = DashboardQueryService(
            self.host,
            OrderSummaryQueryService(self.host),
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_get_scheduler_dashboard_requires_topology_rows(self) -> None:
        with self.assertRaises(Exception) as ctx:
            self.service.get_scheduler_dashboard(
                start_date="2026-04-01",
                end_date="2026-04-30",
                top_n=8,
                current_user={"role_code": "SCHEDULER"},
            )

        self.assertEqual(getattr(ctx.exception, "code", None), "DASHBOARD_TOPOLOGY_EMPTY")


if __name__ == "__main__":
    unittest.main()
