from __future__ import annotations

import sqlite3
import unittest
from uuid import uuid4
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.errors import AppError
from backend.app.services.app_service import AppService


class ShiftCapacityScheduleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.workspace_tmp_root = Path(__file__).resolve().parent / "_tmp"
        self.workspace_tmp_root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.workspace_tmp_root / f"shift-capacity-{uuid4().hex}.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.service = AppService(self.connection)
        self.service._ensure_masterdata_seeded = lambda: None  # type: ignore[method-assign]
        self.service.factory.build_inventory_refresh_service = lambda: type(
            "InventoryRefreshStub",
            (),
            {"refresh_inventory": staticmethod(lambda _codes: None)},
        )()
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
            ("default", "2026-04-13", "2026-04-13T00:00:00+00:00"),
        )
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()
        if self.database_path.exists():
            self.database_path.unlink()
        super().tearDown()

    def test_daily_capacity_split_to_shift_capacity_participates_in_schedule(self) -> None:
        self._seed_route_and_topology("MAT-SPLIT", "PROC-A", capacity_per_shift=10)
        self._seed_order("MO-SPLIT-001", "MAT-SPLIT", 20)
        self.service.save_line_daily_capacity(
            {
                "calendar_date": "2026-04-13",
                "items": [
                    {
                        "company_code": "COMPANY-MAIN",
                        "workshop_code": "WS-1",
                        "line_code": "LINE-1",
                        "process_code": "PROC-A",
                        "planned_capacity_qty": 20,
                        "worker_count": 4,
                        "machine_count": 0,
                        "split_rule": "CUSTOM",
                        "split_day_ratio": 0.25,
                        "split_night_ratio": 0.75,
                        "capacity_change_reason": "班次能力拆分测试",
                    }
                ],
            }
        )
        self.service.save_schedule_calendar_rules(
            {"date_shift_mode_by_date": {"2026-04-13": "BOTH"}}
        )

        generated = self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "PLANNED",
                "use_order_state_window": True,
            }
        )

        rows = self._list_schedule_tasks(str(generated["version_no"]))
        self.assertEqual(rows, [("2026-04-13", "DAY", 5.0), ("2026-04-13", "NIGHT", 15.0)])

    def test_day_insufficient_and_night_sufficient_uses_night_shift_capacity(self) -> None:
        self._seed_route_and_topology("MAT-NIGHT", "PROC-A", capacity_per_shift=10)
        self._seed_order("MO-NIGHT-002", "MAT-NIGHT", 15)
        self.connection.executemany(
            """
            INSERT INTO daily_line_capacity_plan (
                calendar_date, shift_code, company_code, workshop_code, line_code, process_code,
                planned_capacity_qty, worker_count, machine_count, split_rule, split_day_ratio, split_night_ratio,
                capacity_change_type, capacity_change_reason, source_note, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-04-13", "DAY", "COMPANY-MAIN", "WS-1", "LINE-1", "PROC-A", 5, 1, 0, "DAY_ONLY", 1.0, 0.0, "worker_count changed", "白班人手不足", None, "2026-04-13T00:00:00+00:00"),
                ("2026-04-13", "NIGHT", "COMPANY-MAIN", "WS-1", "LINE-1", "PROC-A", 10, 1, 0, "NIGHT_ONLY", 0.0, 1.0, None, None, None, "2026-04-13T00:00:00+00:00"),
            ],
        )
        self.connection.commit()
        self.service.save_schedule_calendar_rules(
            {"date_shift_mode_by_date": {"2026-04-13": "BOTH"}}
        )

        generated = self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "PLANNED",
                "use_order_state_window": True,
            }
        )

        rows = self._list_schedule_tasks(str(generated["version_no"]))
        self.assertEqual(rows, [("2026-04-13", "DAY", 5.0), ("2026-04-13", "NIGHT", 10.0)])

    def test_date_shift_mode_change_updates_scheduled_finish_time(self) -> None:
        self._seed_route_and_topology("MAT-FINISH", "PROC-A", capacity_per_shift=10)
        self._seed_order("MO-FINISH-001", "MAT-FINISH", 30)
        self.service.save_line_daily_capacity(
            {
                "calendar_date": "2026-04-13",
                "items": [
                    {
                        "company_code": "COMPANY-MAIN",
                        "workshop_code": "WS-1",
                        "line_code": "LINE-1",
                        "process_code": "PROC-A",
                        "planned_capacity_qty": 20,
                        "worker_count": 4,
                        "machine_count": 0,
                        "split_rule": "CUSTOM",
                        "split_day_ratio": 0.25,
                        "split_night_ratio": 0.75,
                        "capacity_change_reason": "完成日期敏感性测试",
                    }
                ],
            }
        )

        self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "PLANNED",
                "use_order_state_window": True,
            }
        )
        baseline_row = self.service.list_order_pool()["items"][0]

        self.service.save_schedule_calendar_rules(
            {"date_shift_mode_by_date": {"2026-04-13": "BOTH"}}
        )
        self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "PLANNED",
                "use_order_state_window": True,
            }
        )
        updated_row = self.service.list_order_pool()["items"][0]

        self.assertEqual(str(baseline_row["scheduled_finish_date"]), "2026-04-16")
        self.assertEqual(str(baseline_row["scheduled_finish_time"]), "2026-04-16T20:00:00+08:00")
        self.assertEqual(str(updated_row["scheduled_finish_date"]), "2026-04-14")
        self.assertEqual(str(updated_row["scheduled_finish_time"]), "2026-04-14T20:00:00+08:00")

    def test_rest_day_blocks_exact_start_slot(self) -> None:
        self._seed_route_and_topology("MAT-REST", "PROC-A", capacity_per_shift=10)
        self._seed_order("MO-REST-001", "MAT-REST", 10)
        self.service.save_schedule_calendar_rules(
            {
                "weekend_rest_mode": "NONE",
                "date_shift_mode_by_date": {"2026-04-13": "REST"},
            }
        )

        generated = self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "DEFAULT",
                "use_order_state_window": True,
            }
        )

        rows = self._list_schedule_tasks(str(generated["version_no"]))
        self.assertEqual(rows, [("2026-04-14", "DAY", 10.0)])

        order_row = self.service.list_order_pool()["items"][0]
        self.assertEqual(str(order_row["scheduled_finish_date"]), "2026-04-14")
        self.assertEqual(
            str(order_row["scheduled_finish_time"]),
            "2026-04-14T20:00:00+08:00",
        )

    def test_weekend_rest_mode_applies_without_statutory_holiday_toggle(self) -> None:
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
            ("default", "2026-04-17", "2026-04-17T00:00:00+00:00"),
        )
        self.connection.commit()
        self._seed_route_and_topology("MAT-WEEKEND", "PROC-A", capacity_per_shift=10)
        self._seed_order("MO-WEEKEND-001", "MAT-WEEKEND", 30)

        self.service.save_schedule_calendar_rules(
            {
                "skip_statutory_holidays": False,
                "weekend_rest_mode": "DOUBLE",
            }
        )
        self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "DEFAULT",
                "use_order_state_window": True,
            }
        )
        double_row = self.service.list_order_pool()["items"][0]

        self.service.save_schedule_calendar_rules(
            {
                "skip_statutory_holidays": False,
                "weekend_rest_mode": "NONE",
            }
        )
        self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "DEFAULT",
                "use_order_state_window": True,
            }
        )
        none_row = self.service.list_order_pool()["items"][0]

        self.assertEqual(str(double_row["scheduled_finish_date"]), "2026-04-21")
        self.assertEqual(str(none_row["scheduled_finish_date"]), "2026-04-19")

    def test_capacity_change_type_and_reason_are_separate_fields(self) -> None:
        self._seed_route_and_topology("MAT-SEM", "PROC-A", capacity_per_shift=10)
        payload = self.service.save_line_daily_capacity(
            {
                "calendar_date": "2026-04-13",
                "items": [
                    {
                        "company_code": "COMPANY-MAIN",
                        "workshop_code": "WS-1",
                        "line_code": "LINE-1",
                        "process_code": "PROC-A",
                        "shift_code": "DAY",
                        "worker_count": 1,
                        "machine_count": 0,
                        "capacity_change_type": "worker_count changed",
                        "capacity_change_reason": "人员请假",
                    }
                ],
            }
        )

        row = payload["items"][0]
        self.assertEqual(row["capacity_change_type"], "worker_count changed")
        self.assertEqual(row["capacity_change_reason"], "人员请假")

    def test_material_shortage_generates_risky_plan_instead_of_blocking(self) -> None:
        self._seed_route_and_topology("MAT-RISK", "PROC-A", capacity_per_shift=10)
        self._seed_order("MO-RISK-001", "MAT-RISK", 10)
        self.connection.execute(
            """
            INSERT INTO material_issue_items (
                production_order_no, child_material_code, child_material_name, spec_model, issue_qty,
                supply_type_code, supply_type_name, inventory_qty, inventory_status,
                usage_numerator, usage_denominator, child_unit, expandable, display_order, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "MO-RISK-001", "RM-RISK-001", "短缺物料", "Spec", 5, "PURCHASED", "采购", 0, "LOW",
                1, 1, "PCS", 0, 1, "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

        generated = self.service.generate_schedule(
            {
                "strategy_code": "KEY_ORDER_FIRST",
                "capacity_source_mode": "DEFAULT",
                "use_order_state_window": True,
            }
        )

        self.assertEqual(generated["result_status"], "RISKY")
        self.assertEqual(self.connection.execute("SELECT COUNT(1) FROM schedule_versions").fetchone()[0], 1)
        self.assertGreater(self.connection.execute("SELECT COUNT(1) FROM schedule_tasks").fetchone()[0], 0)

    def test_hard_prerequisite_missing_remains_blocked(self) -> None:
        self._seed_order("MO-BLOCK-001", "MAT-BLOCK", 10)
        with self.assertRaises(AppError) as ctx:
            self.service.generate_schedule(
                {
                    "strategy_code": "KEY_ORDER_FIRST",
                    "capacity_source_mode": "DEFAULT",
                    "use_order_state_window": True,
                }
            )
        self.assertEqual(ctx.exception.code, "SCHEDULE_ROUTE_REQUIRED")

    def _seed_route_and_topology(self, product_code: str, process_code: str, *, capacity_per_shift: int) -> None:
        self.connection.execute(
            """
            INSERT INTO masterdata_process_routes (
                product_code, sequence_no, process_code, process_name_cn, dependency_type,
                route_no, route_name_cn, product_name_cn, is_final_process, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_code, 1, process_code, "工序A", "FS",
                f"ROUTE-{product_code}", "测试路线", "测试产品", 1, "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.execute(
            """
            INSERT INTO masterdata_line_topology (
                company_code, workshop_code, workshop_name, line_code, line_name, process_code,
                capacity_per_shift, required_workers, required_machines, enabled_flag, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "COMPANY-MAIN", "WS-1", "WS-1", "LINE-1", "LINE-1",
                process_code, capacity_per_shift, 1, 0, 1, "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

    def _seed_order(self, order_no: str, material_code: str, quantity: int) -> None:
        self.connection.execute(
            """
            INSERT INTO production_orders (
                production_order_no, material_code, material_name, material_specification, production_qty,
                status, planned_start_date, planned_end_date, source_bill_no, material_list_no, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_no, material_code, "测试产品", "规格A", quantity, "OPEN",
                "2026-04-13", "2026-04-15", f"SRC-{order_no}", f"ML-{order_no}", "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.execute(
            """
            INSERT INTO order_pool_state (
                production_order_no, promised_due_date, expected_start_date, expected_start_time, expected_finish_time,
                priority_level, urgent_flag, lock_flag, frozen_flag, status, order_status,
                completed_qty, remaining_qty, progress_rate, production_batch_no, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_no, "2026-04-15", "2026-04-13", "2026-04-13T08:00:00+08:00", "2026-04-15T18:00:00+08:00",
                5, 0, 0, 0, "OPEN", "OPEN", 0, quantity, 0, f"SRC-{order_no}-B1", "2026-04-13T00:00:00+00:00",
            ),
        )
        self.connection.commit()

    def _list_schedule_tasks(self, version_no: str) -> list[tuple[str, str, float]]:
        rows = self.connection.execute(
            """
            SELECT calendar_date, shift_code, plan_qty
            FROM schedule_tasks
            WHERE version_no = ?
            ORDER BY task_no ASC
            """,
            (version_no,),
        ).fetchall()
        return [(str(row["calendar_date"]), str(row["shift_code"]), float(row["plan_qty"])) for row in rows]


if __name__ == "__main__":
    unittest.main()
