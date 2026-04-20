from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service_provider import create_app_service
from backend.app.services.dashboard_query_service import DashboardQueryService
from backend.app.services.order_summary_query_service import OrderSummaryQueryService


class _DashboardHostStub:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_line_daily_capacity(self, calendar_date: str) -> dict[str, object]:
        return {
            "items": [
                {
                    "calendar_date": calendar_date,
                    "line_code": "LINE-1",
                    "line_name": "1产线",
                    "process_code": "PROC-1",
                    "default_capacity_qty": 100,
                    "planned_capacity_qty": 80,
                    "actual_capacity_qty": 60,
                    "machine_count": 1,
                    "required_machines": 1,
                }
            ]
        }

    def _process_name_by_code(self) -> dict[str, str]:
        return {"PROC-1": "工序1"}


class _DashboardHostWithActualStub(_DashboardHostStub):
    def list_line_daily_capacity(self, calendar_date: str) -> dict[str, object]:
        actual_qty = 60 if calendar_date == "2026-04-01" else 90
        return {
            "items": [
                {
                    "calendar_date": calendar_date,
                    "line_code": "LINE-1",
                    "line_name": "1产线",
                    "process_code": "PROC-1",
                    "default_capacity_qty": 100,
                    "planned_capacity_qty": 80,
                    "actual_capacity_qty": actual_qty,
                    "machine_count": 1,
                    "required_machines": 1,
                }
            ]
        }


class _DashboardHostActualLoadStub(_DashboardHostStub):
    def list_line_daily_capacity(self, calendar_date: str) -> dict[str, object]:
        if calendar_date == "2026-04-01":
            return {
                "items": [
                    {
                        "calendar_date": calendar_date,
                        "line_code": "LINE-1",
                        "line_name": "1产线",
                        "process_code": "PROC-1",
                        "default_capacity_qty": 100,
                        "planned_capacity_qty": 140,
                        "actual_capacity_qty": 50,
                        "machine_count": 1,
                        "required_machines": 1,
                    },
                    {
                        "calendar_date": calendar_date,
                        "line_code": "LINE-2",
                        "line_name": "2产线",
                        "process_code": "PROC-2",
                        "default_capacity_qty": 100,
                        "planned_capacity_qty": 80,
                        "actual_capacity_qty": 130,
                        "machine_count": 1,
                        "required_machines": 1,
                    },
                ]
            }
        return {
            "items": [
                {
                    "calendar_date": calendar_date,
                    "line_code": "LINE-1",
                    "line_name": "1产线",
                    "process_code": "PROC-1",
                    "default_capacity_qty": 100,
                    "planned_capacity_qty": 70,
                    "actual_capacity_qty": 160,
                    "machine_count": 1,
                    "required_machines": 1,
                },
                {
                    "calendar_date": calendar_date,
                    "line_code": "LINE-2",
                    "line_name": "2产线",
                    "process_code": "PROC-2",
                    "default_capacity_qty": 100,
                    "planned_capacity_qty": 120,
                    "actual_capacity_qty": 40,
                    "machine_count": 1,
                    "required_machines": 1,
                },
            ]
        }

    def _process_name_by_code(self) -> dict[str, str]:
        return {"PROC-1": "工序1", "PROC-2": "工序2"}


class _OrderSummaryServiceStub:
    def get_order_summary(self, **_: object) -> dict[str, object]:
        return {
            "summary": {
                "order_count": 1,
                "completed_order_count": 0,
                "completion_rate": 0,
            },
            "order_items": [
                {
                    "order_no": "MO-1",
                }
            ],
        }


class _EmptyOrderSummaryServiceStub:
    def get_order_summary(self, **_: object) -> dict[str, object]:
        return {
            "summary": {
                "order_count": 0,
                "completed_order_count": 0,
                "completion_rate": 0,
            },
            "order_items": [],
            "process_items": [],
        }


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

    def test_get_scheduler_dashboard_returns_empty_material_consumption_when_material_rows_are_missing(self) -> None:
        self.connection.execute(
            """
            INSERT INTO masterdata_line_topology (
                company_code,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                process_code,
                capacity_per_shift,
                required_workers,
                required_machines,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "COMPANY-A",
                "WS-1",
                "1车间",
                "LINE-1",
                "1产线",
                "PROC-1",
                100,
                1,
                1,
                "2026-04-01T00:00:00+00:00",
            ),
        )
        self.connection.commit()
        service = DashboardQueryService(
            _DashboardHostStub(self.connection),
            _OrderSummaryServiceStub(),
        )

        result = service.get_scheduler_dashboard(
            start_date="2026-04-01",
            end_date="2026-04-01",
            top_n=8,
            current_user={"role_code": "SCHEDULER"},
        )

        material_payload = result.get("material_consumption")
        self.assertIsInstance(material_payload, dict)
        assert isinstance(material_payload, dict)
        self.assertEqual(material_payload.get("top_n"), 8)
        self.assertEqual(material_payload.get("items"), [])
        summary = result.get("summary")
        self.assertIsInstance(summary, dict)
        assert isinstance(summary, dict)
        self.assertEqual(summary.get("order_count"), 1)
        self.assertEqual(summary.get("total_capacity_qty"), 80.0)

    def test_get_scheduler_dashboard_allows_empty_order_summary_rows(self) -> None:
        self.connection.execute(
            """
            INSERT INTO masterdata_line_topology (
                company_code,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                process_code,
                capacity_per_shift,
                required_workers,
                required_machines,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "COMPANY-A",
                "WS-1",
                "1车间",
                "LINE-1",
                "1产线",
                "PROC-1",
                100,
                1,
                1,
                "2026-04-01T00:00:00+00:00",
            ),
        )
        self.connection.commit()
        service = DashboardQueryService(
            _DashboardHostStub(self.connection),
            _EmptyOrderSummaryServiceStub(),
        )

        result = service.get_scheduler_dashboard(
            start_date="2026-04-01",
            end_date="2026-04-01",
            top_n=8,
            current_user={"role_code": "SCHEDULER"},
        )

        summary = result.get("summary")
        self.assertIsInstance(summary, dict)
        assert isinstance(summary, dict)
        self.assertEqual(summary.get("order_count"), 0)
        self.assertEqual(summary.get("completed_order_count"), 0)
        self.assertEqual(summary.get("order_completion_rate"), 0)
        self.assertEqual(summary.get("total_capacity_qty"), 80.0)
        material_payload = result.get("material_consumption")
        self.assertIsInstance(material_payload, dict)
        assert isinstance(material_payload, dict)
        self.assertEqual(material_payload.get("items"), [])

    def test_get_scheduler_dashboard_includes_actual_capacity_in_line_and_process_series(self) -> None:
        self.connection.execute(
            """
            INSERT INTO masterdata_line_topology (
                company_code,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                process_code,
                capacity_per_shift,
                required_workers,
                required_machines,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "COMPANY-A",
                "WS-1",
                "1车间",
                "LINE-1",
                "1产线",
                "PROC-1",
                100,
                1,
                1,
                "2026-04-01T00:00:00+00:00",
            ),
        )
        self.connection.commit()
        service = DashboardQueryService(
            _DashboardHostWithActualStub(self.connection),
            _OrderSummaryServiceStub(),
        )

        result = service.get_scheduler_dashboard(
            start_date="2026-04-01",
            end_date="2026-04-02",
            top_n=8,
            current_user={"role_code": "SCHEDULER"},
        )

        line_items = result["capacity_change_by_line"]["items"]
        process_items = result["capacity_change_by_process"]["items"]
        self.assertEqual(line_items[0]["actual_capacity_qty"], 60)
        self.assertEqual(line_items[1]["actual_capacity_qty"], 90)
        self.assertEqual(process_items[0]["actual_capacity_qty"], 60)
        self.assertEqual(process_items[1]["actual_capacity_qty"], 90)

    def test_get_scheduler_dashboard_cockpit_uses_actual_reporting_load(self) -> None:
        self.connection.executemany(
            """
            INSERT INTO masterdata_line_topology (
                company_code,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                process_code,
                capacity_per_shift,
                required_workers,
                required_machines,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "COMPANY-A",
                    "WS-1",
                    "1车间",
                    "LINE-1",
                    "1产线",
                    "PROC-1",
                    100,
                    1,
                    1,
                    "2026-04-01T00:00:00+00:00",
                ),
                (
                    "COMPANY-A",
                    "WS-1",
                    "1车间",
                    "LINE-2",
                    "2产线",
                    "PROC-2",
                    100,
                    1,
                    1,
                    "2026-04-01T00:00:00+00:00",
                ),
            ],
        )
        self.connection.commit()
        service = DashboardQueryService(
            _DashboardHostActualLoadStub(self.connection),
            _OrderSummaryServiceStub(),
        )

        result = service.get_scheduler_dashboard(
            start_date="2026-04-01",
            end_date="2026-04-02",
            top_n=8,
            current_user={"role_code": "SCHEDULER"},
        )

        pressure_items = result["cockpit"]["daily_pressure_items"]
        overload_items = result["cockpit"]["line_overload_items"]
        bottleneck_items = result["cockpit"]["process_bottleneck_items"]
        summary = result["cockpit"]["summary"]

        self.assertEqual(pressure_items[0]["overload_qty"], 0.0)
        self.assertEqual(pressure_items[0]["idle_qty"], 20.0)
        self.assertEqual(pressure_items[0]["overload_line_count"], 1)
        self.assertEqual(pressure_items[1]["overload_qty"], 0.0)
        self.assertEqual(pressure_items[1]["idle_qty"], 0.0)
        self.assertEqual(summary["peak_overload_date"], "2026-04-02")
        self.assertEqual(summary["top_overload_line_code"], "LINE-1")
        self.assertEqual(overload_items[0]["line_code"], "LINE-1")
        self.assertEqual(overload_items[0]["overload_qty"], 60.0)
        self.assertEqual(bottleneck_items[0]["process_code"], "PROC-1")
        self.assertEqual(bottleneck_items[0]["peak_actual_capacity_qty"], 160.0)
        self.assertEqual(bottleneck_items[0]["peak_utilization_rate"], 160.0)


if __name__ == "__main__":
    unittest.main()
