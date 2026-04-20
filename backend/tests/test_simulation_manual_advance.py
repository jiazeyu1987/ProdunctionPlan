from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service import AppService


class SimulationManualAdvanceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "simulation-manual-advance.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.service = AppService(self.connection)
        self.service._seed_simulated_morning_capacity = lambda _calendar_date: 0  # type: ignore[method-assign]
        self.service._simulate_same_day_reportings = lambda _calendar_date: {  # type: ignore[method-assign]
            "inserted_report_count": 0,
            "skipped_existing_report_count": 0,
            "skipped_zero_capacity_report_count": 0,
        }
        self.service._rebuild_line_daily_actual_capacity_rows = lambda _calendar_date: (0, 0)  # type: ignore[method-assign]

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_advance_uses_later_of_current_simulation_date_and_client_today(self) -> None:
        self._seed_simulation_date("2026-04-02")
        client_date = "2026-04-28"
        expected_next_date = (date.fromisoformat(client_date) + timedelta(days=1)).isoformat()

        result = self.service.advance_simulation_one_day({"client_date": client_date})

        snapshot_row = self.connection.execute(
            """
            SELECT snapshot_current_date
            FROM simulation_restore_snapshot_meta
            WHERE singleton_key = ?
            """,
            ("default",),
        ).fetchone()
        current_state = self.connection.execute(
            """
            SELECT simulation_state.current_date AS current_date
            FROM simulation_state
            WHERE singleton_key = ?
            """,
            ("default",),
        ).fetchone()

        self.assertEqual(result["simulated_date"], client_date)
        self.assertEqual(result["current_date"], expected_next_date)
        self.assertIsNotNone(snapshot_row)
        assert snapshot_row is not None
        self.assertEqual(str(snapshot_row["snapshot_current_date"]), client_date)
        self.assertIsNotNone(current_state)
        assert current_state is not None
        self.assertEqual(str(current_state["current_date"]), expected_next_date)

    def test_advance_keeps_existing_session_baseline_when_simulation_is_already_ahead(self) -> None:
        self._seed_simulation_date("2026-04-20")
        self.connection.execute(
            """
            INSERT INTO simulation_restore_snapshot_meta (
                singleton_key,
                snapshot_current_date,
                snapshot_created_at
            ) VALUES (?, ?, ?)
            """,
            ("default", "2026-04-18", "2026-04-18T00:00:00+00:00"),
        )
        self.connection.commit()

        result = self.service.advance_simulation_one_day({"client_date": "2026-04-18"})

        snapshot_row = self.connection.execute(
            """
            SELECT snapshot_current_date
            FROM simulation_restore_snapshot_meta
            WHERE singleton_key = ?
            """,
            ("default",),
        ).fetchone()

        self.assertEqual(result["simulated_date"], "2026-04-20")
        self.assertEqual(result["current_date"], "2026-04-21")
        self.assertIsNotNone(snapshot_row)
        assert snapshot_row is not None
        self.assertEqual(str(snapshot_row["snapshot_current_date"]), "2026-04-18")

    def test_advance_days_moves_state_forward_and_returns_summary(self) -> None:
        self._seed_simulation_date("2026-04-24")
        advanced_dates: list[str] = []

        def seed_capacity(calendar_date: str) -> int:
            advanced_dates.append(calendar_date)
            return 1

        self.service._seed_simulated_morning_capacity = seed_capacity  # type: ignore[method-assign]

        def simulate_reporting(calendar_date: str) -> dict[str, int]:
            return {
                "inserted_report_count": 2,
                "skipped_existing_report_count": 1,
                "skipped_zero_capacity_report_count": 0,
            }

        self.service._simulate_same_day_reportings = simulate_reporting  # type: ignore[method-assign]
        self.service._rebuild_line_daily_actual_capacity_rows = lambda _calendar_date: (3, 0)  # type: ignore[method-assign]

        result = self.service.advance_simulation_days(
            {
                "client_date": "2026-04-24",
                "days": 3,
            }
        )

        self.assertEqual(advanced_dates, ["2026-04-24", "2026-04-25", "2026-04-26"])
        self.assertEqual(result["start_date"], "2026-04-24")
        self.assertEqual(result["end_date"], "2026-04-27")
        self.assertEqual(result["current_date"], "2026-04-27")
        self.assertEqual(result["advanced_days"], 3)
        self.assertEqual(result["total_simulated_reporting_count"], 6)
        self.assertEqual(result["total_skipped_existing_reporting_count"], 3)
        self.assertEqual(result["total_rebuild_actual_row_count"], 9)
        self.assertEqual(len(result["daily_results"]), 3)
        self.assertEqual(result["daily_results"][0]["simulated_date"], "2026-04-24")
        self.assertEqual(result["daily_results"][-1]["current_date"], "2026-04-27")

    def test_advance_days_rejects_non_positive_days(self) -> None:
        self._seed_simulation_date("2026-04-18")

        with self.assertRaisesRegex(Exception, "days must be a positive integer."):
            self.service.advance_simulation_days({"client_date": "2026-04-18", "days": 0})

    def test_reporting_ratio_is_deterministic_and_within_plus_minus_fifty_percent(self) -> None:
        ratio_a = self.service._simulation_reporting_ratio(
            calendar_date="2026-04-21",
            company_code="COMPANY-A",
            workshop_code="WS-1",
            line_code="LINE-1",
            process_code="PROC-1",
        )
        ratio_b = self.service._simulation_reporting_ratio(
            calendar_date="2026-04-21",
            company_code="COMPANY-A",
            workshop_code="WS-1",
            line_code="LINE-1",
            process_code="PROC-1",
        )
        ratio_c = self.service._simulation_reporting_ratio(
            calendar_date="2026-04-22",
            company_code="COMPANY-A",
            workshop_code="WS-1",
            line_code="LINE-1",
            process_code="PROC-1",
        )

        self.assertGreaterEqual(ratio_a, 0.5)
        self.assertLessEqual(ratio_a, 1.5)
        self.assertEqual(ratio_a, ratio_b)
        self.assertNotEqual(ratio_a, ratio_c)

    def test_simulate_same_day_reportings_fails_when_plan_rows_are_missing(self) -> None:
        self.service._simulate_same_day_reportings = AppService._simulate_same_day_reportings.__get__(  # type: ignore[method-assign]
            self.service,
            AppService,
        )
        with self.assertRaisesRegex(
            Exception,
            "No daily line capacity plan rows exist for the simulation date.",
        ):
            self.service._simulate_same_day_reportings("2099-04-21")

    def test_simulate_same_day_reportings_skips_existing_reports_and_respects_ratio_bounds(self) -> None:
        self.service._simulate_same_day_reportings = AppService._simulate_same_day_reportings.__get__(  # type: ignore[method-assign]
            self.service,
            AppService,
        )
        self._insert_topology_row()
        self.connection.execute(
            """
            INSERT INTO daily_line_capacity_plan (
                calendar_date,
                shift_code,
                company_code,
                workshop_code,
                line_code,
                process_code,
                planned_capacity_qty,
                worker_count,
                machine_count,
                source_note,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-04-21",
                "DAY",
                "COMPANY-A",
                "WS-1",
                "LINE-1",
                "PROC-1",
                100.0,
                1,
                1,
                "TEST",
                "2026-04-21T00:00:00+00:00",
            ),
        )
        self.connection.execute(
            """
            INSERT INTO daily_line_capacity_plan (
                calendar_date,
                shift_code,
                company_code,
                workshop_code,
                line_code,
                process_code,
                planned_capacity_qty,
                worker_count,
                machine_count,
                source_note,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-04-21",
                "DAY",
                "COMPANY-A",
                "WS-1",
                "LINE-2",
                "PROC-2",
                200.0,
                1,
                1,
                "TEST",
                "2026-04-21T00:00:00+00:00",
            ),
        )
        self.connection.execute(
            """
            INSERT INTO masterdata_line_topology (
                company_code,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                process_code,
                capacity_per_shift,
                required_workers,
                required_machines,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "COMPANY-A",
                "WS-1",
                "Workshop 1",
                "LINE-2",
                "Line 2",
                "PROC-2",
                200.0,
                1,
                1,
                "2026-04-21T00:00:00+00:00",
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
                "RPT-EXISTING",
                None,
                "PROC-1",
                "Process 1",
                "WS-1",
                "Workshop 1",
                "LINE-1",
                "Line 1",
                99.0,
                "2026-04-21T02:00:00+00:00",
                "tester",
                "2026-04-21T02:00:00+00:00",
            ),
        )
        self.connection.commit()

        result = self.service._simulate_same_day_reportings("2026-04-21")
        inserted_row = self.connection.execute(
            """
            SELECT report_qty
            FROM work_reports
            WHERE report_id != ?
            ORDER BY report_time DESC
            LIMIT 1
            """,
            ("RPT-EXISTING",),
        ).fetchone()

        self.assertEqual(result["inserted_report_count"], 1)
        self.assertEqual(result["skipped_existing_report_count"], 1)
        self.assertEqual(result["skipped_zero_capacity_report_count"], 0)
        self.assertIsNotNone(inserted_row)
        assert inserted_row is not None
        self.assertGreaterEqual(float(inserted_row["report_qty"]), 100.0)
        self.assertLessEqual(float(inserted_row["report_qty"]), 300.0)

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

    def _insert_topology_row(self) -> None:
        self.connection.execute(
            """
            INSERT INTO masterdata_line_topology (
                company_code,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                process_code,
                capacity_per_shift,
                required_workers,
                required_machines,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "COMPANY-A",
                "WS-1",
                "Workshop 1",
                "LINE-1",
                "Line 1",
                "PROC-1",
                100.0,
                1,
                1,
                "2026-04-21T00:00:00+00:00",
            ),
        )


if __name__ == "__main__":
    unittest.main()
