from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.errors import AppError
from backend.app.services.app_service import AppService


class AppServiceScheduleTrustTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "schedule-trust.db"
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

    def test_patch_expected_start_date_does_not_change_promised_due_date(self) -> None:
        self._seed_order("MO-PATCH-001", expected_start_date="2026-04-13")

        result = self.service.patch_order_pool_order(
            "MO-PATCH-001",
            {"expected_start_date": "2026-04-15"},
        )

        self.assertEqual(result["promised_due_date"], "2026-04-20")
        self.assertEqual(result["expected_start_date"], "2026-04-15")
        self.assertEqual(result["expected_start_time"], "2026-04-15T08:00:00+08:00")
        self.assertEqual(result["expected_finish_time"], "2026-04-20T18:00:00+08:00")

    def test_generate_schedule_uses_manual_expected_start_date_when_enabled(self) -> None:
        self._seed_route_and_topology("MAT-STATE", "PROC-A", capacity_per_shift=10)
        self._seed_order(
            "MO-STATE-001",
            material_code="MAT-STATE",
            quantity=10,
            expected_start_date="2026-04-16",
        )

        generated = self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "DEFAULT",
                "use_order_state_window": True,
            }
        )

        tasks = self._list_schedule_tasks(str(generated["version_no"]))
        self.assertEqual(tasks[0]["calendar_date"], "2026-04-16")

    def test_generate_schedule_limits_daily_capacity_across_shifts(self) -> None:
        self._seed_route_and_topology("MAT-DAY", "PROC-A", capacity_per_shift=10)
        self._seed_order(
            "MO-DAY-001",
            material_code="MAT-DAY",
            quantity=15,
            expected_start_date="2026-04-13",
        )
        self.connection.execute(
            """
            INSERT INTO daily_line_capacity_plan (
                calendar_date,
                company_code,
                workshop_code,
                line_code,
                process_code,
                planned_capacity_qty,
                worker_count,
                machine_count,
                source_note,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-04-13",
                "COMPANY-MAIN",
                "WS-1",
                "LINE-1",
                "PROC-A",
                10,
                1,
                0,
                "MANUAL",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

        generated = self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "PLANNED",
                "use_order_state_window": True,
            }
        )

        tasks = self._list_schedule_tasks(str(generated["version_no"]))
        first_day_qty = sum(
            float(row["plan_qty"])
            for row in tasks
            if str(row["calendar_date"]) == "2026-04-13"
        )
        self.assertEqual(first_day_qty, 10.0)
        self.assertEqual(sum(float(row["plan_qty"]) for row in tasks), 15.0)
        self.assertEqual(str(tasks[-1]["calendar_date"]), "2026-04-14")

    def test_generate_schedule_blocks_material_shortage_before_persisting_version(self) -> None:
        self._seed_route_and_topology("MAT-SHORT", "PROC-A", capacity_per_shift=10)
        self._seed_order(
            "MO-SHORT-001",
            material_code="MAT-SHORT",
            quantity=10,
            expected_start_date="2026-04-13",
        )
        self.connection.execute(
            """
            INSERT INTO material_issue_items (
                production_order_no,
                child_material_code,
                child_material_name,
                spec_model,
                issue_qty,
                supply_type_code,
                supply_type_name,
                inventory_qty,
                inventory_status,
                usage_numerator,
                usage_denominator,
                child_unit,
                expandable,
                display_order,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "MO-SHORT-001",
                "RM-001",
                "Raw-1",
                "Spec",
                5,
                "PURCHASED",
                "采购",
                0,
                "LOW",
                1,
                1,
                "PCS",
                0,
                1,
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

        with self.assertRaises(AppError) as ctx:
            self.service.generate_schedule(
                {
                    "strategy_code": "KEY_ORDER_FIRST",
                    "capacity_source_mode": "DEFAULT",
                    "use_order_state_window": True,
                }
            )

        self.assertEqual(ctx.exception.code, "SCHEDULE_MATERIAL_SHORTAGE_BLOCKED")
        self.assertEqual(
            self.connection.execute("SELECT COUNT(1) FROM schedule_versions").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(1) FROM schedule_tasks").fetchone()[0],
            0,
        )

    def test_reference_version_defaults_to_published_version(self) -> None:
        self._seed_order("MO-REF-001", material_code="MAT-REF", quantity=10, expected_start_date="2026-04-13")
        self._seed_schedule_version("V-PUB-001", status="PUBLISHED", created_at="2026-04-13T00:00:00+00:00")
        self._seed_schedule_version("V-DRF-002", status="DRAFT", created_at="2026-04-14T00:00:00+00:00")

        pool_payload = self.service.list_order_pool()
        timeline_payload = self.service.get_order_pool_process_timeline("MO-REF-001")

        self.assertEqual(pool_payload["reference_version_no"], "V-PUB-001")
        self.assertEqual(timeline_payload["summary"]["reference_version_no"], "V-PUB-001")

    def _seed_order(
        self,
        order_no: str,
        *,
        material_code: str = "MAT-001",
        quantity: float = 10,
        expected_start_date: str,
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
                quantity,
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
                expected_start_date,
                f"{expected_start_date}T08:00:00+08:00",
                "2026-04-20T18:00:00+08:00",
                5,
                0,
                0,
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

    def _seed_route_and_topology(
        self,
        material_code: str,
        process_code: str,
        *,
        capacity_per_shift: float,
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
                material_code,
                1,
                process_code,
                f"Process-{process_code}",
                "FS",
                f"ROUTE-{material_code}",
                "Test Route",
                f"Product-{material_code}",
                1,
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
                "Workshop-1",
                "LINE-1",
                "Line-1",
                process_code,
                capacity_per_shift,
                1,
                0,
                1,
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

    def _seed_schedule_version(
        self,
        version_no: str,
        *,
        status: str,
        created_at: str,
    ) -> None:
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

    def _list_schedule_tasks(self, version_no: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT calendar_date, shift_code, plan_qty
            FROM schedule_tasks
            WHERE version_no = ?
            ORDER BY task_no ASC
            """,
            (version_no,),
        ).fetchall()


if __name__ == "__main__":
    unittest.main()
