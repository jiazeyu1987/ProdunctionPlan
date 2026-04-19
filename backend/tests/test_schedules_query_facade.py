from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.schedules_query_facade import SchedulesQueryFacade
from backend.app.services.schedules_query_facade_provider import create_schedules_query_facade
from backend.app.services.schedules_query_service import SchedulesQueryService


class _StubSchedulesAppService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_current_schedule(self) -> dict[str, object]:
        self.calls.append("get_current_schedule")
        return {"data": {"current": True}}

    def list_current_schedule_tasks(self) -> dict[str, object]:
        self.calls.append("list_current_schedule_tasks")
        return {"items": []}

    def list_schedule_snapshots(self) -> dict[str, object]:
        self.calls.append("list_schedule_snapshots")
        return {"items": ["SNAP-1"]}


class SchedulesQueryFacadeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "schedules-query-facade.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_create_schedules_query_facade_wraps_app_service(self) -> None:
        facade = create_schedules_query_facade(self.connection)
        self.assertIsInstance(facade, SchedulesQueryFacade)
        self.assertIsInstance(facade.query_service, SchedulesQueryService)

    def test_schedules_query_facade_delegates(self) -> None:
        service = _StubSchedulesAppService()
        facade = SchedulesQueryFacade(service)  # type: ignore[arg-type]
        self.assertEqual(facade.get_current_schedule(), {"data": {"current": True}})
        self.assertEqual(facade.list_current_schedule_tasks(), {"items": []})
        self.assertEqual(facade.list_schedule_snapshots(), {"items": ["SNAP-1"]})
        self.assertEqual(
            service.calls,
            [
                "get_current_schedule",
                "list_current_schedule_tasks",
                "list_schedule_snapshots",
            ],
        )


if __name__ == "__main__":
    unittest.main()
