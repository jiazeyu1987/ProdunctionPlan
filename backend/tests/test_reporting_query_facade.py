from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.reporting_query_facade import ReportingQueryFacade
from backend.app.services.reporting_query_facade_provider import (
    create_reporting_query_facade,
)
from backend.app.services.reporting_query_service import ReportingQueryService


class _StubReportingAppService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def list_mes_reportings(
        self,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
        current_user: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "list_mes_reportings",
                (),
                {
                    "start_time": start_time,
                    "end_time": end_time,
                    "current_user": current_user,
                },
            ),
        )
        return {"items": []}

    def list_reporting_import_files(self, *, limit: int = 50) -> dict[str, object]:
        self.calls.append(("list_reporting_import_files", (), {"limit": limit}))
        return {"items": [], "limit": limit}


class ReportingQueryFacadeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "reporting-query-facade.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_create_reporting_query_facade_wraps_app_service(self) -> None:
        facade = create_reporting_query_facade(self.connection)

        self.assertIsInstance(facade, ReportingQueryFacade)
        self.assertIsInstance(facade.query_service, ReportingQueryService)
        self.assertIs(facade.query_service.connection, self.connection)

    def test_reporting_query_facade_delegates_to_app_service(self) -> None:
        service = _StubReportingAppService()
        facade = ReportingQueryFacade(service)  # type: ignore[arg-type]

        self.assertEqual(
            facade.list_mes_reportings(
                start_time="2026-04-19T00:00:00+08:00",
                end_time="2026-04-19T23:59:59+08:00",
                current_user={"role_code": "SCHEDULER"},
            ),
            {"items": []},
        )
        self.assertEqual(
            facade.list_reporting_import_files(limit=20),
            {"items": [], "limit": 20},
        )
        self.assertEqual(
            [call[0] for call in service.calls],
            ["list_mes_reportings", "list_reporting_import_files"],
        )


if __name__ == "__main__":
    unittest.main()
