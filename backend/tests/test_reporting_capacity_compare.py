from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.errors import AppError
from backend.app.services.app_service import AppService


class ReportingCapacityCompareTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "reporting-capacity-compare.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.service = AppService(self.connection)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_select_reporting_capacity_compare_persists_snapshot_and_list_result(self) -> None:
        self._seed_report(
            report_id="RPT-SUCCESS",
            workshop_code="WS-01",
            line_code="LINE-01",
            process_code="PROC_TUBE",
            report_qty=60,
            report_time="2026-04-13T10:00:00+08:00",
        )
        self._seed_audit(
            audit_id="AUDIT-OLDER",
            calendar_date="2026-04-13",
            workshop_code="WS-01",
            line_code="LINE-01",
            process_code="PROC_TUBE",
            old_planned_capacity_qty=80,
            new_planned_capacity_qty=100,
            changed_at="2026-04-13T08:00:00+08:00",
        )
        self._seed_audit(
            audit_id="AUDIT-LATEST",
            calendar_date="2026-04-13",
            workshop_code="WS-01",
            line_code="LINE-01",
            process_code="PROC_TUBE",
            old_planned_capacity_qty=100,
            new_planned_capacity_qty=120,
            changed_at="2026-04-13T09:00:00+08:00",
        )

        result = self.service.select_reporting_capacity_compare(
            {
                "report_id": "RPT-SUCCESS",
                "audit_id": "AUDIT-LATEST",
                "actor": {"role_code": "SCHEDULER", "username": "scheduler_e2e"},
            }
        )

        self.assertEqual(result["report_id"], "RPT-SUCCESS")
        self.assertEqual(result["report_local_date"], "2026-04-13")
        self.assertEqual(result["daily_capacity_compare_audit_id"], "AUDIT-LATEST")
        self.assertEqual(result["daily_capacity_compare_qty"], 120.0)
        selected_at = str(result["daily_capacity_compare_selected_at"]).strip()
        self.assertTrue(selected_at)

        row = self.connection.execute(
            """
            SELECT
                daily_capacity_compare_audit_id,
                daily_capacity_compare_qty,
                daily_capacity_compare_selected_at
            FROM work_reports
            WHERE report_id = ?
            """,
            ("RPT-SUCCESS",),
        ).fetchone()
        assert row is not None
        self.assertEqual(str(row["daily_capacity_compare_audit_id"]), "AUDIT-LATEST")
        self.assertEqual(float(row["daily_capacity_compare_qty"]), 120.0)
        self.assertEqual(str(row["daily_capacity_compare_selected_at"]).strip(), selected_at)

        listing = self.service.list_mes_reportings()
        item = next(
            (
                entry
                for entry in (listing.get("items") or [])
                if str(entry.get("report_id") or "").strip() == "RPT-SUCCESS"
            ),
            None,
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["report_local_date"], "2026-04-13")
        self.assertEqual(item["daily_capacity_compare_audit_id"], "AUDIT-LATEST")
        self.assertEqual(float(item["daily_capacity_compare_qty"]), 120.0)

    def test_select_reporting_capacity_compare_requires_audit_id(self) -> None:
        self._seed_report(report_id="RPT-NO-AUDIT-ID")

        with self.assertRaises(AppError) as cm:
            self.service.select_reporting_capacity_compare(
                {
                    "report_id": "RPT-NO-AUDIT-ID",
                    "audit_id": "",
                    "actor": {"role_code": "SCHEDULER", "username": "scheduler_e2e"},
                }
            )

        self.assertEqual(cm.exception.code, "REPORT_CAPACITY_COMPARE_AUDIT_ID_REQUIRED")

    def test_select_reporting_capacity_compare_fails_when_no_same_day_audits_exist(self) -> None:
        self._seed_report(
            report_id="RPT-EMPTY",
            workshop_code="WS-01",
            line_code="LINE-01",
            process_code="PROC_TUBE",
            report_time="2026-04-13T10:00:00+08:00",
        )
        self._seed_audit(
            audit_id="AUDIT-OTHER-DAY",
            calendar_date="2026-04-12",
            workshop_code="WS-01",
            line_code="LINE-01",
            process_code="PROC_TUBE",
            new_planned_capacity_qty=88,
        )

        with self.assertRaises(AppError) as cm:
            self.service.select_reporting_capacity_compare(
                {
                    "report_id": "RPT-EMPTY",
                    "audit_id": "AUDIT-OTHER-DAY",
                    "actor": {"role_code": "SCHEDULER", "username": "scheduler_e2e"},
                }
            )

        self.assertEqual(cm.exception.code, "REPORT_CAPACITY_COMPARE_AUDITS_EMPTY")

    def test_select_reporting_capacity_compare_fails_when_selected_audit_scope_mismatches(self) -> None:
        self._seed_report(
            report_id="RPT-MISMATCH",
            workshop_code="WS-01",
            line_code="LINE-01",
            process_code="PROC_TUBE",
            report_time="2026-04-13T10:00:00+08:00",
        )
        self._seed_audit(
            audit_id="AUDIT-MATCHING",
            calendar_date="2026-04-13",
            workshop_code="WS-01",
            line_code="LINE-01",
            process_code="PROC_TUBE",
            new_planned_capacity_qty=110,
        )
        self._seed_audit(
            audit_id="AUDIT-WRONG-LINE",
            calendar_date="2026-04-13",
            workshop_code="WS-01",
            line_code="LINE-02",
            process_code="PROC_TUBE",
            new_planned_capacity_qty=130,
        )

        with self.assertRaises(AppError) as cm:
            self.service.select_reporting_capacity_compare(
                {
                    "report_id": "RPT-MISMATCH",
                    "audit_id": "AUDIT-WRONG-LINE",
                    "actor": {"role_code": "SCHEDULER", "username": "scheduler_e2e"},
                }
            )

        self.assertEqual(cm.exception.code, "REPORT_CAPACITY_COMPARE_AUDIT_SCOPE_MISMATCH")

    def test_select_reporting_capacity_compare_forbids_workshop_manager_without_scope(self) -> None:
        self._seed_report(
            report_id="RPT-FORBIDDEN",
            workshop_code="WS-01",
            line_code="LINE-01",
            process_code="PROC_TUBE",
            report_time="2026-04-13T10:00:00+08:00",
        )
        self._seed_audit(
            audit_id="AUDIT-FORBIDDEN",
            calendar_date="2026-04-13",
            workshop_code="WS-01",
            line_code="LINE-01",
            process_code="PROC_TUBE",
            new_planned_capacity_qty=90,
        )

        with self.assertRaises(AppError) as cm:
            self.service.select_reporting_capacity_compare(
                {
                    "report_id": "RPT-FORBIDDEN",
                    "audit_id": "AUDIT-FORBIDDEN",
                    "actor": {
                        "user_id": "manager-without-scope",
                        "role_code": "WORKSHOP_MANAGER",
                        "username": "manager_e2e",
                    },
                }
            )

        self.assertEqual(cm.exception.code, "REPORT_LINE_SCOPE_FORBIDDEN")

    def _seed_report(
        self,
        *,
        report_id: str,
        workshop_code: str = "WS-01",
        line_code: str = "LINE-01",
        process_code: str = "PROC_TUBE",
        report_qty: float = 40,
        report_time: str = "2026-04-13T10:00:00+08:00",
    ) -> None:
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
                process_code,
                process_code,
                workshop_code,
                workshop_code,
                line_code,
                line_code,
                report_qty,
                report_time,
                "tester",
                "2026-04-13T02:00:00+00:00",
            ),
        )
        self.connection.commit()

    def _seed_audit(
        self,
        *,
        audit_id: str,
        calendar_date: str,
        workshop_code: str,
        line_code: str,
        process_code: str,
        old_planned_capacity_qty: float = 0,
        new_planned_capacity_qty: float = 100,
        changed_at: str = "2026-04-13T08:00:00+08:00",
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO daily_line_capacity_plan_audit (
                audit_id,
                calendar_date,
                company_code,
                workshop_code,
                line_code,
                process_code,
                old_planned_capacity_qty,
                new_planned_capacity_qty,
                old_worker_count,
                new_worker_count,
                old_machine_count,
                new_machine_count,
                operator_user_id,
                operator_username,
                operator_display_name,
                changed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                calendar_date,
                "COMPANY-MAIN",
                workshop_code,
                line_code,
                process_code,
                old_planned_capacity_qty,
                new_planned_capacity_qty,
                1,
                2,
                1,
                1,
                None,
                "scheduler_e2e",
                "Scheduler",
                changed_at,
            ),
        )
        self.connection.commit()


if __name__ == "__main__":
    unittest.main()
