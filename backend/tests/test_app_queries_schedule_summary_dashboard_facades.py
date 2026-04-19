from __future__ import annotations

import unittest

from backend.app.api.routes import app_queries


class _StubSchedulesFacade:
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


class _StubOrderSummaryFacade:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_order_summary(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("get_order_summary", dict(kwargs)))
        return {"items": []}

    def list_order_summary_workshop_managers(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_order_summary_workshop_managers", dict(kwargs)))
        return {"items": ["manager-a"]}


class _StubDashboardFacade:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_scheduler_dashboard(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("get_scheduler_dashboard", dict(kwargs)))
        return {"summary": {"ok": True}}


class AppQueriesScheduleSummaryDashboardFacadesTestCase(unittest.TestCase):
    def test_schedule_routes_delegate_to_schedules_facade(self) -> None:
        facade = _StubSchedulesFacade()
        self.assertEqual(
            app_queries.get_current_schedule(service=facade),
            {"data": {"current": True}},
        )
        self.assertEqual(
            app_queries.list_current_schedule_tasks(service=facade),
            {"items": []},
        )
        self.assertEqual(
            app_queries.list_schedule_snapshots(service=facade),
            {"items": ["SNAP-1"]},
        )
        self.assertEqual(
            facade.calls,
            [
                "get_current_schedule",
                "list_current_schedule_tasks",
                "list_schedule_snapshots",
            ],
        )

    def test_order_summary_and_dashboard_routes_delegate_to_facades(self) -> None:
        order_summary_facade = _StubOrderSummaryFacade()
        dashboard_facade = _StubDashboardFacade()
        self.assertEqual(
            app_queries.get_order_summary(
                service=order_summary_facade,
                start_date="2026-04-01",
                end_date="2026-04-30",
                workshop_manager_user_id="wm-1",
                current_user={"role_code": "SCHEDULER"},
            ),
            {"items": []},
        )
        self.assertEqual(
            app_queries.list_order_summary_workshop_managers(
                service=order_summary_facade,
                current_user={"role_code": "SCHEDULER"},
            ),
            {"items": ["manager-a"]},
        )
        self.assertEqual(
            app_queries.get_scheduler_dashboard(
                service=dashboard_facade,
                start_date="2026-04-01",
                end_date="2026-04-30",
                top_n=8,
                current_user={"role_code": "SCHEDULER"},
            ),
            {"summary": {"ok": True}},
        )
        self.assertEqual(
            [call[0] for call in order_summary_facade.calls],
            ["get_order_summary", "list_order_summary_workshop_managers"],
        )
        self.assertEqual(
            [call[0] for call in dashboard_facade.calls],
            ["get_scheduler_dashboard"],
        )


if __name__ == "__main__":
    unittest.main()
