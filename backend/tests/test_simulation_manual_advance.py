from __future__ import annotations

import sqlite3
import tempfile
import unittest
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

        result = self.service.advance_simulation_one_day({"client_date": "2026-04-18"})

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

        self.assertEqual(result["simulated_date"], "2026-04-18")
        self.assertEqual(result["current_date"], "2026-04-19")
        self.assertIsNotNone(snapshot_row)
        assert snapshot_row is not None
        self.assertEqual(str(snapshot_row["snapshot_current_date"]), "2026-04-18")
        self.assertIsNotNone(current_state)
        assert current_state is not None
        self.assertEqual(str(current_state["current_date"]), "2026-04-19")

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


if __name__ == "__main__":
    unittest.main()
