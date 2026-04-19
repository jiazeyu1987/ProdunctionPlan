from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.order_summary_query_facade import OrderSummaryQueryFacade
from backend.app.services.order_summary_query_facade_provider import (
    create_order_summary_query_facade,
)
from backend.app.services.order_summary_query_service import OrderSummaryQueryService


class _StubOrderSummaryAppService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_order_summary(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("get_order_summary", dict(kwargs)))
        return {"items": []}

    def list_order_summary_workshop_managers(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_order_summary_workshop_managers", dict(kwargs)))
        return {"items": ["manager-a"]}


class OrderSummaryQueryFacadeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "order-summary-query-facade.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_create_order_summary_query_facade_wraps_app_service(self) -> None:
        facade = create_order_summary_query_facade(self.connection)
        self.assertIsInstance(facade, OrderSummaryQueryFacade)
        self.assertIsInstance(facade.query_service, OrderSummaryQueryService)

    def test_order_summary_query_facade_delegates(self) -> None:
        service = _StubOrderSummaryAppService()
        facade = OrderSummaryQueryFacade(service)  # type: ignore[arg-type]
        self.assertEqual(
            facade.get_order_summary(
                start_date="2026-04-01",
                end_date="2026-04-30",
                workshop_manager_user_id="wm-1",
                current_user={"role_code": "SCHEDULER"},
            ),
            {"items": []},
        )
        self.assertEqual(
            facade.list_order_summary_workshop_managers(current_user={"role_code": "SCHEDULER"}),
            {"items": ["manager-a"]},
        )
        self.assertEqual(
            [call[0] for call in service.calls],
            ["get_order_summary", "list_order_summary_workshop_managers"],
        )


if __name__ == "__main__":
    unittest.main()
