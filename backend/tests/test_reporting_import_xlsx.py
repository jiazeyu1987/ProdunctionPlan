from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
import hashlib
from pathlib import Path

from openpyxl import Workbook

from backend.app.db import initialize_database
from backend.app.services.app_service import AppService


class ReportingImportXlsxTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "reporting-import-xlsx.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.service = AppService(self.connection)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

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

    def _build_xlsx(self, path: Path) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = "报工"
        ws.append(
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
                "支数",
                "公斤数",
                "实腔数",
                "全程时间",
                "生产定额",
                "工作时长",
                "注塑合模/组装公斤数",
                "注塑个数/组装个重",
                "操作",
            ]
        )
        ws.append(
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
                1,
                2.5,
                4,
                10,
                20,
                30,
                40,
                50,
                "",
            ]
        )
        ws.append(
            [
                datetime(2026, 4, 9, 15, 40, 0),
                "OP-002",
                "王五",
                "赵六",
                "881MO999999-1",
                "资源组B",
                "资源B",
                "DISP-02",
                "PROD-02",
                "产品B",
                "SPEC-B",
                "MOLD-02",
                "Z1000",
                "缺失订单工序",
                "生产部",
                8,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
        wb.save(path)

    def test_import_xlsx_inserts_rows_and_is_idempotent(self) -> None:
        self._seed_order("881MO090144")
        xlsx_path = Path(self.temp_dir.name) / "work_reports.xlsx"
        self._build_xlsx(xlsx_path)
        file_sha256 = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()
        expected_source_file_name = f"sha256:{file_sha256}"

        result = self.service.import_mes_reportings_from_xlsx(
            {"file_path": str(xlsx_path), "company_code": "COMPANY-MAIN"}
        )

        self.assertEqual(int(result["total_row_count"]), 2)
        self.assertEqual(int(result["imported_count"]), 1)
        self.assertEqual(int(result["skipped_existing_count"]), 0)
        self.assertEqual(int(result["failed_count"]), 1)
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(str(result["file_sha256"]), file_sha256)
        self.assertEqual(str(result["source_file_name"]), expected_source_file_name)

        row = self.connection.execute(
            """
            SELECT
                production_order_no,
                process_code,
                process_name,
                report_qty,
                report_time,
                operator_code,
                operator_name,
                section_leader_name,
                workshop_code,
                line_code,
                source_file_name,
                source_sheet_name,
                source_row_no,
                updated_at
            FROM work_reports
            WHERE production_order_no = ?
            """,
            ("881MO090144",),
        ).fetchone()
        assert row is not None
        self.assertEqual(str(row["production_order_no"]), "881MO090144")
        self.assertEqual(str(row["process_code"]), "Z9999")
        self.assertEqual(str(row["process_name"]), "测试工序")
        self.assertEqual(float(row["report_qty"]), 12.0)
        self.assertEqual(str(row["operator_code"]), "OP-001")
        self.assertEqual(str(row["operator_name"]), "张三")
        self.assertEqual(str(row["section_leader_name"]), "李四")
        self.assertIsNone(row["workshop_code"])
        self.assertIsNone(row["line_code"])
        self.assertEqual(str(row["source_sheet_name"]), "报工")
        self.assertEqual(int(row["source_row_no"]), 2)
        self.assertEqual(str(row["source_file_name"]), expected_source_file_name)
        self.assertEqual(str(row["report_time"]), "2026-04-09T07:27:17+00:00")
        self.assertEqual(str(row["updated_at"]), "2026-04-09T07:27:17+00:00")

        file_row = self.connection.execute(
            """
            SELECT
                file_sha256,
                original_file_name,
                total_row_count,
                imported_count,
                skipped_existing_count,
                failed_count,
                created_missing_order_count
            FROM reporting_import_files
            WHERE file_sha256 = ?
            """,
            (file_sha256,),
        ).fetchone()
        assert file_row is not None
        self.assertEqual(str(file_row["file_sha256"]), file_sha256)
        self.assertEqual(str(file_row["original_file_name"]), "work_reports.xlsx")
        self.assertEqual(int(file_row["total_row_count"]), 2)
        self.assertEqual(int(file_row["imported_count"]), 1)
        self.assertEqual(int(file_row["failed_count"]), 1)

        listing = self.service.list_mes_reportings()
        self.assertEqual(len(listing["items"]), 1)
        item = listing["items"][0]
        self.assertEqual(item["operator_code"], "OP-001")
        self.assertEqual(item["section_leader_name"], "李四")
        self.assertEqual(item["updated_at"], "2026-04-09T07:27:17+00:00")

        again = self.service.import_mes_reportings_from_xlsx(
            {"file_path": str(xlsx_path), "company_code": "COMPANY-MAIN"}
        )
        self.assertEqual(int(again["total_row_count"]), 2)
        self.assertEqual(int(again["imported_count"]), 0)
        self.assertEqual(int(again["skipped_existing_count"]), 1)
        self.assertEqual(int(again["failed_count"]), 1)

        count_row = self.connection.execute("SELECT COUNT(1) FROM work_reports").fetchone()
        assert count_row is not None
        self.assertEqual(int(count_row[0]), 1)

    def test_import_xlsx_can_create_missing_orders_when_enabled(self) -> None:
        self._seed_order("881MO090144")
        xlsx_path = Path(self.temp_dir.name) / "work_reports.xlsx"
        self._build_xlsx(xlsx_path)
        file_sha256 = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()

        result = self.service.import_mes_reportings_from_xlsx(
            {
                "file_path": str(xlsx_path),
                "company_code": "COMPANY-MAIN",
                "create_missing_orders": 1,
            }
        )

        self.assertEqual(int(result["total_row_count"]), 2)
        self.assertEqual(int(result["imported_count"]), 2)
        self.assertEqual(int(result["failed_count"]), 0)
        self.assertEqual(int(result["created_missing_order_count"]), 1)
        self.assertEqual(str(result["file_sha256"]), file_sha256)

        order_row = self.connection.execute(
            "SELECT production_order_no, material_code, material_name FROM production_orders WHERE production_order_no = ?",
            ("881MO999999",),
        ).fetchone()
        assert order_row is not None
        self.assertEqual(str(order_row["production_order_no"]), "881MO999999")

        file_row = self.connection.execute(
            "SELECT imported_count, failed_count, created_missing_order_count FROM reporting_import_files WHERE file_sha256 = ?",
            (file_sha256,),
        ).fetchone()
        assert file_row is not None
        self.assertEqual(int(file_row["imported_count"]), 2)
        self.assertEqual(int(file_row["failed_count"]), 0)
        self.assertEqual(int(file_row["created_missing_order_count"]), 1)
