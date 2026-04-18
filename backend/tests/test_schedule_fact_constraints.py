from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service import AppService


class ScheduleFactConstraintsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "schedule-fact-constraints.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.service = AppService(self.connection)
        self.service._ensure_masterdata_seeded = lambda: None  # type: ignore[method-assign]

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_terminology_current_saved_prefers_current_over_draft(self) -> None:
        self._seed_order("MO-TERM-001")
        self._seed_schedule_version("V-PUBLISHED-TERM-001", status="PUBLISHED", created_at="2026-04-13T00:00:00+00:00")
        self._seed_schedule_version("V-DRAFT-TERM-002", status="DRAFT", created_at="2026-04-14T00:00:00+00:00")

        payload = self.service.list_order_pool()

        self.assertEqual(payload["reference_version_no"], "V-PUBLISHED-TERM-001")
        self.assertEqual(payload["draft_version_no"], "V-DRAFT-TERM-002")

    def test_fixed_constraints_without_anchor_keep_reference_empty(self) -> None:
        self._seed_order("MO-FIXED-001", lock_flag=1, frozen_flag=1)
        self._seed_schedule_version("V-DRAFT-FIXED-001", status="DRAFT", created_at="2026-04-14T00:00:00+00:00")

        payload = self.service.list_order_pool()
        row = payload["items"][0]

        self.assertIsNone(payload["reference_version_no"])
        self.assertEqual(row["lock_flag"], 1)
        self.assertEqual(row["frozen_flag"], 1)
        self.assertEqual(payload["draft_version_no"], "V-DRAFT-FIXED-001")

    def _seed_order(self, order_no: str, *, lock_flag: int = 0, frozen_flag: int = 0) -> None:
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
                10,
                "OPEN",
                "2026-04-13",
                "2026-04-20",
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
                "2026-04-20",
                "2026-04-13",
                "2026-04-13T08:00:00+08:00",
                "2026-04-15T18:00:00+08:00",
                5,
                0,
                lock_flag,
                frozen_flag,
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

    def _seed_schedule_version(self, version_no: str, *, status: str, created_at: str) -> None:
        published_at = created_at if status == "PUBLISHED" else None
        self.connection.execute(
            """
            INSERT INTO schedule_versions (
                version_no,
                status,
                status_name_cn,
                strategy_code,
                created_at,
                published_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                version_no,
                status,
                status,
                "KEY_ORDER_FIRST",
                created_at,
                published_at,
            ),
        )
        self.connection.commit()
