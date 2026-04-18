from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service import AppService


class AppServiceGenerateScheduleUnlockedOnlyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "schedule-generate.db"
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

    def test_generate_schedule_ignores_locked_orders_missing_in_base_version(self) -> None:
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
                "MAT-001",
                1,
                "PROC-A",
                "工序A",
                "FS",
                "ROUTE-MAT-001",
                "测试路线",
                "测试物料一",
                0,
                "2026-04-13T00:00:00+00:00",
            ),
        )
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
                "WS-1",
                "车间1",
                "LINE-1",
                "产线1",
                "PROC-A",
                10,
                0,
                0,
                1,
                "2026-04-13T00:00:00+00:00",
            ),
        )

        orders = [
            ("MO-UNLOCK-001", "MAT-001", 5, 0),
            ("MO-LOCK-001", "MAT-001", 10, 1),
            ("MO-LOCK-MISSING", "MAT-NO-ROUTE", 5, 1),
        ]
        for order_no, material_code, qty, lock_flag in orders:
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
                    "测试物料",
                    "规格A",
                    qty,
                    "OPEN",
                    "2026-04-13",
                    "2026-04-20",
                    "SRC-001",
                    "ML-001",
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
                    "2026-04-20T18:00:00+08:00",
                    5,
                    0,
                    lock_flag,
                    0,
                    "OPEN",
                    "OPEN",
                    0,
                    qty,
                    0,
                    "BATCH-001",
                    "2026-04-13T00:00:00+00:00",
                ),
            )

        base_version_no = "BASE-V1"
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
                base_version_no,
                "PUBLISHED",
                "已发布",
                "KEY_ORDER_FIRST",
                "2026-04-13T00:00:00+00:00",
                "2026-04-13T00:00:00+00:00",
            ),
        )
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
                base_version_no,
                1,
                "MO-LOCK-001",
                "PROC-A",
                "工序A",
                "2026-04-13",
                "DAY",
                10,
                "2026-04-13T08:00:00+08:00",
            ),
        )
        self.connection.commit()

        generated = self.service.generate_schedule(
            {
                "base_version_no": base_version_no,
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "DEFAULT",
                "use_order_state_window": False,
            }
        )
        version_no = str(generated.get("version_no") or "").strip()
        self.assertTrue(version_no)

        tasks = self.connection.execute(
            """
            SELECT production_order_no, process_code, calendar_date, shift_code, plan_qty
            FROM schedule_tasks
            WHERE version_no = ?
            ORDER BY task_no ASC
            """,
            (version_no,),
        ).fetchall()
        task_map = [
            (
                str(row["production_order_no"]),
                str(row["process_code"]),
                str(row["calendar_date"]),
                str(row["shift_code"]),
                float(row["plan_qty"]),
            )
            for row in tasks
        ]

        self.assertIn(("MO-LOCK-001", "PROC-A", "2026-04-13", "DAY", 10.0), task_map)
        self.assertTrue(any(row[0] == "MO-UNLOCK-001" for row in task_map))
        self.assertFalse(any(row[0] == "MO-LOCK-MISSING" for row in task_map))

        unlock_task_dates = sorted({row[2] for row in task_map if row[0] == "MO-UNLOCK-001"})
        self.assertEqual(unlock_task_dates[0], "2026-04-14")

    def test_generate_schedule_clamps_open_order_start_to_simulation_current_day(self) -> None:
        self.service.factory.build_inventory_refresh_service = lambda: type(  # type: ignore[method-assign]
            "InventoryRefreshStub",
            (),
            {"refresh_inventory": staticmethod(lambda _codes: None)},
        )()
        self.connection.execute(
            """
            INSERT INTO simulation_state (
                singleton_key,
                current_date,
                updated_at
            ) VALUES (?, ?, ?)
            ON CONFLICT(singleton_key) DO UPDATE SET
                current_date = excluded.current_date,
                updated_at = excluded.updated_at
            """,
            ("default", "2026-04-18", "2026-04-18T00:00:00+00:00"),
        )
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
                "MAT-SIM-001",
                1,
                "PROC-A",
                "工序A",
                "FS",
                "ROUTE-MAT-SIM-001",
                "测试路线",
                "测试物料",
                1,
                "2026-04-18T00:00:00+00:00",
            ),
        )
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
                "WS-SIM",
                "车间SIM",
                "LINE-SIM",
                "产线SIM",
                "PROC-A",
                10,
                0,
                0,
                1,
                "2026-04-18T00:00:00+00:00",
            ),
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
                "MO-SIM-001",
                "MAT-SIM-001",
                "测试物料",
                "规格A",
                10,
                "OPEN",
                "2026-04-02",
                "2026-04-25",
                "SRC-SIM-001",
                "ML-SIM-001",
                "2026-04-18T00:00:00+00:00",
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
                "MO-SIM-001",
                "2026-04-25",
                "2026-04-02",
                "2026-04-02T08:00:00+08:00",
                "2026-04-25T18:00:00+08:00",
                5,
                0,
                0,
                0,
                "OPEN",
                "OPEN",
                0,
                10,
                0,
                "BATCH-SIM-001",
                "2026-04-18T00:00:00+00:00",
            ),
        )
        self.connection.commit()

        generated = self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "DEFAULT",
                "use_order_state_window": True,
            }
        )

        version_no = str(generated.get("version_no") or "").strip()
        first_task = self.connection.execute(
            """
            SELECT production_order_no, calendar_date, shift_code, plan_start_time
            FROM schedule_tasks
            WHERE version_no = ?
            ORDER BY task_no ASC
            LIMIT 1
            """,
            (version_no,),
        ).fetchone()

        self.assertIsNotNone(first_task)
        assert first_task is not None
        self.assertEqual(str(first_task["production_order_no"]), "MO-SIM-001")
        self.assertEqual(str(first_task["calendar_date"]), "2026-04-18")
        self.assertEqual(str(first_task["shift_code"]), "DAY")
        self.assertEqual(str(first_task["plan_start_time"]), "2026-04-18T08:00:00+08:00")
