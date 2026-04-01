from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from ...db import get_db
from ...services.app_service import AppService


router = APIRouter(tags=["app-queries"])


def get_app_service(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> AppService:
    return AppService(connection)


@router.get("/order-pool")
def list_order_pool(
    service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, Any]:
    return service.list_order_pool()


@router.get("/order-pool/{order_no}")
def get_order_pool_item(
    order_no: str,
    service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, Any]:
    return service.get_order_pool_item(order_no)


@router.get("/order-pool/{order_no}/materials")
def list_order_pool_materials(
    order_no: str,
    service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, Any]:
    return service.list_order_pool_materials(order_no, refresh=False)


@router.get("/order-pool/materials/{parent_material_code}/children")
def list_material_children(
    parent_material_code: str,
    service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, Any]:
    return service.list_material_children(parent_material_code, refresh=False)


@router.get("/schedules")
def list_schedule_versions(
    service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, Any]:
    return service.list_schedule_versions()


@router.get("/schedules/{version_no}")
def get_schedule_version(
    version_no: str,
    service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, Any]:
    return service.get_schedule_version(version_no)


@router.get("/schedules/{version_no}/tasks")
def list_schedule_tasks(
    version_no: str,
    service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, Any]:
    return service.list_schedule_tasks(version_no)


@router.get("/schedules/{version_no}/algorithm")
def get_schedule_algorithm(
    version_no: str,
    service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, Any]:
    return service.get_schedule_algorithm(version_no)


@router.get("/schedules/{version_no}/diff")
def get_schedule_diff(
    version_no: str,
    compare_with: str | None = Query(default=None),
    service: Annotated[AppService, Depends(get_app_service)] = None,
) -> dict[str, Any]:
    assert service is not None
    return service.get_schedule_diff(version_no, compare_with)


@router.get("/schedules/{version_no}/process-load/daily")
def get_schedule_daily_process_load(
    version_no: str,
    service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, Any]:
    return service.get_schedule_daily_process_load(version_no)


@router.get("/masterdata/config")
def get_masterdata_config(
    service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, Any]:
    return service.get_masterdata_config()


@router.get("/masterdata/calendar-rules")
def get_schedule_calendar_rules(
    service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, Any]:
    return service.get_schedule_calendar_rules()


@router.get("/masterdata/process-routes")
def list_process_routes(
    service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, Any]:
    return service.list_process_routes()


@router.get("/reportings")
def list_mes_reportings(
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    service: Annotated[AppService, Depends(get_app_service)] = None,
) -> dict[str, Any]:
    assert service is not None
    return service.list_mes_reportings(start_time=start_time, end_time=end_time)
