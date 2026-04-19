from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.errors import AppError
from backend.app.services.app_service_provider import create_app_service
from backend.app.services.masterdata_command_service import MasterdataCommandService


class MasterdataCommandServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "masterdata-command-service.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.host = create_app_service(self.connection)
        self.service = MasterdataCommandService(self.host)

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_create_and_delete_process_routes(self) -> None:
        result = self.service.create_process_routes(
            {
                "product_code": "MAT-001",
                "steps": [{"process_code": "PROC-A"}],
            }
        )
        self.assertEqual(result, {"ok": True})

        row = self.connection.execute(
            "SELECT product_code FROM masterdata_process_routes WHERE product_code = ?",
            ("MAT-001",),
        ).fetchone()
        self.assertIsNotNone(row)

        deleted = self.service.delete_process_routes({"product_code": "MAT-001"})
        self.assertEqual(deleted, {"ok": True})
        row = self.connection.execute(
            "SELECT product_code FROM masterdata_process_routes WHERE product_code = ?",
            ("MAT-001",),
        ).fetchone()
        self.assertIsNone(row)

    def test_save_schedule_calendar_rules_updates_date_shift_mode(self) -> None:
        payload = self.service.save_schedule_calendar_rules(
            {"date_shift_mode_by_date": {"2026-04-13": "BOTH"}}
        )
        self.assertEqual(payload["data"]["date_shift_mode_by_date"]["2026-04-13"], "BOTH")

    def test_create_process_routes_requires_product_code(self) -> None:
        with self.assertRaises(AppError) as ctx:
            self.service.create_process_routes({"product_code": "", "steps": []})

        self.assertEqual(ctx.exception.code, "PRODUCT_CODE_REQUIRED")

    def test_save_masterdata_config_requires_line_skeletons(self) -> None:
        with self.assertRaises(AppError) as ctx:
            self.service.save_masterdata_config(
                {
                    "line_skeletons": [],
                    "line_topology": [],
                    "workshop_manager_users": [],
                    "workshop_manager_line_scopes": [],
                }
            )

        self.assertEqual(ctx.exception.code, "LINE_SKELETONS_REQUIRED")


if __name__ == "__main__":
    unittest.main()
