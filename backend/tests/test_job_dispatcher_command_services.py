from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.job_dispatcher import JobDispatcher


class _StubDispatchCommandService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def create_dispatch_command(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("create_dispatch_command", (payload,)))
        return {"command_id": "CMD-1"}

    def approve_dispatch_command(self, command_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("approve_dispatch_command", (command_id, payload)))
        return {"ok": True}

    def batch_dispatch_commands(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("batch_dispatch_commands", (payload,)))
        return {"count": 1}


class _StubReportingCommandService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def create_reporting(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("create_reporting", (payload,)))
        return {"report_id": "RPT-1"}

    def import_mes_reportings_from_xlsx(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("import_mes_reportings_from_xlsx", (payload,)))
        return {"imported_count": 1}

    def select_reporting_capacity_compare(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("select_reporting_capacity_compare", (payload,)))
        return {"report_id": payload.get("report_id")}

    def delete_reporting(self, report_id: str, actor: object) -> dict[str, object]:
        self.calls.append(("delete_reporting", (report_id, actor)))
        return {"ok": True}


class _StubMasterdataCommandService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def save_schedule_calendar_rules(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("save_schedule_calendar_rules", (payload,)))
        return {"ok": True}

    def save_masterdata_config(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("save_masterdata_config", (payload,)))
        return {"ok": True}

    def create_process_routes(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("create_process_routes", (payload,)))
        return {"ok": True}

    def update_process_routes(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("update_process_routes", (payload,)))
        return {"ok": True}

    def copy_process_routes(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("copy_process_routes", (payload,)))
        return {"ok": True}

    def delete_process_routes(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("delete_process_routes", (payload,)))
        return {"ok": True}


class _StubAppService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def patch_order_pool_order(self, order_no: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("patch_order_pool_order", (order_no, payload)))
        return {"order_no": order_no}

    def delete_order_pool_order(self, order_no: str) -> dict[str, object]:
        self.calls.append(("delete_order_pool_order", (order_no,)))
        return {"order_no": order_no}

    def generate_schedule(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("generate_schedule", (payload,)))
        return {"version_no": "CURRENT"}

    def generate_schedule_by_fact(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("generate_schedule_by_fact", (payload,)))
        return {"version_no": "CURRENT"}

    def save_current_schedule_version(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("save_current_schedule_version", (payload,)))
        return {"version_no": "CURRENT"}

    def load_saved_schedule_version(self, version_no: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("load_saved_schedule_version", (version_no, payload)))
        return {"version_no": version_no}

    def save_line_daily_capacity(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("save_line_daily_capacity", (payload,)))
        return {"ok": True}

    def rebuild_line_daily_actual_capacity(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("rebuild_line_daily_actual_capacity", (payload,)))
        return {"ok": True}

    def advance_simulation_one_day(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("advance_simulation_one_day", (payload,)))
        return {"ok": True}

    def reset_manual_simulation(self) -> dict[str, object]:
        self.calls.append(("reset_manual_simulation", ()))
        return {"ok": True}

    def import_mes_reportings_from_xlsx(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("import_mes_reportings_from_xlsx_app", (payload,)))
        return {"imported_count": 1}
    def import_production_orders_from_erp(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("import_production_orders_from_erp", (payload,)))
        return {"ok": True}

    def test_material_issues(self, order_no: str, mode: str) -> dict[str, object]:
        self.calls.append(("test_material_issues", (order_no, mode)))
        return {"ok": True}

    def test_material_supply(self, material_code: str) -> dict[str, object]:
        self.calls.append(("test_material_supply", (material_code,)))
        return {"ok": True}

    def test_material_inventory(self, material_code: str) -> dict[str, object]:
        self.calls.append(("test_material_inventory", (material_code,)))
        return {"ok": True}


class JobDispatcherCommandServicesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "job-dispatcher-command-services.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.dispatcher = JobDispatcher(self.connection)
        self.dispatch_service = _StubDispatchCommandService()
        self.reporting_service = _StubReportingCommandService()
        self.masterdata_service = _StubMasterdataCommandService()
        self.app_service = _StubAppService()
        self.dispatcher.factory.build_dispatch_command_service = lambda: self.dispatch_service  # type: ignore[method-assign]
        self.dispatcher.factory.build_reporting_command_service = lambda: self.reporting_service  # type: ignore[method-assign]
        self.dispatcher.factory.build_masterdata_command_service = lambda: self.masterdata_service  # type: ignore[method-assign]
        self.dispatcher.factory.build_app_service = lambda: self.app_service  # type: ignore[method-assign]

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_dispatch_routes_use_dispatch_command_service(self) -> None:
        self.dispatcher.dispatch({"job_type": "LEGACY_DISPATCH_COMMAND_CREATE", "payload": {"target_order_no": "MO-1", "command_type": "LOCK"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_DISPATCH_COMMAND_APPROVE", "payload": {"command_id": "CMD-1"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_DISPATCH_COMMAND_BATCH", "payload": {"order_nos": ["MO-1"], "command_type": "LOCK"}})

        self.assertEqual(
            [call[0] for call in self.dispatch_service.calls],
            ["create_dispatch_command", "approve_dispatch_command", "batch_dispatch_commands"],
        )

    def test_reporting_routes_use_reporting_command_service(self) -> None:
        self.dispatcher.dispatch({"job_type": "LEGACY_REPORT_CREATE", "payload": {"process_code": "PROC-A", "report_qty": 1}})
        self.dispatcher.dispatch({"job_type": "LEGACY_REPORT_IMPORT_XLSX", "payload": {"file_path": "C:\\\\tmp\\\\a.xlsx"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_REPORT_CAPACITY_COMPARE_SELECT", "payload": {"report_id": "RPT-1", "audit_id": "AUDIT-1"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_REPORT_DELETE", "payload": {"report_id": "RPT-1", "actor": {"role_code": "SCHEDULER"}}})

        self.assertEqual(
            [call[0] for call in self.reporting_service.calls],
            ["create_reporting", "import_mes_reportings_from_xlsx", "select_reporting_capacity_compare", "delete_reporting"],
        )

    def test_masterdata_routes_use_masterdata_command_service(self) -> None:
        self.dispatcher.dispatch({"job_type": "LEGACY_MASTERDATA_CONFIG_SAVE", "payload": {"line_skeletons": []}})
        self.dispatcher.dispatch({"job_type": "LEGACY_CALENDAR_RULES_SAVE", "payload": {"weekend_rest_mode": "DOUBLE"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_PROCESS_ROUTE_CREATE", "payload": {"product_code": "MAT-1"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_PROCESS_ROUTE_UPDATE", "payload": {"product_code": "MAT-1"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_PROCESS_ROUTE_COPY", "payload": {"target_product_code": "MAT-2"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_PROCESS_ROUTE_DELETE", "payload": {"product_code": "MAT-1"}})

        self.assertEqual(
            [call[0] for call in self.masterdata_service.calls],
            [
                "save_masterdata_config",
                "save_schedule_calendar_rules",
                "create_process_routes",
                "update_process_routes",
                "copy_process_routes",
                "delete_process_routes",
            ],
        )

    def test_remaining_legacy_routes_use_explicit_app_service_methods(self) -> None:
        self.dispatcher.dispatch({"job_type": "LEGACY_ORDER_PATCH", "payload": {"order_no": "MO-1"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_ORDER_DELETE", "payload": {"order_no": "MO-1"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_SCHEDULE_GENERATE", "payload": {"strategy_code": "KEY_ORDER_FIRST"}})
        self.dispatcher.dispatch({"job_type": "FACT_SCHEDULE_GENERATE", "payload": {"capacity_source_mode": "FACT"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_SCHEDULE_SAVE_CURRENT", "payload": {"version_no": "CURRENT"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_SCHEDULE_LOAD_SAVED", "payload": {"version_no": "V1"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_DAILY_LINE_CAPACITY_SAVE", "payload": {"calendar_date": "2026-04-13"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_DAILY_LINE_CAPACITY_ACTUAL_REBUILD", "payload": {"calendar_date": "2026-04-13"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_SIMULATION_ADVANCE_DAY", "payload": {"client_date": "2026-04-13"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_SIMULATION_RESET", "payload": {}})
        self.dispatcher.dispatch({"job_type": "LEGACY_IMPORT_PRODUCTION_ORDERS", "payload": {"material_code": "MAT-1"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_TEST_MATERIAL_ISSUES_QUERY", "payload": {"order_no": "MO-1", "mode": "fast"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_TEST_MATERIAL_SUPPLY_QUERY", "payload": {"material_code": "MAT-1"}})
        self.dispatcher.dispatch({"job_type": "LEGACY_TEST_MATERIAL_INVENTORY_QUERY", "payload": {"material_code": "MAT-1"}})

        self.assertEqual(
            [call[0] for call in self.app_service.calls],
            [
                "patch_order_pool_order",
                "delete_order_pool_order",
                "generate_schedule",
                "generate_schedule_by_fact",
                "save_current_schedule_version",
                "load_saved_schedule_version",
                "save_line_daily_capacity",
                "rebuild_line_daily_actual_capacity",
                "advance_simulation_one_day",
                "reset_manual_simulation",
                "import_production_orders_from_erp",
                "test_material_issues",
                "test_material_supply",
                "test_material_inventory",
            ],
        )


if __name__ == "__main__":
    unittest.main()
