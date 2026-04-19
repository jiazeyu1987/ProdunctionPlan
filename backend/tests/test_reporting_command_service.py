from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
import hashlib
from pathlib import Path

from openpyxl import Workbook

from backend.app.db import initialize_database
from backend.app.errors import AppError
from backend.app.services.app_service_provider import create_app_service
from backend.app.services.reporting_command_service import ReportingCommandService


class ReportingCommandServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "reporting-command-service.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.host = create_app_service(self.connection)
        self.service = ReportingCommandService(self.host)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_delete_reporting_removes_row(self) -> None:
        self._seed_report("RPT-DELETE")

        result = self.service.delete_reporting("RPT-DELETE", {"role_code": "SCHEDULER"})

        self.assertEqual(result, {"ok": True})
        row = self.connection.execute(
            "SELECT report_id FROM work_reports WHERE report_id = ?",
            ("RPT-DELETE",),
        ).fetchone()
        self.assertIsNone(row)

    def test_select_reporting_capacity_compare_requires_report_id(self) -> None:
        with self.assertRaises(AppError) as ctx:
            self.service.select_reporting_capacity_compare({"report_id": "", "audit_id": "A-1"})

        self.assertEqual(ctx.exception.code, "REPORT_ID_REQUIRED")

    def test_create_reporting_persists_row_for_line_output_scope(self) -> None:
        result = self.service.create_reporting(
            {
                "process_code": "PROC-A",
                "report_qty": 12,
                "report_scope": "LINE_OUTPUT",
                "calendar_date": "2026-04-13",
                "operator_name": "tester",
            }
        )

        self.assertEqual(result["report_scope"], "LINE_OUTPUT")
        self.assertEqual(result["process_code"], "PROC-A")
        row = self.connection.execute(
            "SELECT report_id, report_scope, process_code, report_qty FROM work_reports WHERE report_id = ?",
            (result["report_id"],),
        ).fetchone()
        assert row is not None
        self.assertEqual(str(row["report_scope"]), "LINE_OUTPUT")
        self.assertEqual(str(row["process_code"]), "PROC-A")
        self.assertEqual(float(row["report_qty"]), 12.0)

    def test_import_mes_reportings_from_xlsx_persists_row(self) -> None:
        self._seed_order("881MO090144")
        xlsx_path = Path(self.temp_dir.name) / "reporting-command-import.xlsx"
        self._build_import_xlsx(xlsx_path)
        expected_sha256 = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()

        result = self.service.import_mes_reportings_from_xlsx(
            {"file_path": str(xlsx_path), "company_code": "COMPANY-MAIN"}
        )

        self.assertEqual(str(result["file_sha256"]), expected_sha256)
        self.assertEqual(int(result["imported_count"]), 1)
        self.assertEqual(int(result["failed_count"]), 0)
        row = self.connection.execute(
            """
            SELECT production_order_no, process_code, report_qty, source_file_name
            FROM work_reports
            WHERE production_order_no = ?
            """,
            ("881MO090144",),
        ).fetchone()
        assert row is not None
        self.assertEqual(str(row["process_code"]), "Z9999")
        self.assertEqual(float(row["report_qty"]), 12.0)
        self.assertEqual(str(row["source_file_name"]), f"sha256:{expected_sha256}")

    def _seed_report(self, report_id: str) -> None:
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
                report_id,
                None,
                "PROC-A",
                "PROC-A",
                "WS-01",
                "WS-01",
                "LINE-01",
                "LINE-01",
                10,
                "2026-04-13T10:00:00+08:00",
                "tester",
                "2026-04-13T02:00:00+00:00",
            ),
        )
        self.connection.commit()

    def _seed_order(self, order_no: str) -> None:
        self.connection.execute(
            """
            INSERT INTO production_orders (
                production_order_no,
                material_code,
                material_name,
                production_qty,
                status,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                order_no,
                "YXN.000.000.0000",
                "Test Material",
                100,
                "OPEN",
                "2026-04-09T00:00:00+00:00",
            ),
        )
        self.connection.commit()

    def _build_import_xlsx(self, path: Path) -> None:
        workbook = Workbook()
        sheet = workbook.active
        assert sheet is not None
        sheet.title = "报工"
        sheet.append(
            [
                "报工日期",
                "报工人编码",
                "报工人名称",
                "工段长",
                "生产订单号",
                "生产资源组",
                "生产资源",
                "派工单号",
                "产品编码",
                "产品名称",
                "规格",
                "模具编码",
                "工序编码",
                "工序名称",
                "所属部门",
                "报工数量",
            ]
        )
        sheet.append(
            [
                datetime(2026, 4, 9, 15, 27, 17),
                "OP-001",
                "张三",
                "李四",
                "881MO090144-1",
                "资源组A",
                "资源A",
                "DISP-01",
                "PROD-01",
                "产品A",
                "SPEC",
                "MOLD-01",
                "Z9999",
                "测试工序",
                "生产部",
                12,
            ]
        )
        workbook.save(path)


if __name__ == "__main__":
    unittest.main()
