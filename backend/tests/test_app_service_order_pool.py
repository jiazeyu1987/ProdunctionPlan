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

    def test_list_order_pool_exposes_shortage_summary_for_published_orders(self) -> None:
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
                "MO-SHORT-001",
                "MAT-SHORT-001",
                "测试成品",
                "规格C",
                10,
                "2",
                "2026-04-13",
                "2026-04-15",
                "SRC-SHORT-001",
                "ML-SHORT-001",
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
                "MO-SHORT-001",
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
                "SRC-SHORT-001-B1",
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
                "V2026.04.15-D1",
                "PUBLISHED",
                "已发布",
                "KEY_ORDER_FIRST",
                "2026-04-15T00:00:00+08:00",
                "2026-04-15T01:00:00+08:00",
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
                "V2026.04.15-D1",
                1,
                "MO-SHORT-001",
                "PROC-A",
                "工序A",
                "2026-04-13",
                "DAY",
                10,
                "2026-04-13T08:00:00+08:00",
            ),
        )
        self.connection.execute(
            """
            INSERT INTO material_issue_items (
                production_order_no,
                child_material_code,
                child_material_name,
                issue_qty,
                supply_type_code,
                supply_type_name,
                inventory_qty,
                inventory_status,
                child_unit,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "MO-SHORT-001",
                "RM-001",
                "关键物料",
                10,
                "PURCHASED",
                "外购",
                0,
                "KNOWN",
                "PCS",
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
                "RM-001",
                2,
                "KNOWN",
                "2026-04-13T00:00:00+00:00",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

        payload = self.service.list_order_pool()

        self.assertEqual(payload["reference_version_no"], "V2026.04.15-D1")
        self.assertEqual(
            payload["items"][0]["reference_schedule_version_no"],
            "V2026.04.15-D1",
        )
        self.assertEqual(
            payload["items"][0]["reference_schedule_version_status"],
            "PUBLISHED",
        )
        self.assertTrue(payload["items"][0]["scheduled_in_reference_version"])
        self.assertTrue(payload["items"][0]["published_in_reference_version"])
        self.assertEqual(payload["items"][0]["scheduled_start_date"], "2026-04-13")
        self.assertEqual(payload["items"][0]["scheduled_finish_date"], "2026-04-13")
        self.assertEqual(payload["items"][0]["material_shortage_count"], 1)
        self.assertEqual(payload["items"][0]["material_shortage_first_material_code"], "RM-001")
        self.assertEqual(payload["items"][0]["material_shortage_start_date"], "2026-04-13")
        self.assertEqual(payload["items"][0]["material_shortage_first_process_code"], "PROC-A")

    def test_list_order_pool_exposes_shortage_summary_for_self_made_child_materials(self) -> None:
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
                "MO-SELF-001",
                "MAT-SELF-001",
                "测试成品",
                "规格D",
                10,
                "2",
                "2026-04-13",
                "2026-04-15",
                "SRC-SELF-001",
                "ML-SELF-001",
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
                "MO-SELF-001",
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
                "SRC-SELF-001-B1",
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
                "V2026.04.15-D2",
                "PUBLISHED",
                "已发布",
                "KEY_ORDER_FIRST",
                "2026-04-15T00:00:00+08:00",
                "2026-04-15T01:00:00+08:00",
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
                "V2026.04.15-D2",
                1,
                "MO-SELF-001",
                "PROC-A",
                "工序A",
                "2026-04-13",
                "DAY",
                10,
                "2026-04-13T08:00:00+08:00",
            ),
        )
        self.connection.execute(
            """
            INSERT INTO material_issue_items (
                production_order_no,
                child_material_code,
                child_material_name,
                issue_qty,
                supply_type_code,
                supply_type_name,
                inventory_qty,
                inventory_status,
                child_unit,
                expandable,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "MO-SELF-001",
                "SUB-001",
                "自制件A",
                2,
                "SELF_MADE",
                "自制",
                0,
                "KNOWN",
                "PCS",
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
                "下级原料A",
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

        payload = self.service.list_order_pool()

        self.assertEqual(payload["items"][0]["material_shortage_count"], 1)
        self.assertEqual(payload["items"][0]["material_shortage_first_material_code"], "RM-CHILD-001")

    def test_list_order_pool_marks_natural_overdue_and_final_eta_risk(self) -> None:
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
                "MO-RISK-001",
                "MAT-RISK-001",
                "测试风险订单",
                "规格E",
                10,
                "2",
                "2026-04-13",
                "2026-04-15",
                "SRC-RISK-001",
                "ML-RISK-001",
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
                "MO-RISK-001",
                "2026-04-15",
                "2026-04-17",
                "2026-04-17T20:00:00+08:00",
                "2026-04-18T18:00:00+08:00",
                5,
                0,
                0,
                0,
                "OPEN",
                "OPEN",
                0,
                10,
                0,
                "SRC-RISK-001-B1",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

        payload = self.service.list_order_pool()

        self.assertTrue(payload["items"][0]["is_naturally_overdue"])
        self.assertEqual(payload["items"][0]["expected_start_due_gap_days"], 2)
        self.assertEqual(payload["items"][0]["order_window_risk_level"], "OVERDUE")
        self.assertEqual(payload["items"][0]["final_process_risk_level"], "UNKNOWN")

    def test_list_order_pool_keeps_manual_window_separate_from_schedule_fact(self) -> None:
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
                "MO-MANUAL-001",
                "MAT-MANUAL-001",
                "人工干预订单",
                "规格F",
                10,
                "2",
                "2026-04-13",
                "2026-04-15",
                "SRC-MANUAL-001",
                "ML-MANUAL-001",
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
                "MO-MANUAL-001",
                "2026-04-15",
                "2026-04-14",
                "2026-04-14T20:00:00+08:00",
                "2026-04-16T18:00:00+08:00",
                2,
                1,
                1,
                0,
                "OPEN",
                "OPEN",
                0,
                10,
                0,
                "SRC-MANUAL-001-B1",
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
                "V2026.04.16-D1",
                "PUBLISHED",
                "已发布",
                "KEY_ORDER_FIRST",
                "2026-04-16T00:00:00+08:00",
                "2026-04-16T01:00:00+08:00",
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
                "V2026.04.16-D1",
                1,
                "MO-MANUAL-001",
                "PROC-A",
                "工序A",
                "WS-01",
                "LINE-01",
                "2026-04-15",
                "DAY",
                10,
                "2026-04-15T08:00:00+08:00",
            ),
        )
        self.connection.commit()

        payload = self.service.list_order_pool()
        row = payload["items"][0]

        self.assertEqual(row["expected_start_date"], "2026-04-14")
        self.assertEqual(row["scheduled_start_date"], "2026-04-15")
        self.assertTrue(row["manual_expected_start_override"])
        self.assertEqual(row["manual_expected_start_shift"], "NIGHT")
        self.assertEqual(row["scheduled_due_gap_days"], 1)
        self.assertEqual(row["reference_schedule_version_status_label"], "已发布")
        self.assertEqual(row["reference_schedule_version_label"], "正式发布版 V2026.04.16-D1")
        self.assertEqual(row["viewing_schedule_version_label"], "当前查看版 V2026.04.16-D1（已发布）")
        self.assertEqual(row["published_schedule_version_label"], "正式执行版 V2026.04.16-D1")
        self.assertTrue(row["scheduled_in_published_version"])
        self.assertEqual(row["delay_risk_source"], "SCHEDULE_FACT")
        self.assertEqual(row["manual_intervention_types"], ["EXPECTED_START", "PRIORITY", "LOCK"])
        self.assertEqual(row["actual_workshop_codes"], ["WS-01"])
        self.assertEqual(row["actual_line_codes"], ["LINE-01"])
        self.assertEqual(row["actual_process_codes"], ["PROC-A"])

    def test_get_order_pool_item_separates_viewing_and_published_versions(self) -> None:
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
                "MO-VERSION-001",
                "MAT-VERSION-001",
                "版本口径订单",
                "规格G",
                10,
                "2",
                "2026-04-13",
                "2026-04-15",
                "SRC-VERSION-001",
                "ML-VERSION-001",
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
                "MO-VERSION-001",
                "2026-04-15",
                "2026-04-14",
                "2026-04-14T08:00:00+08:00",
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
                "SRC-VERSION-001-B1",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.executemany(
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
            [
                (
                    "V2026.04.16-D1",
                    "PUBLISHED",
                    "已发布",
                    "KEY_ORDER_FIRST",
                    "2026-04-16T00:00:00+08:00",
                    "2026-04-16T01:00:00+08:00",
                ),
                (
                    "V2026.04.17-D1",
                    "DRAFT",
                    "草稿",
                    "KEY_ORDER_FIRST",
                    "2026-04-17T00:00:00+08:00",
                    None,
                ),
            ],
        )
        self.connection.executemany(
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
            [
                (
                    "V2026.04.16-D1",
                    1,
                    "MO-VERSION-001",
                    "PROC-A",
                    "工序A",
                    "WS-01",
                    "LINE-01",
                    "2026-04-14",
                    "DAY",
                    10,
                    "2026-04-14T08:00:00+08:00",
                ),
                (
                    "V2026.04.17-D1",
                    1,
                    "MO-VERSION-001",
                    "PROC-A",
                    "工序A",
                    "WS-02",
                    "LINE-02",
                    "2026-04-15",
                    "NIGHT",
                    10,
                    "2026-04-15T20:00:00+08:00",
                ),
            ],
        )
        self.connection.commit()

        row = self.service.get_order_pool_item("MO-VERSION-001", version_no="V2026.04.17-D1")

        self.assertEqual(row["viewing_schedule_version_no"], "V2026.04.17-D1")
        self.assertEqual(row["viewing_schedule_version_label"], "当前查看版 V2026.04.17-D1（草稿）")
        self.assertEqual(row["published_schedule_version_no"], "V2026.04.16-D1")
        self.assertEqual(row["published_schedule_version_label"], "正式执行版 V2026.04.16-D1")
        self.assertTrue(row["scheduled_in_reference_version"])
        self.assertTrue(row["scheduled_in_published_version"])
        self.assertEqual(row["scheduled_start_shift"], "NIGHT")
        self.assertEqual(row["published_scheduled_start_shift"], "DAY")
