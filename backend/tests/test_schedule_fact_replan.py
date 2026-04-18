from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service import AppService


class ScheduleFactReplanTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "schedule-fact-replan.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.service = AppService(self.connection)
        self.service._ensure_masterdata_seeded = lambda: None  # type: ignore[method-assign]
        self.service.factory.build_inventory_refresh_service = lambda: type(
            "InventoryRefreshStub",
            (),
            {"refresh_inventory": staticmethod(lambda _codes: None)},
        )()

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_order_pool_without_version_metadata_still_returns_items(self) -> None:
        self._seed_order("MO-ENTRY-001", material_code="MAT-ENTRY-001")
        self._seed_schedule_version("V-PUB-ENTRY-001", status="PUBLISHED", created_at="2026-04-13T00:00:00+00:00")
        self._seed_schedule_version("V-DRF-ENTRY-002", status="DRAFT", created_at="2026-04-14T00:00:00+00:00")

        payload = self.service.list_order_pool()
        timeline = self.service.get_order_pool_process_timeline("MO-ENTRY-001")

        self.assertIn("items", payload)
        self.assertEqual(len(payload["items"]), 1)
        self.assertIn("reference_version_no", timeline["summary"])

    def test_state_window_keeps_manual_window_separate_from_schedule_fact(self) -> None:
        self._seed_order(
            "MO-WINDOW-001",
            material_code="MAT-WINDOW-001",
            expected_start_date="2026-04-13",
            expected_start_time="2026-04-13T08:00:00+08:00",
            expected_finish_time="2026-04-15T18:00:00+08:00",
        )
        self._seed_schedule_version("V-PUB-WINDOW-001", status="PUBLISHED", created_at="2026-04-13T00:00:00+00:00")
        self._seed_schedule_task(
            version_no="V-PUB-WINDOW-001",
            task_no=1,
            order_no="MO-WINDOW-001",
            process_code="PROC-A",
            process_name_cn="工序A",
            calendar_date="2026-04-14",
            shift_code="NIGHT",
            plan_qty=10,
            plan_start_time="2026-04-14T20:00:00+08:00",
        )

        row = self.service.list_order_pool()["items"][0]

        self.assertEqual(row["manual_expected_start_date"], "2026-04-13")
        self.assertEqual(row["manual_expected_start_time"], "2026-04-13T08:00:00+08:00")
        self.assertEqual(row["scheduled_start_date"], "2026-04-14")
        self.assertEqual(row["scheduled_start_time"], "2026-04-14T20:00:00+08:00")

    def test_order_pool_without_current_schedule_hides_version_metadata(self) -> None:
        self._seed_order("MO-FACT-001", material_code="MAT-FACT-001")
        self._seed_schedule_version("V-DRF-FACT-001", status="DRAFT", created_at="2026-04-14T00:00:00+00:00")

        payload = self.service.list_order_pool()
        timeline = self.service.get_order_pool_process_timeline("MO-FACT-001")

        self.assertEqual(len(payload["items"]), 1)
        self.assertIsNone(timeline["summary"]["reference_version_no"])

    def test_explicit_order_pool_view_still_reads_schedule_fact(self) -> None:
        self._seed_order("MO-LEGACY-001", material_code="MAT-LEGACY-001")
        self._seed_schedule_version("V-PUB-LEGACY-001", status="PUBLISHED", created_at="2026-04-13T00:00:00+00:00")
        self._seed_schedule_version("V-DRF-LEGACY-002", status="DRAFT", created_at="2026-04-14T00:00:00+00:00")
        self._seed_schedule_task(
            version_no="V-DRF-LEGACY-002",
            task_no=1,
            order_no="MO-LEGACY-001",
            process_code="PROC-A",
            process_name_cn="工序A",
            calendar_date="2026-04-14",
            shift_code="DAY",
            plan_qty=10,
            plan_start_time="2026-04-14T08:00:00+08:00",
        )

        payload = self.service.list_order_pool(version_no="V-DRF-LEGACY-002")
        row = payload["items"][0]
        timeline = self.service.get_order_pool_process_timeline("MO-LEGACY-001", version_no="V-DRF-LEGACY-002")

        self.assertEqual(row["scheduled_start_date"], "2026-04-14")
        self.assertEqual(timeline["summary"]["reference_version_no"], "V-DRF-LEGACY-002")

    def test_generate_schedule_by_fact_skips_locked_and_frozen_orders(self) -> None:
        self._seed_simulation_date("2026-04-13")
        self._seed_route_and_topology("MAT-FACT-A", "PROC-A", capacity_per_shift=10)
        self._seed_order("MO-FACT-OPEN-001", material_code="MAT-FACT-A")
        self._seed_order("MO-FACT-LOCK-001", material_code="MAT-FACT-A", lock_flag=1)
        self._seed_order("MO-FACT-FROZEN-001", material_code="MAT-FACT-A", frozen_flag=1)
        self._seed_schedule_version("V-CUR-FACT-001", status="CURRENT", created_at="2026-04-13T00:00:00+00:00")
        self._seed_schedule_task(
            version_no="V-CUR-FACT-001",
            task_no=1,
            order_no="MO-FACT-OPEN-001",
            process_code="PROC-A",
            process_name_cn="工序A",
            calendar_date="2026-04-13",
            shift_code="DAY",
            plan_qty=10,
            plan_start_time="2026-04-13T08:00:00+08:00",
        )
        self._seed_work_report(
            order_no="MO-FACT-OPEN-001",
            process_code="PROC-A",
            report_time="2026-04-13T09:00:00+08:00",
        )

        generated = self.service.generate_schedule_by_fact(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "PLANNED",
                "use_order_state_window": True,
            }
        )

        rows = self._list_tasks(str(generated["version_no"]))
        self.assertEqual(generated["capacity_source_mode"], "PLANNED")
        self.assertEqual(str(rows[0]["production_order_no"]), "MO-FACT-OPEN-001")
        self.assertEqual(str(rows[0]["calendar_date"]), "2026-04-13")
        self.assertEqual(str(rows[0]["shift_code"]), "DAY")
        future_rows = rows[1:]
        self.assertGreater(len(future_rows), 0)
        self.assertTrue(all(str(row["production_order_no"]) == "MO-FACT-OPEN-001" for row in future_rows))
        self.assertTrue(all(str(row["shift_code"]) == "NIGHT" for row in future_rows[:1]))
        self.assertFalse(any(str(row["production_order_no"]) == "MO-FACT-LOCK-001" for row in rows))
        self.assertFalse(any(str(row["production_order_no"]) == "MO-FACT-FROZEN-001" for row in rows))

    def test_generate_schedule_by_fact_accepts_actual_mode_without_base_version(self) -> None:
        self._seed_simulation_date("2026-04-13")
        self._seed_route_and_topology("MAT-FACT-B", "PROC-A", capacity_per_shift=10)
        self._seed_order("MO-FACT-ACTUAL-001", material_code="MAT-FACT-B")
        self._seed_work_report(
            order_no="MO-FACT-ACTUAL-001",
            process_code="PROC-A",
            report_time="2026-04-13T09:00:00+08:00",
        )

        generated = self.service.generate_schedule_by_fact(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "ACTUAL",
                "use_order_state_window": True,
            }
        )

        rows = self._list_tasks(str(generated["version_no"]))
        self.assertEqual(generated["capacity_source_mode"], "ACTUAL")
        self.assertGreater(len(rows), 0)
        self.assertEqual(str(rows[0]["calendar_date"]), "2026-04-13")
        self.assertEqual(str(rows[0]["shift_code"]), "NIGHT")

    def _seed_order(
        self,
        order_no: str,
        *,
        material_code: str,
        expected_start_date: str = "2026-04-13",
        expected_start_time: str = "2026-04-13T08:00:00+08:00",
        expected_finish_time: str = "2026-04-15T18:00:00+08:00",
        lock_flag: int = 0,
        frozen_flag: int = 0,
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
                expected_start_date,
                expected_start_time,
                expected_finish_time,
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

    def _seed_route_and_topology(self, product_code: str, process_code: str, *, capacity_per_shift: int) -> None:
        self.connection.execute(
            """
            INSERT INTO masterdata_process_routes (
                product_code, sequence_no, process_code, process_name_cn, dependency_type,
                route_no, route_name_cn, product_name_cn, is_final_process, updated_at
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
        self.connection.execute(
            """
            INSERT INTO masterdata_line_topology (
                company_code, workshop_code, workshop_name, line_code, line_name, process_code,
                capacity_per_shift, required_workers, required_machines, enabled_flag, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "COMPANY-MAIN",
                "WS-01",
                "WS-01",
                "LINE-01",
                "LINE-01",
                process_code,
                capacity_per_shift,
                1,
                0,
                1,
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

    def _seed_simulation_date(self, current_date: str) -> None:
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
            ("default", current_date, f"{current_date}T00:00:00+00:00"),
        )
        self.connection.commit()

    def _seed_work_report(self, *, order_no: str, process_code: str, report_time: str) -> None:
        self.connection.execute(
            """
            INSERT INTO work_reports (
                report_id,
                production_order_no,
                report_scope,
                process_code,
                process_name,
                company_code,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                report_qty,
                report_time,
                operator_name,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"RPT-{order_no}",
                order_no,
                "ORDER",
                process_code,
                process_code,
                "COMPANY-MAIN",
                "WS-01",
                "WS-01",
                "LINE-01",
                "LINE-01",
                1,
                report_time,
                "tester",
                report_time,
            ),
        )
        self.connection.commit()

    def _seed_schedule_task(
        self,
        *,
        version_no: str,
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
                workshop_code,
                line_code,
                calendar_date,
                shift_code,
                plan_qty,
                plan_start_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_no,
                task_no,
                order_no,
                process_code,
                process_name_cn,
                "WS-01",
                "LINE-01",
                calendar_date,
                shift_code,
                plan_qty,
                plan_start_time,
            ),
        )
        self.connection.commit()

    def _list_tasks(self, version_no: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT production_order_no, calendar_date, shift_code, plan_qty
            FROM schedule_tasks
            WHERE version_no = ?
            ORDER BY task_no ASC
            """,
            (version_no,),
        ).fetchall()
