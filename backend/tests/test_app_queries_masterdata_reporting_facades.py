from __future__ import annotations

import unittest

from backend.app.api.routes import app_queries


class _StubMasterdataFacade:
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

    def list_line_daily_capacity(self, calendar_date: str, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_line_daily_capacity", (calendar_date,), kwargs))
        return {"calendar_date": calendar_date}

    def list_line_daily_capacity_audits(
        self,
        calendar_date: str,
        **kwargs: object,
    ) -> dict[str, object]:
        self.calls.append(("list_line_daily_capacity_audits", (calendar_date,), kwargs))
        return {"calendar_date": calendar_date, "audits": True}


class _StubReportingFacade:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def list_mes_reportings(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_mes_reportings", (), kwargs))
        return {"items": []}

    def list_reporting_import_files(self, *, limit: int = 50) -> dict[str, object]:
        self.calls.append(("list_reporting_import_files", (), {"limit": limit}))
        return {"items": [], "limit": limit}


class AppQueriesMasterdataReportingFacadesTestCase(unittest.TestCase):
    def test_masterdata_routes_delegate_to_masterdata_facade(self) -> None:
        facade = _StubMasterdataFacade()

        self.assertEqual(
            app_queries.get_masterdata_config(service=facade),
            {"data": {"config": True}},
        )
        self.assertEqual(
            app_queries.get_schedule_calendar_rules(service=facade),
            {"data": {"rules": True}},
        )
        self.assertEqual(
            app_queries.list_process_routes(service=facade),
            {"items": ["PROC-A"]},
        )
        self.assertEqual(
            app_queries.list_line_daily_capacity(
                service=facade,
                calendar_date="2026-04-19",
                workshop_code="WS-01",
                line_code="LINE-01",
                process_code="PROC-A",
                current_user={"role_code": "SCHEDULER"},
            ),
            {"calendar_date": "2026-04-19"},
        )
        self.assertEqual(
            app_queries.list_line_daily_capacity_audits(
                service=facade,
                calendar_date="2026-04-19",
                operator_keyword="alice",
                changed_only=True,
                current_user={"role_code": "SCHEDULER"},
            ),
            {"calendar_date": "2026-04-19", "audits": True},
        )
        self.assertEqual(
            [call[0] for call in facade.calls],
            [
                "get_masterdata_config",
                "get_schedule_calendar_rules",
                "list_process_routes",
                "list_line_daily_capacity",
                "list_line_daily_capacity_audits",
            ],
        )

    def test_reporting_routes_delegate_to_reporting_facade(self) -> None:
        facade = _StubReportingFacade()

        self.assertEqual(
            app_queries.list_mes_reportings(
                service=facade,
                start_time="2026-04-19T00:00:00+08:00",
                end_time="2026-04-19T23:59:59+08:00",
                current_user={"role_code": "SCHEDULER"},
            ),
            {"items": []},
        )
        self.assertEqual(
            app_queries.list_reporting_import_files(service=facade, limit=20),
            {"items": [], "limit": 20},
        )
        self.assertEqual(
            [call[0] for call in facade.calls],
            ["list_mes_reportings", "list_reporting_import_files"],
        )


if __name__ == "__main__":
    unittest.main()
