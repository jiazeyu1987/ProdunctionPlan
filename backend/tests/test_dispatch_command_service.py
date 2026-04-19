from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.errors import AppError
from backend.app.services.app_service_provider import create_app_service
from backend.app.services.dispatch_command_service import DispatchCommandService


class DispatchCommandServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "dispatch-command-service.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.host = create_app_service(self.connection)
        self.service = DispatchCommandService(self.host)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_create_and_approve_dispatch_command(self) -> None:
        self._seed_order("MO-CMD-001")

        created = self.service.create_dispatch_command(
            {"target_order_no": "MO-CMD-001", "command_type": "LOCK"}
        )
        self.assertIn("command_id", created)

        approved = self.service.approve_dispatch_command(
            created["command_id"],
            {"approver": "scheduler", "decision": "APPROVED"},
        )
        self.assertEqual(approved, {"ok": True})

    def test_batch_dispatch_requires_order_nos(self) -> None:
        with self.assertRaises(AppError) as ctx:
            self.service.batch_dispatch_commands({"order_nos": [], "command_type": "LOCK"})

        self.assertEqual(ctx.exception.code, "ORDER_BATCH_DISPATCH_EMPTY")

    def _seed_order(self, order_no: str) -> None:
        self.connection.execute(
            """
            INSERT INTO production_orders (
                production_order_no, material_code, material_name, material_specification, production_qty,
                status, planned_start_date, planned_end_date, source_bill_no, material_list_no, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_no,
                f"MAT-{order_no}",
                "Material",
                "Spec",
                10,
                "OPEN",
                "2026-04-13",
                "2026-04-15",
                f"SRC-{order_no}",
                f"ML-{order_no}",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.execute(
            """
            INSERT INTO order_pool_state (
                production_order_no, promised_due_date, expected_start_date, expected_start_time, expected_finish_time,
                priority_level, urgent_flag, lock_flag, frozen_flag, status, order_status,
                completed_qty, remaining_qty, progress_rate, production_batch_no, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_no,
                "2026-04-15",
                "2026-04-13",
                "2026-04-13T08:00:00+08:00",
                "2026-04-15T18:00:00+08:00",
                5,
                0,
                0,
                0,
                "OPEN",
                "OPEN",
                0,
                10,
                0,
                f"SRC-{order_no}-B1",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()


if __name__ == "__main__":
    unittest.main()
