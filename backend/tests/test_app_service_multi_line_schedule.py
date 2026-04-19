from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service import AppService


class AppServiceMultiLineScheduleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "multi-line-schedule.db"
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

    def test_generate_schedule_distributes_same_process_across_candidate_lines(self) -> None:
        self._seed_route_and_topology("MAT-A", "PROC-A", [("WS-1", "LINE-1"), ("WS-1", "LINE-2")], 10)
        self._seed_order("MO-001", "MAT-A", 15)

        generated = self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "DEFAULT",
                "use_order_state_window": True,
            }
        )

        rows = self.connection.execute(
            """
            SELECT workshop_code, line_code, plan_qty
            FROM schedule_tasks
            WHERE version_no = ?
            ORDER BY task_no
            """,
            (generated["version_no"],),
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in rows],
            [("WS-1", "LINE-1", 10.0), ("WS-1", "LINE-2", 5.0)],
        )

    def test_generate_schedule_skips_locked_order(self) -> None:
        self._seed_route_and_topology("MAT-A", "PROC-A", [("WS-1", "LINE-1")], 10)
        self._seed_order("MO-OPEN-001", "MAT-A", 10)
        self._seed_order("MO-LOCK-001", "MAT-A", 10, lock_flag=1)

        generated = self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "DEFAULT",
                "use_order_state_window": True,
            }
        )

        rows = self.connection.execute(
            """
            SELECT production_order_no
            FROM schedule_tasks
            WHERE version_no = ?
            ORDER BY task_no
            """,
            (generated["version_no"],),
        ).fetchall()
        self.assertEqual([str(row["production_order_no"]) for row in rows], ["MO-OPEN-001"])

    def _seed_route_and_topology(
        self,
        product_code: str,
        process_code: str,
        line_pairs: list[tuple[str, str]],
        capacity_per_shift: int,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO masterdata_process_routes (
                product_code,
                sequence_no,
                process_code,
                process_name_cn,
                dependency_type,
                route_no,
                route_name_cn,
                product_name_cn,
                is_final_process,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_code,
                1,
                process_code,
                "工序A",
                "FS",
                f"ROUTE-{product_code}",
                "测试路线",
                "测试产品",
                1,
                "2026-04-13T00:00:00+00:00",
            ),
        )
        for workshop_code, line_code in line_pairs:
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
                    enabled_flag,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "COMPANY-MAIN",
                    workshop_code,
                    workshop_code,
                    line_code,
                    line_code,
                    process_code,
                    capacity_per_shift,
                    1,
                    0,
                    1,
                    "2026-04-13T00:00:00+00:00",
                ),
            )
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
                "V-BASE-001",
                "PUBLISHED",
                "已发布",
                "KEY_ORDER_FIRST",
                "2026-04-13T00:00:00+00:00",
                "2026-04-13T00:10:00+00:00",
            ),
        )
        self.connection.commit()

    def _seed_order(self, order_no: str, material_code: str, quantity: int, *, lock_flag: int = 0) -> None:
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
                "测试产品",
                "规格A",
                quantity,
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
                5,
                0,
                lock_flag,
                0,
                "OPEN",
                "OPEN",
                0,
                quantity,
                0,
                f"SRC-{order_no}-B1",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()


if __name__ == "__main__":
    unittest.main()
