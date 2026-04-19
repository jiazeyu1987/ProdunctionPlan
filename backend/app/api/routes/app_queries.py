from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from ...auth import ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER, require_roles
from ...db import get_db
from ...services.app_service import AppService
from ...services.app_service_provider import create_app_service
from ...services.dashboard_query_facade import DashboardQueryFacade
from ...services.dashboard_query_facade_provider import create_dashboard_query_facade
from ...services.masterdata_query_facade import MasterdataQueryFacade
from ...services.masterdata_query_facade_provider import create_masterdata_query_facade
from ...services.order_summary_query_facade import OrderSummaryQueryFacade
from ...services.order_summary_query_facade_provider import create_order_summary_query_facade
from ...services.order_pool_query_facade import OrderPoolQueryFacade
from ...services.order_pool_query_facade_provider import create_order_pool_query_facade
from ...services.reporting_query_facade import ReportingQueryFacade
from ...services.reporting_query_facade_provider import create_reporting_query_facade
from ...services.schedules_query_facade import SchedulesQueryFacade
from ...services.schedules_query_facade_provider import create_schedules_query_facade


router = APIRouter(tags=["app-queries"])


def get_app_service(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> AppService:
    return create_app_service(connection)


def get_order_pool_query_facade(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> OrderPoolQueryFacade:
    return create_order_pool_query_facade(connection)


def get_masterdata_query_facade(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> MasterdataQueryFacade:
    return create_masterdata_query_facade(connection)


def get_reporting_query_facade(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ReportingQueryFacade:
    return create_reporting_query_facade(connection)


def get_schedules_query_facade(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> SchedulesQueryFacade:
    return create_schedules_query_facade(connection)


def get_order_summary_query_facade(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> OrderSummaryQueryFacade:
    return create_order_summary_query_facade(connection)


def get_dashboard_query_facade(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> DashboardQueryFacade:
    return create_dashboard_query_facade(connection)


@router.get("/order-pool")
def list_order_pool(
    service: Annotated[OrderPoolQueryFacade, Depends(get_order_pool_query_facade)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_order_pool()


@router.get("/order-pool/{order_no}")
def get_order_pool_item(
    order_no: str,
    service: Annotated[OrderPoolQueryFacade, Depends(get_order_pool_query_facade)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.get_order_pool_item(order_no)


@router.get("/order-pool/{order_no}/process-timeline")
def get_order_pool_process_timeline(
    order_no: str,
    service: Annotated[OrderPoolQueryFacade, Depends(get_order_pool_query_facade)],
    process_code: str | None = Query(default=None),
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.get_order_pool_process_timeline(
        order_no,
        process_code=process_code,
    )


@router.get("/order-pool/{order_no}/materials")
def list_order_pool_materials(
    order_no: str,
    service: Annotated[OrderPoolQueryFacade, Depends(get_order_pool_query_facade)],
    refresh: bool = Query(default=False),
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_order_pool_materials(order_no, refresh=refresh)


@router.get("/order-pool/materials/{parent_material_code}/children")
def list_material_children(
    parent_material_code: str,
    service: Annotated[OrderPoolQueryFacade, Depends(get_order_pool_query_facade)],
    refresh: bool = Query(default=False),
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_material_children(parent_material_code, refresh=refresh)

@router.get("/schedules/current")
def get_current_schedule(
    service: Annotated[SchedulesQueryFacade, Depends(get_schedules_query_facade)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.get_current_schedule()


@router.get("/schedules/current/tasks")
def list_current_schedule_tasks(
    service: Annotated[SchedulesQueryFacade, Depends(get_schedules_query_facade)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_current_schedule_tasks()


@router.get("/schedules/snapshots")
def list_schedule_snapshots(
    service: Annotated[SchedulesQueryFacade, Depends(get_schedules_query_facade)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_schedule_snapshots()


@router.get("/masterdata/config")
def get_masterdata_config(
    service: Annotated[MasterdataQueryFacade, Depends(get_masterdata_query_facade)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.get_masterdata_config()


@router.get("/masterdata/calendar-rules")
def get_schedule_calendar_rules(
    service: Annotated[MasterdataQueryFacade, Depends(get_masterdata_query_facade)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.get_schedule_calendar_rules()


@router.get("/masterdata/process-routes")
def list_process_routes(
    service: Annotated[MasterdataQueryFacade, Depends(get_masterdata_query_facade)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_process_routes()


@router.get("/masterdata/line-capacity/daily")
def list_line_daily_capacity(
    service: Annotated[MasterdataQueryFacade, Depends(get_masterdata_query_facade)],
    calendar_date: str = Query(...),
    workshop_code: str | None = Query(default=None),
    line_code: str | None = Query(default=None),
    process_code: str | None = Query(default=None),
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER)),
    ] = None,
) -> dict[str, Any]:
    return service.list_line_daily_capacity(
        calendar_date,
        workshop_code=workshop_code,
        line_code=line_code,
        process_code=process_code,
        current_user=current_user,
    )


@router.get("/masterdata/line-capacity/daily/audits")
def list_line_daily_capacity_audits(
    service: Annotated[MasterdataQueryFacade, Depends(get_masterdata_query_facade)],
    calendar_date: str = Query(...),
    workshop_code: str | None = Query(default=None),
    line_code: str | None = Query(default=None),
    process_code: str | None = Query(default=None),
    operator_keyword: str | None = Query(default=None),
    changed_only: bool = Query(default=False),
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER)),
    ] = None,
) -> dict[str, Any]:
    return service.list_line_daily_capacity_audits(
        calendar_date,
        workshop_code=workshop_code,
        line_code=line_code,
        process_code=process_code,
        operator_keyword=operator_keyword,
        changed_only=changed_only,
        current_user=current_user,
    )


@router.get("/reportings")
def list_mes_reportings(
    service: Annotated[ReportingQueryFacade, Depends(get_reporting_query_facade)],
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER)),
    ] = None,
) -> dict[str, Any]:
    return service.list_mes_reportings(
        start_time=start_time,
        end_time=end_time,
        current_user=current_user,
    )


@router.get("/reportings/import-files")
def list_reporting_import_files(
    service: Annotated[ReportingQueryFacade, Depends(get_reporting_query_facade)] = None,
    limit: int = Query(default=50, ge=1, le=200),
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_reporting_import_files(limit=limit)


@router.get("/order-summary")
def get_order_summary(
    service: Annotated[OrderSummaryQueryFacade, Depends(get_order_summary_query_facade)],
    start_date: str = Query(...),
    end_date: str = Query(...),
    workshop_manager_user_id: str | None = Query(default=None),
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER)),
    ] = None,
) -> dict[str, Any]:
    return service.get_order_summary(
        start_date=start_date,
        end_date=end_date,
        workshop_manager_user_id=workshop_manager_user_id,
        current_user=current_user,
    )


@router.get("/order-summary/workshop-managers")
def list_order_summary_workshop_managers(
    service: Annotated[OrderSummaryQueryFacade, Depends(get_order_summary_query_facade)],
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER)),
    ] = None,
) -> dict[str, Any]:
    return service.list_order_summary_workshop_managers(current_user=current_user)


@router.get("/dashboard/scheduler")
def get_scheduler_dashboard(
    service: Annotated[DashboardQueryFacade, Depends(get_dashboard_query_facade)],
    start_date: str = Query(...),
    end_date: str = Query(...),
    top_n: int = Query(default=8),
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER)),
    ] = None,
) -> dict[str, Any]:
    return service.get_scheduler_dashboard(
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        current_user=current_user,
    )
