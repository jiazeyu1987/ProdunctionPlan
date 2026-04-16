from __future__ import annotations

import sqlite3
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from backend.app.config import get_settings
from backend.app.db import initialize_database
from backend.app.errors import AppError
from backend.app.gateway.k3cloud_orders import K3CloudERPOrderGateway
from backend.app.gateway.orders import ERPOrderGateway
from backend.app.repositories.orders import ProductionOrderRepository
from backend.app.services.order_sync_service import OrderSyncService


class FakeSyncGateway:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self.items = items

    def fetch_sync_orders(self) -> list[dict[str, object]]:
        return list(self.items)


class FakeK3CloudClient:
    def __init__(self, responses: list[list[dict[str, object]]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def validate_base_settings(self) -> None:
        return None

    def create_session(self) -> object:
        return object()

    def execute_bill_query(self, session: object, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(kwargs)
        if self.responses:
            return self.responses.pop(0)
        return []


class FakeERPClient:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self.items = items
        self.calls: list[dict[str, object]] = []

    def request_items(
        self,
        path: str | None,
        *,
        method: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                "path": path,
                "method": method,
                "payload": payload or {},
            }
        )
        return list(self.items)


@unittest.skip("Legacy full-reset sync behavior was replaced by incremental sync.")
class OrderSyncServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_root = Path(__file__).resolve().parent / "_tmp"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.temp_root / f"orders-sync-{uuid4().hex}.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.base_settings = replace(
            get_settings(),
            erp_orders_excluded_statuses=("结算", "结案", "完工"),
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.database_path.unlink(missing_ok=True)
        super().tearDown()

    def test_full_reset_sync_replaces_orders_and_cascades_bound_data(self) -> None:
        self._seed_existing_order("OLD-001")
        service = OrderSyncService(
            connection=self.connection,
            order_repository=ProductionOrderRepository(self.connection),
            order_gateway=FakeSyncGateway(
                [
                    self._sync_item("NEW-001", business_status="下达", source_bill_no="SRC-001"),
                    self._sync_item("NEW-002", business_status="生产中", source_bill_no="SRC-002"),
                    self._sync_item("NEW-002", business_status="生产中", source_bill_no="SRC-002"),
                    self._sync_item("CLOSED-001", business_status="结案", source_bill_no="SRC-003"),
                ]
            ),
            settings=self.base_settings,
        )

        result = service.sync_orders_from_erp_full_reset()

        self.assertEqual(result["deleted_before_import_count"], 1)
        self.assertEqual(result["imported_count"], 2)
        self.assertEqual(result["filtered_out_count"], 1)
        self.assertEqual(result["order_nos"], ["NEW-001", "NEW-002"])

        order_rows = self.connection.execute(
            """
            SELECT production_order_no, status, material_code
            FROM production_orders
            ORDER BY production_order_no
            """
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in order_rows],
            [
                ("NEW-001", "下达", "MAT-NEW-001"),
                ("NEW-002", "生产中", "MAT-NEW-002"),
            ],
        )

        order_state_rows = self.connection.execute(
            """
            SELECT
                production_order_no,
                status,
                order_status,
                remaining_qty,
                progress_rate,
                priority_level,
                urgent_flag,
                production_batch_no
            FROM order_pool_state
            ORDER BY production_order_no
            """
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in order_state_rows],
            [
                ("NEW-001", "OPEN", "OPEN", 12.0, 0.0, 5, 0, "SRC-001-B1"),
                ("NEW-002", "OPEN", "OPEN", 12.0, 0.0, 5, 0, "SRC-002-B1"),
            ],
        )

        self.assertEqual(self._count_rows("material_issue_items"), 0)
        self.assertEqual(self._count_rows("work_reports"), 0)
        self.assertEqual(self._count_rows("capacity_bindings"), 0)
        self.assertEqual(self._count_rows("schedule_tasks"), 0)
        self.assertEqual(self._count_rows("schedule_versions"), 1)

    def test_full_reset_sync_fails_when_business_status_is_missing(self) -> None:
        self._seed_existing_order("OLD-001")
        service = OrderSyncService(
            connection=self.connection,
            order_repository=ProductionOrderRepository(self.connection),
            order_gateway=FakeSyncGateway([self._sync_item("NEW-001", business_status=None)]),
            settings=self.base_settings,
        )

        with self.assertRaises(AppError) as cm:
            service.sync_orders_from_erp_full_reset()

        self.assertEqual(cm.exception.code, "ERP_SYNC_BUSINESS_STATUS_UNRECOGNIZED")
        self.assertEqual(self._count_rows("production_orders"), 1)
        self.assertEqual(self._count_rows("order_pool_state"), 1)

    def test_full_reset_sync_fails_when_duplicate_orders_conflict(self) -> None:
        self._seed_existing_order("OLD-001")
        service = OrderSyncService(
            connection=self.connection,
            order_repository=ProductionOrderRepository(self.connection),
            order_gateway=FakeSyncGateway(
                [
                    self._sync_item("DUP-001", business_status="下达", material_code="MAT-A"),
                    self._sync_item("DUP-001", business_status="下达", material_code="MAT-B"),
                ]
            ),
            settings=self.base_settings,
        )

        with self.assertRaises(AppError) as cm:
            service.sync_orders_from_erp_full_reset()

        self.assertEqual(cm.exception.code, "ERP_SYNC_DUPLICATE_ORDER_CONFLICT")
        self.assertEqual(cm.exception.details, {"order_nos": ["DUP-001"]})
        self.assertEqual(self._count_rows("production_orders"), 1)

    def _sync_item(
        self,
        order_no: str,
        *,
        business_status: str | None,
        material_code: str | None = None,
        source_bill_no: str | None = None,
    ) -> dict[str, object]:
        normalized_material_code = material_code or f"MAT-{order_no}"
        return {
            "production_order_no": order_no,
            "material_code": normalized_material_code,
            "material_name": f"物料-{order_no}",
            "material_specification": "规格A",
            "production_qty": 12,
            "planned_start_date": "2026-04-13",
            "planned_end_date": "2026-04-15",
            "source_bill_no": source_bill_no or f"SRC-{order_no}",
            "material_list_no": f"ML-{order_no}",
            "business_status": business_status,
        }

    def _seed_existing_order(self, order_no: str) -> None:
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
                order_no,
                "CHILD-001",
                "子物料",
                "规格",
                2,
                "PURCHASED",
                "采购",
                1,
                "KNOWN",
                1,
                1,
                "PCS",
                0,
                1,
                "2026-04-13T00:00:00+00:00",
            ),
        )
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
                "WR-001",
                order_no,
                "PROC-A",
                "工序A",
                "WS-01",
                "车间A",
                "LINE-01",
                "产线A",
                2,
                "2026-04-13T00:00:00+08:00",
                "tester",
                "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.execute(
            """
            INSERT INTO capacity_bindings (
                production_order_no,
                process_code,
                workshop_code,
                line_code,
                process_name,
                workshop_name,
                line_name,
                capacity_qty,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_no,
                "PROC-A",
                "WS-01",
                "LINE-01",
                "工序A",
                "车间A",
                "产线A",
                10,
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
                calendar_date,
                shift_code,
                plan_qty,
                plan_start_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "V-001",
                1,
                order_no,
                "PROC-A",
                "工序A",
                "2026-04-13",
                "DAY",
                8,
                "2026-04-13T08:00:00+08:00",
            ),
        )
        self.connection.commit()

    def _count_rows(self, table_name: str) -> int:
        row = self.connection.execute(f"SELECT COUNT(1) FROM {table_name}").fetchone()
        return int(row[0] if row else 0)


class K3CloudERPOrderGatewayTestCase(unittest.TestCase):
    def test_fetch_sync_orders_paginates_until_all_rows_are_loaded(self) -> None:
        settings = replace(
            get_settings(),
            erp_orders_business_status_field="FBizStatus",
            erp_k3cloud_orders_form_id="PRD_MO",
            erp_k3cloud_orders_field_keys=(
                "FBillNo,FDocumentStatus,FMaterialId.FNumber,FMaterialId.FName,"
                "FMaterialId.FSpecification,FQty,FPlanStartDate,FPlanFinishDate,FSrcBillNo,FBizStatus"
            ),
            erp_k3cloud_orders_order_string="FID DESC",
            erp_k3cloud_orders_limit=2,
            erp_k3cloud_orders_bill_no_field="FBillNo",
            erp_k3cloud_orders_material_field="FMaterialId.FNumber",
            erp_k3cloud_orders_name_field="FMaterialId.FName",
            erp_k3cloud_orders_spec_field="FMaterialId.FSpecification",
            erp_k3cloud_orders_qty_field="FQty",
            erp_k3cloud_orders_status_field="FDocumentStatus",
            erp_k3cloud_orders_start_date_field="FPlanStartDate",
            erp_k3cloud_orders_end_date_field="FPlanFinishDate",
            erp_k3cloud_orders_source_bill_field="FSrcBillNo",
            erp_k3cloud_orders_material_list_field=None,
        )
        fake_client = FakeK3CloudClient(
            [
                [
                    self._k3cloud_row("MO-001", material_code="AW-001"),
                    self._k3cloud_row("MO-002", material_code="MAT-002"),
                ],
                [
                    self._k3cloud_row("MO-003", material_code="YXN-003"),
                    self._k3cloud_row("MO-004", material_code="YTN-004"),
                ],
                [self._k3cloud_row("MO-005", material_code="MAT-005")],
            ]
        )
        gateway = K3CloudERPOrderGateway(settings)
        gateway.client = fake_client  # type: ignore[assignment]

        items = gateway.fetch_sync_orders()

        self.assertEqual(
            [item["production_order_no"] for item in items],
            ["MO-001", "MO-003", "MO-004"],
        )
        self.assertEqual(
            [call["start_row"] for call in fake_client.calls],
            [0, 2, 4],
        )
        self.assertTrue(
            all(
                call["filter_string"]
                == (
                    "(FMaterialId.FNumber like 'AW%' or "
                    "FMaterialId.FNumber like 'YXN%' or "
                    "FMaterialId.FNumber like 'YTN%')"
                )
                for call in fake_client.calls
            )
        )
        self.assertTrue(all(item["business_status"] == "下达" for item in items))

    def test_fetch_orders_keeps_only_allowed_material_prefixes(self) -> None:
        settings = replace(
            get_settings(),
            erp_k3cloud_orders_form_id="PRD_MO",
            erp_k3cloud_orders_field_keys=(
                "FBillNo,FDocumentStatus,FMaterialId.FNumber,FMaterialId.FName,"
                "FMaterialId.FSpecification,FQty,FPlanStartDate,FPlanFinishDate,FSrcBillNo"
            ),
            erp_k3cloud_orders_order_string="FID DESC",
            erp_k3cloud_orders_limit=10,
            erp_k3cloud_orders_bill_no_field="FBillNo",
            erp_k3cloud_orders_material_field="FMaterialId.FNumber",
            erp_k3cloud_orders_name_field="FMaterialId.FName",
            erp_k3cloud_orders_spec_field="FMaterialId.FSpecification",
            erp_k3cloud_orders_qty_field="FQty",
            erp_k3cloud_orders_status_field="FDocumentStatus",
            erp_k3cloud_orders_start_date_field="FPlanStartDate",
            erp_k3cloud_orders_end_date_field="FPlanFinishDate",
            erp_k3cloud_orders_source_bill_field="FSrcBillNo",
            erp_k3cloud_orders_material_list_field=None,
        )
        fake_client = FakeK3CloudClient(
            [[
                self._k3cloud_row("MO-001", material_code="AW-001"),
                self._k3cloud_row("MO-002", material_code="ZZ-002"),
                self._k3cloud_row("MO-003", material_code="yxn-003"),
            ]]
        )
        gateway = K3CloudERPOrderGateway(settings)
        gateway.client = fake_client  # type: ignore[assignment]

        items = gateway.fetch_orders(limit=10)

        self.assertEqual(
            [item["production_order_no"] for item in items],
            ["MO-001", "MO-003"],
        )
        self.assertEqual(
            fake_client.calls[0]["filter_string"],
            (
                "(FMaterialId.FNumber like 'AW%' or "
                "FMaterialId.FNumber like 'YXN%' or "
                "FMaterialId.FNumber like 'YTN%')"
            ),
        )

    def test_fetch_sync_orders_fails_when_business_status_field_is_not_configured(self) -> None:
        settings = replace(
            get_settings(),
            erp_orders_business_status_field=None,
            erp_k3cloud_orders_form_id="PRD_MO",
            erp_k3cloud_orders_field_keys="FBillNo,FMaterialId.FNumber,FMaterialId.FName,FQty,FDocumentStatus",
            erp_k3cloud_orders_bill_no_field="FBillNo",
            erp_k3cloud_orders_material_field="FMaterialId.FNumber",
            erp_k3cloud_orders_name_field="FMaterialId.FName",
            erp_k3cloud_orders_qty_field="FQty",
            erp_k3cloud_orders_status_field="FDocumentStatus",
        )
        gateway = K3CloudERPOrderGateway(settings)
        gateway.client = FakeK3CloudClient([])  # type: ignore[assignment]

        with self.assertRaises(AppError) as cm:
            gateway.fetch_sync_orders()

        self.assertEqual(cm.exception.code, "ERP_SYNC_BUSINESS_STATUS_FIELD_MISSING")

    @staticmethod
    def _k3cloud_row(
        order_no: str,
        *,
        material_code: str | None = None,
    ) -> dict[str, object]:
        return {
            "FBillNo": order_no,
            "FDocumentStatus": "C",
            "FMaterialId.FNumber": material_code or f"AW-{order_no}",
            "FMaterialId.FName": f"物料-{order_no}",
            "FMaterialId.FSpecification": "规格A",
            "FQty": 10,
            "FPlanStartDate": "2026-04-13T00:00:00",
            "FPlanFinishDate": "2026-04-15T00:00:00",
            "FSrcBillNo": f"SRC-{order_no}",
            "FBizStatus": "下达",
        }


class ERPOrderGatewayTestCase(unittest.TestCase):
    def test_fetch_orders_keeps_only_allowed_material_prefixes_for_http_list(self) -> None:
        fake_client = FakeERPClient(
            [
                {
                    "production_order_no": "MO-001",
                    "material_code": "AW-001",
                    "material_name": "Item 1",
                    "production_qty": 10,
                    "status": "OPEN",
                },
                {
                    "production_order_no": "MO-002",
                    "material_code": "MAT-002",
                    "material_name": "Item 2",
                    "production_qty": 10,
                    "status": "OPEN",
                },
                {
                    "production_order_no": "MO-003",
                    "material_code": "ytn-003",
                    "material_name": "Item 3",
                    "production_qty": 10,
                    "status": "OPEN",
                },
            ]
        )
        gateway = ERPOrderGateway(client=fake_client)  # type: ignore[arg-type]
        gateway.settings = replace(
            get_settings(),
            erp_orders_source="HTTP_LIST",
            erp_orders_path="/erp/orders",
            erp_orders_method="GET",
        )

        items = gateway.fetch_orders()

        self.assertEqual(
            [item["production_order_no"] for item in items],
            ["MO-001", "MO-003"],
        )

    def test_fetch_sync_orders_keeps_only_allowed_material_prefixes_for_http_list(self) -> None:
        fake_client = FakeERPClient(
            [
                {
                    "production_order_no": "MO-001",
                    "material_code": "YXN-001",
                    "material_name": "Item 1",
                    "production_qty": 10,
                    "status": "OPEN",
                    "business_status": "下达",
                },
                {
                    "production_order_no": "MO-002",
                    "material_code": "MAT-002",
                    "material_name": "Item 2",
                    "production_qty": 10,
                    "status": "OPEN",
                    "business_status": "下达",
                },
                {
                    "production_order_no": "MO-003",
                    "material_code": "aw-003",
                    "material_name": "Item 3",
                    "production_qty": 10,
                    "status": "OPEN",
                    "business_status": "生产中",
                },
            ]
        )
        gateway = ERPOrderGateway(client=fake_client)  # type: ignore[arg-type]
        gateway.settings = replace(
            get_settings(),
            erp_orders_source="HTTP_LIST",
            erp_orders_path="/erp/orders",
            erp_orders_method="POST",
            erp_orders_business_status_field="business_status",
        )

        items = gateway.fetch_sync_orders()

        self.assertEqual(
            [item["production_order_no"] for item in items],
            ["MO-001", "MO-003"],
        )


if __name__ == "__main__":
    unittest.main()
