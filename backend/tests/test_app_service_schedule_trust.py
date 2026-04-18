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
            ("default", "2026-04-13", "2026-04-13T00:00:00+00:00"),
        )
        self.connection.commit()

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
        self.assertFalse(result["save_impact"]["causes_unavoidable_delay"])

    def test_patch_expected_start_night_on_due_date_marks_unavoidable_delay(self) -> None:
        self._seed_order("MO-PATCH-NIGHT-001", expected_start_date="2026-04-13")

        result = self.service.patch_order_pool_order(
            "MO-PATCH-NIGHT-001",
            {
                "expected_start_date": "2026-04-20",
                "expected_start_shift": "NIGHT",
            },
        )

        self.assertEqual(result["expected_start_time"], "2026-04-20T20:00:00+08:00")
        self.assertTrue(result["is_naturally_overdue"])
        self.assertEqual(result["expected_start_due_gap_days"], 1)
        self.assertTrue(result["save_impact"]["causes_unavoidable_delay"])
        self.assertIn("该订单已必然延期", result["save_impact"]["summary_items"])

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

    def test_generate_schedule_uses_manual_expected_start_shift_when_enabled(self) -> None:
        self._seed_route_and_topology("MAT-NIGHT", "PROC-A", capacity_per_shift=10)
        self._seed_order(
            "MO-NIGHT-001",
            material_code="MAT-NIGHT",
            quantity=10,
            expected_start_date="2026-04-16",
            expected_start_shift="NIGHT",
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
        self.assertEqual(tasks[0]["shift_code"], "NIGHT")

    def test_generate_schedule_treats_late_night_timestamp_as_night_shift(self) -> None:
        self._seed_route_and_topology("MAT-NIGHT-LATE", "PROC-A", capacity_per_shift=10)
        self._seed_order(
            "MO-NIGHT-LATE-001",
            material_code="MAT-NIGHT-LATE",
            quantity=10,
            expected_start_date="2026-04-16",
            expected_start_shift="NIGHT",
        )
        self.connection.execute(
            """
            UPDATE order_pool_state
            SET expected_start_time = ?
            WHERE production_order_no = ?
            """,
            ("2026-04-16T23:00:00+08:00", "MO-NIGHT-LATE-001"),
        )
        self.connection.commit()

        generated = self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "DEFAULT",
                "use_order_state_window": True,
            }
        )

        tasks = self._list_schedule_tasks(str(generated["version_no"]))
        self.assertEqual(tasks[0]["calendar_date"], "2026-04-16")
        self.assertEqual(tasks[0]["shift_code"], "NIGHT")

    def test_generate_schedule_preserves_due_date_earlier_than_start_date(self) -> None:
        self._seed_route_and_topology("MAT-LATE", "PROC-A", capacity_per_shift=10)
        self._seed_order(
            "MO-LATE-001",
            material_code="MAT-LATE",
            quantity=10,
            expected_start_date="2026-04-16",
            promised_due_date="2026-04-14",
        )

        captured_candidates: list[dict[str, object]] = []
        original_sort_schedule_candidates = self.service._sort_schedule_candidates

        def capture_candidates(*, strategy_code, candidates):
            captured_candidates[:] = list(candidates)
            return original_sort_schedule_candidates(
                strategy_code=strategy_code,
                candidates=candidates,
            )

        self.service._sort_schedule_candidates = capture_candidates  # type: ignore[method-assign]
        self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "DEFAULT",
                "use_order_state_window": True,
            }
        )
        self.assertEqual(len(captured_candidates), 1)
        self.assertEqual(
            captured_candidates[0]["due_date"].isoformat(),
            "2026-04-14",
        )

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
                shift_code,
                company_code,
                workshop_code,
                line_code,
                process_code,
                planned_capacity_qty,
                worker_count,
                machine_count,
                source_note,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-04-13",
                "DAY",
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

        generated = self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "DEFAULT",
                "use_order_state_window": True,
            }
        )
        self.assertEqual(generated["result_status"], "RISKY")
        self.assertEqual(
            self.connection.execute("SELECT COUNT(1) FROM schedule_versions").fetchone()[0],
            1,
        )
        self.assertGreater(
            self.connection.execute("SELECT COUNT(1) FROM schedule_tasks").fetchone()[0],
            0,
        )

    def test_generate_schedule_blocks_self_made_child_material_shortage(self) -> None:
        self._seed_route_and_topology("MAT-SELF", "PROC-A", capacity_per_shift=10)
        self._seed_order(
            "MO-SELF-001",
            material_code="MAT-SELF",
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
                "MO-SELF-001",
                "SUB-001",
                "SelfMade-1",
                "Spec",
                2,
                "SELF_MADE",
                "自制",
                0,
                "LOW",
                1,
                1,
                "PCS",
                1,
                1,
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.execute(
            """
            INSERT INTO bom_children (
                parent_material_code,
                child_material_code,
                child_material_name,
                child_specification,
                usage_numerator,
                usage_denominator,
                child_unit,
                supply_type_code,
                supply_type_name,
                inventory_qty,
                inventory_status,
                expandable,
                display_order,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SUB-001",
                "RM-CHILD-001",
                "Child-Raw-1",
                "Spec",
                3,
                1,
                "PCS",
                "PURCHASED",
                "采购",
                0,
                "KNOWN",
                0,
                1,
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.execute(
            """
            INSERT INTO inventory_cache (
                material_code,
                inventory_qty,
                inventory_status,
                snapshot_time,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "RM-CHILD-001",
                1,
                "KNOWN",
                "2026-04-13T00:00:00+00:00",
                "2026-04-13T00:00:00+00:00",
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
        self.assertEqual(generated["result_status"], "RISKY")

    def test_order_pool_returns_items_when_current_schedule_exists(self) -> None:
        self._seed_order("MO-REF-001", material_code="MAT-REF", quantity=10, expected_start_date="2026-04-13")
        self._seed_schedule_version("V-PUB-001", status="PUBLISHED", created_at="2026-04-13T00:00:00+00:00")
        self._seed_schedule_version("V-DRF-002", status="DRAFT", created_at="2026-04-14T00:00:00+00:00")

        pool_payload = self.service.list_order_pool()
        timeline_payload = self.service.get_order_pool_process_timeline("MO-REF-001")

        self.assertIn("items", pool_payload)
        self.assertEqual(len(pool_payload["items"]), 1)
        self.assertEqual(timeline_payload["summary"]["reference_version_no"], "V-PUB-001")

    def test_order_pool_hides_version_metadata_when_no_current_schedule_exists(self) -> None:
        self._seed_order("MO-REF-002", material_code="MAT-REF-002", quantity=10, expected_start_date="2026-04-13")
        self._seed_schedule_version("V-DRF-ONLY-001", status="DRAFT", created_at="2026-04-14T00:00:00+00:00")

        pool_payload = self.service.list_order_pool()
        timeline_payload = self.service.get_order_pool_process_timeline("MO-REF-002")

        self.assertIn("items", pool_payload)
        self.assertEqual(len(pool_payload["items"]), 1)
        self.assertIsNone(timeline_payload["summary"]["reference_version_no"])

    def _seed_order(
        self,
        order_no: str,
        *,
        material_code: str = "MAT-001",
        quantity: float = 10,
        expected_start_date: str,
        expected_start_shift: str = "DAY",
        promised_due_date: str = "2026-04-20",
    ) -> None:
        start_time = (
            f"{expected_start_date}T20:00:00+08:00"
            if expected_start_shift == "NIGHT"
            else f"{expected_start_date}T08:00:00+08:00"
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
                material_code,
                f"Material-{order_no}",
                "Spec-A",
                quantity,
                "OPEN",
                "2026-04-13",
                promised_due_date,
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
                promised_due_date,
                expected_start_date,
                start_time,
                f"{promised_due_date}T18:00:00+08:00",
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
