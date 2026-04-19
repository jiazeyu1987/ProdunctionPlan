from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service_provider import create_app_service
from backend.app.services.order_pool_query_facade import OrderPoolQueryFacade


class OrderPoolQueryFacadeBehaviorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "order-pool-query-facade.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.facade = OrderPoolQueryFacade(create_app_service(self.connection))
        self.facade.app_service._ensure_masterdata_seeded = lambda: None  # type: ignore[method-assign]

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_list_order_pool_exposes_erp_status_separately_from_local_state(self) -> None:
        self._seed_order("MO-ERP-001", material_code="MAT-001", status="7")

        payload = self.facade.list_order_pool()

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["status"], "OPEN")
        self.assertEqual(payload["items"][0]["order_status"], "OPEN")
        self.assertEqual(payload["items"][0]["erp_status"], "7")

    def test_list_order_pool_marks_when_process_route_exists(self) -> None:
        self._seed_order("MO-ERP-002", material_code="YXN.044.02.1020", status="2")
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
                "YXN.044.02.1020",
                1,
                "PROC-A",
                "工序A",
                "FS",
                "ROUTE-TEST-002",
                "测试路线",
                "测试物料二",
                0,
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

        payload = self.facade.list_order_pool()

        self.assertEqual(len(payload["items"]), 1)
        self.assertTrue(payload["items"][0]["has_process_route"])

    def test_process_timeline_query_remains_available(self) -> None:
        self._seed_order("MO-PT-001", material_code="MAT-PT-001", status="OPEN", production_qty=120)
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
                "V-PT-001",
                "PUBLISHED",
                "已发布",
                "KEY_ORDER_FIRST",
                "2026-04-13T00:00:00+00:00",
                "2026-04-13T00:05:00+00:00",
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
                "V-PT-001",
                1,
                "MO-PT-001",
                "PROC-A",
                "工序A",
                "2026-04-13",
                "DAY",
                80,
                "2026-04-13T08:00:00+08:00",
            ),
        )
        self.connection.commit()

        payload = self.facade.get_order_pool_process_timeline("MO-PT-001")

        self.assertEqual(payload["summary"]["reference_version_no"], "V-PT-001")
        self.assertEqual(payload["process_items"][0]["process_code"], "PROC-A")

    def _seed_order(
        self,
        order_no: str,
        *,
        material_code: str,
        status: str,
        production_qty: float = 10,
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
                status,
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
                0,
                0,
                "OPEN",
                "OPEN",
                0,
                production_qty,
                0,
                f"SRC-{order_no}-B1",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()


if __name__ == "__main__":
    unittest.main()
