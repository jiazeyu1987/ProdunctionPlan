from __future__ import annotations

import sqlite3
from typing import Any

from ..gateway.orders import ERPOrderGateway
from ..gateway.inventory import ERPInventoryGateway
from ..gateway.materials import ERPMaterialGateway
from ..gateway.supply import ERPSupplyGateway
from ..repositories.capacity import CapacityRepository
from ..repositories.inventory import InventoryRepository
from ..repositories.materials import BomChildrenRepository, MaterialIssueRepository
from ..repositories.orders import ProductionOrderRepository
from ..repositories.reports import WorkReportRepository
from ..repositories.supply import MaterialSupplyRepository
from .backup_service import BACKUP_TRIGGER_AUTO, BACKUP_TRIGGER_MANUAL, BackupService, restore_backup_job
from .capacity_query_service import CapacityQueryService
from .inventory_refresh_service import InventoryRefreshService
from .dispatch_command_service import DispatchCommandService
from .masterdata_command_service import MasterdataCommandService
from .material_query_service import MaterialQueryService
from .material_refresh_service import MaterialRefreshService
from .order_sync_service import OrderSyncService
from .order_query_service import OrderQueryService
from .reporting_command_service import ReportingCommandService
from .report_query_service import ReportQueryService


class ServiceFactory:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.order_repository = ProductionOrderRepository(connection)
        self.material_issue_repository = MaterialIssueRepository(connection)
        self.bom_children_repository = BomChildrenRepository(connection)
        self.inventory_repository = InventoryRepository(connection)
        self.supply_repository = MaterialSupplyRepository(connection)
        self.report_repository = WorkReportRepository(connection)
        self.capacity_repository = CapacityRepository(connection)
        self.order_gateway = ERPOrderGateway()
        self.material_gateway = ERPMaterialGateway()
        self.supply_gateway = ERPSupplyGateway()
        self.inventory_gateway = ERPInventoryGateway()

    def build_order_query_service(self) -> OrderQueryService:
        return OrderQueryService(self.order_repository)

    def build_material_query_service(self) -> MaterialQueryService:
        return MaterialQueryService(
            order_repository=self.order_repository,
            material_issue_repository=self.material_issue_repository,
            bom_children_repository=self.bom_children_repository,
            inventory_repository=self.inventory_repository,
            supply_repository=self.supply_repository,
        )

    def build_report_query_service(self) -> ReportQueryService:
        return ReportQueryService(
            order_repository=self.order_repository,
            report_repository=self.report_repository,
        )

    def build_capacity_query_service(self) -> CapacityQueryService:
        return CapacityQueryService(
            order_repository=self.order_repository,
            capacity_repository=self.capacity_repository,
        )

    def build_material_refresh_service(self) -> MaterialRefreshService:
        return MaterialRefreshService(
            connection=self.connection,
            order_repository=self.order_repository,
            material_issue_repository=self.material_issue_repository,
            bom_children_repository=self.bom_children_repository,
            supply_repository=self.supply_repository,
            material_gateway=self.material_gateway,
            supply_gateway=self.supply_gateway,
        )

    def build_order_sync_service(self) -> OrderSyncService:
        return OrderSyncService(
            connection=self.connection,
            order_repository=self.order_repository,
            order_gateway=self.order_gateway,
        )

    def build_inventory_refresh_service(self) -> InventoryRefreshService:
        return InventoryRefreshService(
            connection=self.connection,
            inventory_repository=self.inventory_repository,
            material_issue_repository=self.material_issue_repository,
            bom_children_repository=self.bom_children_repository,
            inventory_gateway=self.inventory_gateway,
        )

    def build_backup_service(self) -> BackupService:
        return BackupService(self.connection)

    def build_reporting_command_service(self) -> ReportingCommandService:
        from .app_service_provider import create_app_service

        return ReportingCommandService(create_app_service(self.connection))

    def build_masterdata_command_service(self) -> MasterdataCommandService:
        from .app_service_provider import create_app_service

        return MasterdataCommandService(create_app_service(self.connection))

    def build_dispatch_command_service(self) -> DispatchCommandService:
        from .app_service_provider import create_app_service

        return DispatchCommandService(create_app_service(self.connection))

    def build_app_service(self):
        from .app_service_provider import create_app_service

        return create_app_service(self.connection)


class JobDispatcher:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.factory = ServiceFactory(connection)

    @staticmethod
    def dispatch_without_connection(job: dict[str, Any]) -> dict[str, Any]:
        job_type = str(job["job_type"])
        if job_type == "DB_BACKUP_RESTORE":
            return restore_backup_job(job)
        raise ValueError(f"Unsupported connectionless job type: {job_type}")

    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = job.get("payload") or {}
        job_type = str(job["job_type"])

        if job_type == "DB_BACKUP_CREATE":
            return self.factory.build_backup_service().create_backup(
                trigger=BACKUP_TRIGGER_MANUAL,
                actor=payload.get("actor"),
            )
        if job_type == "DB_BACKUP_CREATE_AUTO":
            return self.factory.build_backup_service().create_backup(
                trigger=BACKUP_TRIGGER_AUTO,
                actor=payload.get("actor"),
            )
        if job_type == "DB_BACKUP_RESTORE":
            return self.dispatch_without_connection(job)
        if job_type == "ORDER_MATERIALS_REFRESH":
            return self.factory.build_material_refresh_service().refresh_order_materials(
                str(payload["order_no"])
            )
        if job_type == "SELF_MADE_MATERIALS_REFRESH":
            return self.factory.build_material_refresh_service().refresh_self_made_materials(
                str(payload["order_no"]),
                [str(item) for item in payload.get("parent_material_codes", [])],
            )
        if job_type == "INVENTORY_REFRESH":
            return self.factory.build_inventory_refresh_service().refresh_inventory(
                [str(item) for item in payload.get("material_codes", [])]
            )
        if job_type == "ORDERS_SYNC_FROM_ERP":
            return self.factory.build_order_sync_service().sync_orders_from_erp_incremental()
        if job_type == "LEGACY_ORDER_PATCH":
            return self.factory.build_app_service().patch_order_pool_order(str(payload["order_no"]), payload)
        if job_type == "LEGACY_ORDER_DELETE":
            return self.factory.build_app_service().delete_order_pool_order(str(payload["order_no"]))
        if job_type == "LEGACY_DISPATCH_COMMAND_CREATE":
            return self.factory.build_dispatch_command_service().create_dispatch_command(payload)
        if job_type == "LEGACY_DISPATCH_COMMAND_APPROVE":
            return self.factory.build_dispatch_command_service().approve_dispatch_command(
                str(payload["command_id"]),
                payload,
            )
        if job_type == "LEGACY_DISPATCH_COMMAND_BATCH":
            return self.factory.build_dispatch_command_service().batch_dispatch_commands(payload)
        if job_type == "LEGACY_REPORT_CREATE":
            return self.factory.build_reporting_command_service().create_reporting(payload)
        if job_type == "LEGACY_REPORT_IMPORT_XLSX":
            return self.factory.build_reporting_command_service().import_mes_reportings_from_xlsx(payload)
        if job_type == "LEGACY_REPORT_CAPACITY_COMPARE_SELECT":
            return self.factory.build_reporting_command_service().select_reporting_capacity_compare(payload)
        if job_type == "LEGACY_REPORT_DELETE":
            return self.factory.build_reporting_command_service().delete_reporting(
                str(payload["report_id"]),
                payload.get("actor"),
            )
        if job_type == "LEGACY_SCHEDULE_GENERATE":
            return self.factory.build_app_service().generate_schedule(payload)
        if job_type == "FACT_SCHEDULE_GENERATE":
            return self.factory.build_app_service().generate_schedule_by_fact(payload)
        if job_type == "LEGACY_SCHEDULE_SAVE_CURRENT":
            return self.factory.build_app_service().save_current_schedule_version(payload)
        if job_type == "LEGACY_SCHEDULE_LOAD_SAVED":
            return self.factory.build_app_service().load_saved_schedule_version(
                str(payload["version_no"]),
                payload,
            )
        if job_type == "LEGACY_CALENDAR_RULES_SAVE":
            return self.factory.build_masterdata_command_service().save_schedule_calendar_rules(payload)
        if job_type == "LEGACY_MASTERDATA_CONFIG_SAVE":
            return self.factory.build_masterdata_command_service().save_masterdata_config(payload)
        if job_type == "LEGACY_PROCESS_ROUTE_CREATE":
            return self.factory.build_masterdata_command_service().create_process_routes(payload)
        if job_type == "LEGACY_PROCESS_ROUTE_UPDATE":
            return self.factory.build_masterdata_command_service().update_process_routes(payload)
        if job_type == "LEGACY_PROCESS_ROUTE_COPY":
            return self.factory.build_masterdata_command_service().copy_process_routes(payload)
        if job_type == "LEGACY_PROCESS_ROUTE_DELETE":
            return self.factory.build_masterdata_command_service().delete_process_routes(payload)
        if job_type == "LEGACY_DAILY_LINE_CAPACITY_SAVE":
            return self.factory.build_app_service().save_line_daily_capacity(payload)
        if job_type == "LEGACY_DAILY_LINE_CAPACITY_ACTUAL_REBUILD":
            return self.factory.build_app_service().rebuild_line_daily_actual_capacity(payload)
        if job_type == "LEGACY_SIMULATION_ADVANCE_DAY":
            return self.factory.build_app_service().advance_simulation_one_day(payload)
        if job_type == "LEGACY_SIMULATION_RESET":
            return self.factory.build_app_service().reset_manual_simulation()
        if job_type == "LEGACY_IMPORT_PRODUCTION_ORDERS":
            return self.factory.build_app_service().import_production_orders_from_erp(payload)
        if job_type == "LEGACY_TEST_MATERIAL_ISSUES_QUERY":
            return self.factory.build_app_service().test_material_issues(
                str(payload["order_no"]),
                str(payload.get("mode") or "fast"),
            )
        if job_type == "LEGACY_TEST_MATERIAL_SUPPLY_QUERY":
            return self.factory.build_app_service().test_material_supply(
                str(payload["material_code"]),
            )
        if job_type == "LEGACY_TEST_MATERIAL_INVENTORY_QUERY":
            return self.factory.build_app_service().test_material_inventory(
                str(payload["material_code"]),
            )

        raise ValueError(f"Unsupported job type: {job_type}")
