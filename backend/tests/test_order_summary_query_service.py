from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.auth import register_user
from backend.app.db import initialize_database
from backend.app.services.app_service_provider import create_app_service
from backend.app.services.order_summary_query_service import OrderSummaryQueryService


class OrderSummaryQueryServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "order-summary-query-service.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.host = create_app_service(self.connection)
        self.service = OrderSummaryQueryService(self.host)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_get_order_summary_returns_empty_payload_for_empty_range(self) -> None:
        payload = self.service.get_order_summary(
            start_date="2026-04-01",
            end_date="2026-04-30",
            current_user={"role_code": "SCHEDULER"},
        )

        self.assertEqual(payload["summary"]["order_count"], 0)
        self.assertEqual(payload["order_items"], [])
        self.assertEqual(payload["process_items"], [])

    def test_list_order_summary_workshop_managers_rejects_non_scheduler(self) -> None:
        with self.assertRaises(Exception) as ctx:
            self.service.list_order_summary_workshop_managers(
                current_user={"role_code": "WORKSHOP_MANAGER"},
            )

        self.assertEqual(getattr(ctx.exception, "code", None), "ORDER_SUMMARY_WORKSHOP_MANAGER_FILTER_FORBIDDEN")

    def test_list_order_summary_workshop_managers_returns_visible_managers(self) -> None:
        user = register_user(
            self.connection,
            {
                "username": "wm_visible",
                "password": "Passw0rd!",
                "display_name": "Visible Manager",
                "role_code": "WORKSHOP_MANAGER",
            },
        )
        self.connection.execute(
            """
            INSERT INTO app_user_line_scopes (
                user_id,
                company_code,
                workshop_code,
                line_code,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                user["user_id"],
                "COMPANY-MAIN",
                "WS-1",
                "LINE-1",
                "2026-04-01T00:00:00+00:00",
            ),
        )
        self.connection.commit()

        payload = self.service.list_order_summary_workshop_managers(
            current_user={"role_code": "SCHEDULER"},
        )

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["user_id"], user["user_id"])
        self.assertEqual(payload["items"][0]["display_name"], "Visible Manager")
        self.assertEqual(payload["items"][0]["line_scope_count"], 1)


if __name__ == "__main__":
    unittest.main()
