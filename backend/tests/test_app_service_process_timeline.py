from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service import AppService


class AppServiceProcessTimelineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "process-timeline.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.service = AppService(self.connection)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_get_order_pool_process_timeline_includes_version_wide_process_stats(self) -> None:
        self._seed_order("MO-PT-001", material_code="MAT-001", production_qty=120)
        self._seed_order("MO-PT-002", material_code="MAT-002", production_qty=30)
        self._seed_schedule_version("V-PT-001")

        self._seed_schedule_task(
            task_no=1,
            order_no="MO-PT-001",
            process_code="PROC-A",
            process_name_cn="工序A",
            calendar_date="2026-04-13",
            shift_code="DAY",
            plan_qty=80,
            plan_start_time="2026-04-13T08:00:00+08:00",
        )
        self._seed_schedule_task(
            task_no=2,
            order_no="MO-PT-001",
            process_code="PROC-A",
            process_name_cn="工序A",
            calendar_date="2026-04-13",
            shift_code="NIGHT",
            plan_qty=40,
            plan_start_time="2026-04-13T20:00:00+08:00",
        )
        self._seed_schedule_task(
            task_no=3,
            order_no="MO-PT-002",
            process_code="PROC-A",
            process_name_cn="工序A",
            calendar_date="2026-04-14",
            shift_code="DAY",
            plan_qty=30,
            plan_start_time="2026-04-14T08:00:00+08:00",
        )
        self._seed_schedule_task(
            task_no=4,
            order_no="MO-PT-001",
            process_code="PROC-B",
            process_name_cn="工序B",
            calendar_date="2026-04-14",
            shift_code="DAY",
            plan_qty=55,
            plan_start_time="2026-04-14T08:00:00+08:00",
        )

        result = self.service.get_order_pool_process_timeline("MO-PT-001")

        process_items = {
            str(item["process_code"]): item for item in result["process_items"]
        }
        self.assertEqual(sorted(process_items.keys()), ["PROC-A", "PROC-B"])

        process_a = process_items["PROC-A"]
        self.assertEqual(process_a["process_name_cn"], "工序A")
        self.assertEqual(process_a["related_order_count"], 2)
        self.assertEqual(process_a["plan_qty_total"], 150.0)
        self.assertEqual(process_a["duration_hours"], 24.0)

        process_b = process_items["PROC-B"]
        self.assertEqual(process_b["process_name_cn"], "工序B")
        self.assertEqual(process_b["related_order_count"], 1)
        self.assertEqual(process_b["plan_qty_total"], 55.0)
        self.assertEqual(process_b["duration_hours"], 12.0)

    def test_get_order_pool_process_timeline_returns_empty_when_no_reference_version_exists(self) -> None:
        self._seed_order("MO-PT-EMPTY", material_code="MAT-EMPTY", production_qty=10)

        result = self.service.get_order_pool_process_timeline("MO-PT-EMPTY")

        self.assertEqual(result["summary"]["reference_version_no"], None)
        self.assertEqual(result["process_items"], [])
        self.assertEqual(result["selected_process_detail"], None)

    def test_get_order_pool_process_timeline_returns_empty_when_reference_version_has_no_tasks(self) -> None:
        self._seed_order("MO-PT-NO-TASK", material_code="MAT-NO-TASK", production_qty=20)
        self._seed_schedule_version("V-PT-EMPTY")

        result = self.service.get_order_pool_process_timeline("MO-PT-NO-TASK")

        self.assertEqual(result["summary"]["reference_version_no"], "V-PT-EMPTY")
        self.assertEqual(result["process_items"], [])
        self.assertEqual(result["selected_process_detail"], None)

    def _seed_order(
        self,
        order_no: str,
        *,
        material_code: str,
        production_qty: float,
    ) -> None:
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
                material_code,
                f"Material-{order_no}",
                "Spec-A",
                production_qty,
                "OPEN",
                "2026-04-13",
                "2026-04-20",
                f"SRC-{order_no}",
                f"ML-{order_no}",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

    def _seed_schedule_version(self, version_no: str) -> None:
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
                "PUBLISHED",
                "已发布",
                "KEY_ORDER_FIRST",
                "2026-04-13T00:00:00+00:00",
                "2026-04-13T00:05:00+00:00",
            ),
        )
        self.connection.commit()

    def _seed_schedule_task(
        self,
        *,
        task_no: int,
        order_no: str,
        process_code: str,
        process_name_cn: str,
        calendar_date: str,
        shift_code: str,
        plan_qty: float,
        plan_start_time: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO schedule_tasks (
                version_no,
                task_no,
                production_order_no,
                process_code,
                process_name_cn,
                calendar_date,
                shift_code,
                plan_qty,
                plan_start_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "V-PT-001",
                task_no,
                order_no,
                process_code,
                process_name_cn,
                calendar_date,
                shift_code,
                plan_qty,
                plan_start_time,
            ),
        )
        self.connection.commit()


if __name__ == "__main__":
    unittest.main()
