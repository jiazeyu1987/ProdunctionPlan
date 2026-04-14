from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service import AppService


class AppServiceOrderPoolStatusTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "order-pool-status.db"
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

    def test_list_order_pool_exposes_erp_status_separately_from_local_state(self) -> None:
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
                "MO-ERP-001",
                "MAT-001",
                "测试物料",
                "规格A",
                10,
                "7",
                "2026-04-13",
                "2026-04-15",
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
                "MO-ERP-001",
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
                "SRC-001-B1",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

        payload = self.service.list_order_pool()

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["status"], "OPEN")
        self.assertEqual(payload["items"][0]["order_status"], "OPEN")
        self.assertEqual(payload["items"][0]["erp_status"], "7")
        self.assertFalse(payload["items"][0]["has_process_route"])

    def test_list_order_pool_marks_when_process_route_exists(self) -> None:
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
                "MO-ERP-002",
                "YXN.044.02.1020",
                "测试物料二",
                "规格B",
                10,
                "2",
                "2026-04-13",
                "2026-04-15",
                "SRC-002",
                "ML-002",
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
                "MO-ERP-002",
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
                "SRC-002-B1",
                "2026-04-13T00:00:00+00:00",
            ),
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

        payload = self.service.list_order_pool()

        self.assertEqual(len(payload["items"]), 1)
        self.assertTrue(payload["items"][0]["has_process_route"])
