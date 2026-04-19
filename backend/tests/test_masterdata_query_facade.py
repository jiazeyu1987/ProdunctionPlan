from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.masterdata_query_facade import MasterdataQueryFacade
from backend.app.services.masterdata_query_facade_provider import (
    create_masterdata_query_facade,
)
from backend.app.services.masterdata_query_service import MasterdataQueryService


class _StubMasterdataAppService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def get_masterdata_config(self) -> dict[str, object]:
        self.calls.append(("get_masterdata_config", (), {}))
        return {"data": {"config": True}}

    def get_schedule_calendar_rules(self) -> dict[str, object]:
        self.calls.append(("get_schedule_calendar_rules", (), {}))
        return {"data": {"rules": True}}

    def list_process_routes(self) -> dict[str, object]:
        self.calls.append(("list_process_routes", (), {}))
        return {"items": ["PROC-A"]}

    def list_line_daily_capacity(
        self,
        calendar_date: str,
        *,
        workshop_code: str | None = None,
        line_code: str | None = None,
        process_code: str | None = None,
        current_user: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "list_line_daily_capacity",
                (calendar_date,),
                {
                    "workshop_code": workshop_code,
                    "line_code": line_code,
                    "process_code": process_code,
                    "current_user": current_user,
                },
            ),
        )
        return {"calendar_date": calendar_date}

    def list_line_daily_capacity_audits(
        self,
        calendar_date: str,
        *,
        workshop_code: str | None = None,
        line_code: str | None = None,
        process_code: str | None = None,
        operator_keyword: str | None = None,
        changed_only: bool = False,
        current_user: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "list_line_daily_capacity_audits",
                (calendar_date,),
                {
                    "workshop_code": workshop_code,
                    "line_code": line_code,
                    "process_code": process_code,
                    "operator_keyword": operator_keyword,
                    "changed_only": changed_only,
                    "current_user": current_user,
                },
            ),
        )
        return {"calendar_date": calendar_date, "audits": True}


class MasterdataQueryFacadeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "masterdata-query-facade.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_create_masterdata_query_facade_wraps_app_service(self) -> None:
        facade = create_masterdata_query_facade(self.connection)

        self.assertIsInstance(facade, MasterdataQueryFacade)
        self.assertIsInstance(facade.query_service, MasterdataQueryService)
        self.assertIs(facade.query_service.host.connection, self.connection)

    def test_masterdata_query_facade_delegates_to_app_service(self) -> None:
        service = _StubMasterdataAppService()
        facade = MasterdataQueryFacade(service)  # type: ignore[arg-type]

        self.assertEqual(facade.get_masterdata_config(), {"data": {"config": True}})
        self.assertEqual(facade.get_schedule_calendar_rules(), {"data": {"rules": True}})
        self.assertEqual(facade.list_process_routes(), {"items": ["PROC-A"]})
        self.assertEqual(
            facade.list_line_daily_capacity(
                "2026-04-19",
                workshop_code="WS-01",
                line_code="LINE-01",
                process_code="PROC-A",
                current_user={"role_code": "SCHEDULER"},
            ),
            {"calendar_date": "2026-04-19"},
        )
        self.assertEqual(
            facade.list_line_daily_capacity_audits(
                "2026-04-19",
                operator_keyword="alice",
                changed_only=True,
                current_user={"role_code": "SCHEDULER"},
            ),
            {"calendar_date": "2026-04-19", "audits": True},
        )
        self.assertEqual(
            [call[0] for call in service.calls],
            [
                "get_masterdata_config",
                "get_schedule_calendar_rules",
                "list_process_routes",
                "list_line_daily_capacity",
                "list_line_daily_capacity_audits",
            ],
        )


if __name__ == "__main__":
    unittest.main()
