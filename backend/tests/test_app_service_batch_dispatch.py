from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.errors import AppError
from backend.app.services.app_service import AppService


class AppServiceBatchDispatchTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "batch-dispatch.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.service = AppService(self.connection)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_batch_lock_and_unlock_updates_state_and_audit_records(self) -> None:
        self._seed_order("MO-LOCK-001")
        self._seed_order("MO-LOCK-002")

        lock_result = self.service.batch_dispatch_commands(
            {
                "order_nos": ["MO-LOCK-001", "MO-LOCK-002"],
                "command_type": "LOCK",
                "actor": {"username": "scheduler_e2e"},
            }
        )

        self.assertEqual(lock_result["command_type"], "LOCK")
        self.assertEqual(lock_result["order_nos"], ["MO-LOCK-001", "MO-LOCK-002"])
        self.assertEqual(lock_result["count"], 2)
        self.assertEqual(self._lock_flags(), [("MO-LOCK-001", 1), ("MO-LOCK-002", 1)])
        self.assertEqual(
            self._dispatch_command_rows(),
            [
                ("MO-LOCK-001", "LOCK", "APPROVED", "scheduler_e2e", "scheduler_e2e"),
                ("MO-LOCK-002", "LOCK", "APPROVED", "scheduler_e2e", "scheduler_e2e"),
            ],
        )

        unlock_result = self.service.batch_dispatch_commands(
            {
                "order_nos": ["MO-LOCK-001", "MO-LOCK-002"],
                "command_type": "UNLOCK",
                "actor": {"username": "scheduler_e2e"},
            }
        )

        self.assertEqual(unlock_result["command_type"], "UNLOCK")
        self.assertEqual(unlock_result["count"], 2)
        self.assertEqual(self._lock_flags(), [("MO-LOCK-001", 0), ("MO-LOCK-002", 0)])
        self.assertEqual(len(self._dispatch_command_rows()), 4)

    def test_batch_lock_fails_when_selected_orders_have_mixed_lock_state(self) -> None:
        self._seed_order("MO-MIX-001")
        self._seed_order("MO-MIX-002", lock_flag=1)

        with self.assertRaises(AppError) as cm:
            self.service.batch_dispatch_commands(
                {
                    "order_nos": ["MO-MIX-001", "MO-MIX-002"],
                    "command_type": "LOCK",
                    "actor": {"username": "scheduler_e2e"},
                }
            )

        self.assertEqual(cm.exception.code, "ORDER_BATCH_DISPATCH_LOCK_STATE_INVALID")
        self.assertEqual(self._lock_flags(), [("MO-MIX-001", 0), ("MO-MIX-002", 1)])
        self.assertEqual(self._count_rows("dispatch_commands"), 0)

    def test_batch_dispatch_fails_for_completed_orders_without_partial_changes(self) -> None:
        self._seed_order(
            "MO-DONE-001",
            order_status="DONE",
            completed_qty=10,
            remaining_qty=0,
            progress_rate=100,
        )
        self._seed_order("MO-DONE-002")

        with self.assertRaises(AppError) as cm:
            self.service.batch_dispatch_commands(
                {
                    "order_nos": ["MO-DONE-001", "MO-DONE-002"],
                    "command_type": "LOCK",
                    "actor": {"username": "scheduler_e2e"},
                }
            )

        self.assertEqual(cm.exception.code, "ORDER_BATCH_DISPATCH_COMPLETED")
        self.assertEqual(self._lock_flags(), [("MO-DONE-001", 0), ("MO-DONE-002", 0)])
        self.assertEqual(self._count_rows("dispatch_commands"), 0)

    def test_batch_dispatch_fails_for_frozen_orders_without_partial_changes(self) -> None:
        self._seed_order("MO-FROZEN-001", frozen_flag=1)
        self._seed_order("MO-FROZEN-002")

        with self.assertRaises(AppError) as cm:
            self.service.batch_dispatch_commands(
                {
                    "order_nos": ["MO-FROZEN-001", "MO-FROZEN-002"],
                    "command_type": "LOCK",
                    "actor": {"username": "scheduler_e2e"},
                }
            )

        self.assertEqual(cm.exception.code, "ORDER_BATCH_DISPATCH_FROZEN")
        self.assertEqual(self._lock_flags(), [("MO-FROZEN-001", 0), ("MO-FROZEN-002", 0)])
        self.assertEqual(self._count_rows("dispatch_commands"), 0)

    def test_batch_priority_up_updates_priority_levels(self) -> None:
        self._seed_order("MO-PRI-001")
        self._seed_order("MO-PRI-002")

        result = self.service.batch_dispatch_commands(
            {
                "order_nos": ["MO-PRI-001", "MO-PRI-002"],
                "command_type": "PRIORITY_UP",
                "actor": {"username": "scheduler_e2e"},
            }
        )

        rows = self.connection.execute(
            """
            SELECT production_order_no, priority_level
            FROM order_pool_state
            WHERE production_order_no IN ('MO-PRI-001', 'MO-PRI-002')
            ORDER BY production_order_no
            """
        ).fetchall()
        self.assertEqual(result["command_type"], "PRIORITY_UP")
        self.assertEqual([(str(row[0]), int(row[1])) for row in rows], [("MO-PRI-001", 4), ("MO-PRI-002", 4)])

    def test_batch_priority_up_rejects_orders_already_at_highest_priority(self) -> None:
        self._seed_order("MO-PRI-HIGH", priority_level=1)
        self._seed_order("MO-PRI-NORMAL", priority_level=3)

        with self.assertRaises(AppError) as cm:
            self.service.batch_dispatch_commands(
                {
                    "order_nos": ["MO-PRI-HIGH", "MO-PRI-NORMAL"],
                    "command_type": "PRIORITY_UP",
                    "actor": {"username": "scheduler_e2e"},
                }
            )

        self.assertEqual(cm.exception.code, "ORDER_BATCH_DISPATCH_PRIORITY_STATE_INVALID")
        self.assertEqual(self._count_rows("dispatch_commands"), 0)

    def _seed_order(
        self,
        order_no: str,
        *,
        lock_flag: int = 0,
        frozen_flag: int = 0,
        priority_level: int = 5,
        order_status: str = "OPEN",
        completed_qty: float = 0,
        remaining_qty: float | None = None,
        progress_rate: float = 0,
    ) -> None:
        production_qty = 10.0
        next_remaining_qty = (
            remaining_qty if remaining_qty is not None else max(0.0, production_qty - completed_qty)
        )
        self.connection.execute(
            """
            INSERT INTO production_orders (
                production_order_no,
                material_code,
                material_name,
                material_specification,
                production_qty,
                status,
                planned_start_date,
                planned_end_date,
                source_bill_no,
                material_list_no,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_no,
                f"MAT-{order_no}",
                f"Material-{order_no}",
                "Spec-A",
                production_qty,
                order_status,
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
                production_order_no,
                promised_due_date,
                expected_start_date,
                expected_start_time,
                expected_finish_time,
                priority_level,
                urgent_flag,
                lock_flag,
                frozen_flag,
                status,
                order_status,
                completed_qty,
                remaining_qty,
                progress_rate,
                production_batch_no,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_no,
                "2026-04-15",
                "2026-04-13",
                "2026-04-13T08:00:00+08:00",
                "2026-04-15T18:00:00+08:00",
                priority_level,
                1 if priority_level <= 1 else 0,
                lock_flag,
                frozen_flag,
                order_status,
                order_status,
                completed_qty,
                next_remaining_qty,
                progress_rate,
                f"SRC-{order_no}-B1",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

    def _lock_flags(self) -> list[tuple[str, int]]:
        rows = self.connection.execute(
            """
            SELECT production_order_no, lock_flag
            FROM order_pool_state
            ORDER BY production_order_no
            """
        ).fetchall()
        return [(str(row[0]), int(row[1])) for row in rows]

    def _dispatch_command_rows(self) -> list[tuple[str, str, str, str | None, str | None]]:
        rows = self.connection.execute(
            """
            SELECT target_order_no, command_type, status, created_by, approver
            FROM dispatch_commands
            ORDER BY target_order_no ASC, created_at ASC, command_id ASC
            """
        ).fetchall()
        return [
            (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]) if row[3] is not None else None,
                str(row[4]) if row[4] is not None else None,
            )
            for row in rows
        ]

    def _count_rows(self, table_name: str) -> int:
        row = self.connection.execute(f"SELECT COUNT(1) FROM {table_name}").fetchone()
        return int(row[0] if row else 0)


if __name__ == "__main__":
    unittest.main()
