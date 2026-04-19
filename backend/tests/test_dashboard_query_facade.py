from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.dashboard_query_facade import DashboardQueryFacade
from backend.app.services.dashboard_query_facade_provider import create_dashboard_query_facade
from backend.app.services.dashboard_query_service import DashboardQueryService


class _StubDashboardAppService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_scheduler_dashboard(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("get_scheduler_dashboard", dict(kwargs)))
        return {"summary": {"ok": True}}


class DashboardQueryFacadeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "dashboard-query-facade.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_create_dashboard_query_facade_wraps_app_service(self) -> None:
        facade = create_dashboard_query_facade(self.connection)
        self.assertIsInstance(facade, DashboardQueryFacade)
        self.assertIsInstance(facade.query_service, DashboardQueryService)

    def test_dashboard_query_facade_delegates(self) -> None:
        service = _StubDashboardAppService()
        facade = DashboardQueryFacade(service)  # type: ignore[arg-type]
        self.assertEqual(
            facade.get_scheduler_dashboard(
                start_date="2026-04-01",
                end_date="2026-04-30",
                top_n=8,
                current_user={"role_code": "SCHEDULER"},
            ),
            {"summary": {"ok": True}},
        )
        self.assertEqual([call[0] for call in service.calls], ["get_scheduler_dashboard"])


if __name__ == "__main__":
    unittest.main()
