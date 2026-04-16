from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from ...auth import ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER, require_roles
from ...db import get_db
from ...services.app_service import AppService


router = APIRouter(tags=["app-queries"])


def get_app_service(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> AppService:
    return AppService(connection)


@router.get("/order-pool")
def list_order_pool(
    version_no: str | None = Query(default=None),
    service: Annotated[AppService, Depends(get_app_service)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_order_pool(version_no=version_no)


@router.get("/order-pool/{order_no}")
def get_order_pool_item(
    order_no: str,
    version_no: str | None = Query(default=None),
    service: Annotated[AppService, Depends(get_app_service)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.get_order_pool_item(order_no, version_no=version_no)


@router.get("/order-pool/{order_no}/process-timeline")
def get_order_pool_process_timeline(
    order_no: str,
    process_code: str | None = Query(default=None),
    version_no: str | None = Query(default=None),
    service: Annotated[AppService, Depends(get_app_service)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    assert service is not None
    return service.get_order_pool_process_timeline(
        order_no,
        process_code=process_code,
        version_no=version_no,
    )


@router.get("/order-pool/{order_no}/materials")
def list_order_pool_materials(
    order_no: str,
    service: Annotated[AppService, Depends(get_app_service)],
    refresh: bool = Query(default=False),
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_order_pool_materials(order_no, refresh=refresh)


@router.get("/order-pool/materials/{parent_material_code}/children")
def list_material_children(
    parent_material_code: str,
    service: Annotated[AppService, Depends(get_app_service)],
    refresh: bool = Query(default=False),
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_material_children(parent_material_code, refresh=refresh)


@router.get("/schedules")
def list_schedule_versions(
    service: Annotated[AppService, Depends(get_app_service)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_schedule_versions()


@router.get("/schedules/{version_no}")
def get_schedule_version(
    version_no: str,
    service: Annotated[AppService, Depends(get_app_service)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.get_schedule_version(version_no)


@router.get("/schedules/{version_no}/tasks")
def list_schedule_tasks(
    version_no: str,
    service: Annotated[AppService, Depends(get_app_service)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_schedule_tasks(version_no)


@router.get("/schedules/{version_no}/algorithm")
def get_schedule_algorithm(
    version_no: str,
    service: Annotated[AppService, Depends(get_app_service)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.get_schedule_algorithm(version_no)


@router.get("/schedules/{version_no}/diff")
def get_schedule_diff(
    version_no: str,
    compare_with: str | None = Query(default=None),
    service: Annotated[AppService, Depends(get_app_service)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    assert service is not None
    return service.get_schedule_diff(version_no, compare_with)


@router.get("/schedules/{version_no}/material-shortages")
def get_schedule_material_shortages(
    version_no: str,
    service: Annotated[AppService, Depends(get_app_service)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.get_schedule_material_shortages(version_no)


@router.get("/schedules/{version_no}/process-load/daily")
def get_schedule_daily_process_load(
    version_no: str,
    service: Annotated[AppService, Depends(get_app_service)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.get_schedule_daily_process_load(version_no)


@router.get("/masterdata/config")
def get_masterdata_config(
    service: Annotated[AppService, Depends(get_app_service)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.get_masterdata_config()


@router.get("/masterdata/calendar-rules")
def get_schedule_calendar_rules(
    service: Annotated[AppService, Depends(get_app_service)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.get_schedule_calendar_rules()


@router.get("/masterdata/process-routes")
def list_process_routes(
    service: Annotated[AppService, Depends(get_app_service)],
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    return service.list_process_routes()


@router.get("/masterdata/line-capacity/daily")
def list_line_daily_capacity(
    calendar_date: str = Query(...),
    workshop_code: str | None = Query(default=None),
    line_code: str | None = Query(default=None),
    process_code: str | None = Query(default=None),
    service: Annotated[AppService, Depends(get_app_service)] = None,
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER)),
    ] = None,
) -> dict[str, Any]:
    assert service is not None
    return service.list_line_daily_capacity(
        calendar_date,
        workshop_code=workshop_code,
        line_code=line_code,
        process_code=process_code,
        current_user=current_user,
    )


@router.get("/masterdata/line-capacity/daily/audits")
def list_line_daily_capacity_audits(
    calendar_date: str = Query(...),
    workshop_code: str | None = Query(default=None),
    line_code: str | None = Query(default=None),
    process_code: str | None = Query(default=None),
    operator_keyword: str | None = Query(default=None),
    changed_only: bool = Query(default=False),
    service: Annotated[AppService, Depends(get_app_service)] = None,
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER)),
    ] = None,
) -> dict[str, Any]:
    assert service is not None
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
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    service: Annotated[AppService, Depends(get_app_service)] = None,
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER)),
    ] = None,
) -> dict[str, Any]:
    assert service is not None
    return service.list_mes_reportings(
        start_time=start_time,
        end_time=end_time,
        current_user=current_user,
    )


@router.get("/reportings/import-files")
def list_reporting_import_files(
    limit: int = Query(default=50, ge=1, le=200),
    service: Annotated[AppService, Depends(get_app_service)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, Any]:
    assert service is not None
    return service.list_reporting_import_files(limit=limit)


@router.get("/order-summary")
def get_order_summary(
    start_date: str = Query(...),
    end_date: str = Query(...),
    workshop_manager_user_id: str | None = Query(default=None),
    service: Annotated[AppService, Depends(get_app_service)] = None,
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER)),
    ] = None,
) -> dict[str, Any]:
    assert service is not None
    return service.get_order_summary(
        start_date=start_date,
        end_date=end_date,
        workshop_manager_user_id=workshop_manager_user_id,
        current_user=current_user,
    )


@router.get("/order-summary/workshop-managers")
def list_order_summary_workshop_managers(
    service: Annotated[AppService, Depends(get_app_service)] = None,
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER)),
    ] = None,
) -> dict[str, Any]:
    assert service is not None
    return service.list_order_summary_workshop_managers(current_user=current_user)


@router.get("/dashboard/scheduler")
def get_scheduler_dashboard(
    start_date: str = Query(...),
    end_date: str = Query(...),
    top_n: int = Query(default=8),
    service: Annotated[AppService, Depends(get_app_service)] = None,
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER)),
    ] = None,
) -> dict[str, Any]:
    assert service is not None
    return service.get_scheduler_dashboard(
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        current_user=current_user,
    )
