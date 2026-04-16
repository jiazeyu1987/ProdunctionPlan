from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from backend.app.config import get_settings
from backend.app.db import initialize_database
from backend.app.errors import AppError
from backend.app.repositories.orders import ProductionOrderRepository
from backend.app.services.order_sync_service import OrderSyncService


class FakeSyncGateway:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self.items = items

    def fetch_sync_orders(self) -> list[dict[str, object]]:
        return list(self.items)


class OrderSyncServiceIncrementalTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "orders-sync-incremental.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.settings = replace(
            get_settings(),
            erp_orders_excluded_statuses=("结算", "结案", "完工"),
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_preview_separates_new_updated_close_and_conflict_orders(self) -> None:
        self._seed_order("MO-LOCKED", with_reports=True, with_schedule=True)
        self._seed_order("MO-CLOSE", with_reports=False, with_schedule=False)
        service = self._build_service(
            [
                self._sync_item("MO-LOCKED", business_status="下达", material_name="新物料名"),
                self._sync_item("MO-NEW", business_status="生产中"),
                self._sync_item("MO-CLOSE", business_status="完工"),
            ]
        )

        preview = service.preview_orders_from_erp_incremental_sync()

        self.assertEqual(preview["summary"]["new_order_count"], 1)
        self.assertEqual(preview["summary"]["updated_order_count"], 1)
        self.assertEqual(preview["summary"]["close_order_count"], 1)
        self.assertEqual(preview["summary"]["conflict_order_count"], 0)
        self.assertEqual(preview["new_items"][0]["production_order_no"], "MO-NEW")
        self.assertEqual(preview["updated_items"][0]["production_order_no"], "MO-LOCKED")
        self.assertEqual(preview["close_items"][0]["production_order_no"], "MO-CLOSE")
        self.assertEqual(preview["conflict_items"], [])

    def test_apply_upserts_and_closes_without_deleting_existing_rows(self) -> None:
        self._seed_order("MO-OLD", with_reports=False, with_schedule=False)
        self._seed_order("MO-CLOSE", with_reports=False, with_schedule=False)
        service = self._build_service(
            [
                self._sync_item("MO-OLD", business_status="下达", material_name="更新后物料"),
                self._sync_item("MO-NEW", business_status="生产中"),
                self._sync_item("MO-CLOSE", business_status="结案"),
            ]
        )

        result = service.sync_orders_from_erp_incremental()

        self.assertEqual(result["summary"]["new_order_count"], 1)
        self.assertEqual(result["summary"]["updated_order_count"], 1)
        self.assertEqual(result["summary"]["close_order_count"], 1)
        rows = self.connection.execute(
            """
            SELECT production_order_no, status, material_name
            FROM production_orders
            ORDER BY production_order_no
            """
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in rows],
            [
                ("MO-CLOSE", "OPEN", "旧物料"),
                ("MO-NEW", "生产中", "物料-MO-NEW"),
                ("MO-OLD", "下达", "更新后物料"),
            ],
        )
        state_rows = self.connection.execute(
            """
            SELECT production_order_no, order_status
            FROM order_pool_state
            ORDER BY production_order_no
            """
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in state_rows],
            [("MO-CLOSE", "CLOSED"), ("MO-NEW", "OPEN"), ("MO-OLD", "OPEN")],
        )

    def test_apply_fails_when_conflicts_exist(self) -> None:
        self._seed_order("MO-BLOCKED", with_reports=True, with_schedule=False)
        service = self._build_service([self._sync_item("MO-BLOCKED", business_status="完工")])

        with self.assertRaises(AppError) as cm:
            service.sync_orders_from_erp_incremental()

        self.assertEqual(cm.exception.code, "ERP_SYNC_CONFLICTS_BLOCKED")

    def _build_service(self, items: list[dict[str, object]]) -> OrderSyncService:
        return OrderSyncService(
            connection=self.connection,
            order_repository=ProductionOrderRepository(self.connection),
            order_gateway=FakeSyncGateway(items),
            settings=self.settings,
        )

    def _sync_item(
        self,
        order_no: str,
        *,
        business_status: str,
        material_name: str | None = None,
    ) -> dict[str, object]:
        return {
            "production_order_no": order_no,
            "material_code": f"MAT-{order_no}",
            "material_name": material_name or f"物料-{order_no}",
            "material_specification": "规格A",
            "production_qty": 12,
            "planned_start_date": "2026-04-13",
            "planned_end_date": "2026-04-15",
            "source_bill_no": f"SRC-{order_no}",
            "material_list_no": f"ML-{order_no}",
            "business_status": business_status,
        }

    def _seed_order(
        self,
        order_no: str,
        *,
        with_reports: bool,
        with_schedule: bool,
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
                "MAT-OLD",
                "旧物料",
                "旧规格",
                8,
                "OPEN",
                "2026-04-10",
                "2026-04-12",
                "SRC-OLD",
                "ML-OLD",
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
                "2026-04-12",
                "2026-04-10",
                "2026-04-10T08:00:00+08:00",
                "2026-04-12T18:00:00+08:00",
                5,
                0,
                0,
                0,
                "OPEN",
                "OPEN",
                0,
                8,
                0,
                "SRC-OLD-B1",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        if with_reports:
            self.connection.execute(
                """
                INSERT INTO work_reports (
                    report_id,
                    production_order_no,
                    process_code,
                    process_name,
                    workshop_code,
                    workshop_name,
                    line_code,
                    line_name,
                    report_qty,
                    report_time,
                    operator_name,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"RPT-{order_no}",
                    order_no,
                    "PROC-A",
                    "工序A",
                    "WS-01",
                    "车间A",
                    "LINE-01",
                    "产线A",
                    2,
                    "2026-04-13T10:00:00+08:00",
                    "tester",
                    "2026-04-13T02:00:00+00:00",
                ),
            )
        if with_schedule:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO schedule_versions (
                    version_no,
                    status,
                    status_name_cn,
                    strategy_code,
                    created_at,
                    published_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "V-001",
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
                    workshop_code,
                    line_code,
                    calendar_date,
                    shift_code,
                    plan_qty,
                    plan_start_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "V-001",
                    1,
                    order_no,
                    "PROC-A",
                    "工序A",
                    "WS-01",
                    "LINE-01",
                    "2026-04-13",
                    "DAY",
                    8,
                    "2026-04-13T08:00:00+08:00",
                ),
            )
        self.connection.commit()


if __name__ == "__main__":
    unittest.main()
