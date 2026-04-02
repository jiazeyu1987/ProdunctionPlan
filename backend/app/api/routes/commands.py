from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from ...auth import ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER, require_roles
from ...db import get_db
from ...repositories.jobs import JobRepository
from ...schemas.jobs import AcceptedCommandResponse


router = APIRouter(tags=["commands"])


def enqueue_command_job(
    connection: sqlite3.Connection,
    *,
    job_type: str,
    target_type: str,
    target_key: str,
    request_id: str | None,
    payload: dict[str, Any],
) -> AcceptedCommandResponse:
    job = JobRepository(connection).enqueue(
        job_type=job_type,
        target_type=target_type,
        target_key=target_key,
        request_id=request_id,
        payload=payload,
    )
    return AcceptedCommandResponse(
        success=True,
        job_id=str(job["job_id"]),
        status_url=f"/api/jobs/{job['job_id']}",
        message="Task accepted.",
    )


@router.post("/dispatch-commands", status_code=202)
def create_dispatch_command(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    order_no = str(payload.get("target_order_no") or "").strip()
    return enqueue_command_job(
        connection,
        job_type="LEGACY_DISPATCH_COMMAND_CREATE",
        target_type="ORDER",
        target_key=order_no or "UNKNOWN",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload=payload,
    )


@router.post("/dispatch-commands/{command_id}/approvals", status_code=202)
def approve_dispatch_command(
    command_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_DISPATCH_COMMAND_APPROVE",
        target_type="DISPATCH_COMMAND",
        target_key=command_id,
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload={**payload, "command_id": command_id},
    )


@router.post("/order-pool/{order_no}/patch", status_code=202)
def patch_order_pool_order(
    order_no: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_ORDER_PATCH",
        target_type="ORDER",
        target_key=order_no,
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload={**payload, "order_no": order_no},
    )


@router.post("/order-pool/{order_no}/delete", status_code=202)
def delete_order_pool_order(
    order_no: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_ORDER_DELETE",
        target_type="ORDER",
        target_key=order_no,
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload={"order_no": order_no},
    )


@router.post("/masterdata/config", status_code=202)
def save_masterdata_config(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_MASTERDATA_CONFIG_SAVE",
        target_type="MASTERDATA",
        target_key="CONFIG",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload=payload,
    )


@router.post("/masterdata/calendar-rules", status_code=202)
def save_schedule_calendar_rules(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_CALENDAR_RULES_SAVE",
        target_type="SCHEDULE_RULES",
        target_key="default",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload=payload,
    )


@router.post("/masterdata/process-routes/create", status_code=202)
def create_process_routes(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_PROCESS_ROUTE_CREATE",
        target_type="PROCESS_ROUTE",
        target_key=str(payload.get("product_code") or "").strip() or "UNKNOWN",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload=payload,
    )


@router.post("/masterdata/process-routes/update", status_code=202)
def update_process_routes(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_PROCESS_ROUTE_UPDATE",
        target_type="PROCESS_ROUTE",
        target_key=str(payload.get("product_code") or "").strip() or "UNKNOWN",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload=payload,
    )


@router.post("/masterdata/process-routes/copy", status_code=202)
def copy_process_routes(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_PROCESS_ROUTE_COPY",
        target_type="PROCESS_ROUTE",
        target_key=str(payload.get("target_product_code") or "").strip() or "UNKNOWN",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload=payload,
    )


@router.post("/masterdata/process-routes/delete", status_code=202)
def delete_process_routes(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_PROCESS_ROUTE_DELETE",
        target_type="PROCESS_ROUTE",
        target_key=str(payload.get("product_code") or "").strip() or "UNKNOWN",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload=payload,
    )


@router.post("/masterdata/line-capacity/daily", status_code=202)
def save_line_daily_capacity(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    current_user: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER)),
    ] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    calendar_date = str(payload.get("calendar_date") or "").strip() or "UNKNOWN"
    actor = {
        "user_id": str(current_user.get("user_id") or "").strip(),
        "username": str(current_user.get("username") or "").strip(),
        "display_name": str(current_user.get("display_name") or "").strip(),
        "role_code": str(current_user.get("role_code") or "").strip(),
    }
    return enqueue_command_job(
        connection,
        job_type="LEGACY_DAILY_LINE_CAPACITY_SAVE",
        target_type="LINE_CAPACITY_DAILY",
        target_key=calendar_date,
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload={**payload, "actor": actor},
    )


@router.post("/masterdata/line-capacity/actuals/rebuild", status_code=202)
def rebuild_line_daily_actual_capacity(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    calendar_date = str(payload.get("calendar_date") or "").strip() or "UNKNOWN"
    return enqueue_command_job(
        connection,
        job_type="LEGACY_DAILY_LINE_CAPACITY_ACTUAL_REBUILD",
        target_type="LINE_CAPACITY_ACTUAL_DAILY",
        target_key=calendar_date,
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload=payload,
    )


@router.post("/schedules/{version_no}/publish", status_code=202)
def publish_schedule_version(
    version_no: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_SCHEDULE_PUBLISH",
        target_type="SCHEDULE_VERSION",
        target_key=version_no,
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload={"version_no": version_no},
    )


@router.post("/simulation/manual/advance-day", status_code=202)
def advance_simulation_one_day(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_SIMULATION_ADVANCE_DAY",
        target_type="SIMULATION",
        target_key="default",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload=payload,
    )


@router.post("/simulation/manual/reset", status_code=202)
def reset_manual_simulation(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_SIMULATION_RESET",
        target_type="SIMULATION",
        target_key="default",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload={},
    )


@router.post("/reportings", status_code=202)
def create_reporting(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER)),
    ] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_REPORT_CREATE",
        target_type="ORDER",
        target_key=str(payload.get("order_no") or "").strip() or "UNKNOWN",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload=payload,
    )


@router.delete("/reportings/{report_id}", status_code=202)
def delete_reporting(
    report_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[
        dict[str, Any],
        Depends(require_roles(ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER)),
    ] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_REPORT_DELETE",
        target_type="REPORT",
        target_key=report_id,
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload={"report_id": report_id},
    )


@router.post("/schedules/generate", status_code=202)
def generate_schedule(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_SCHEDULE_GENERATE",
        target_type="SCHEDULE_VERSION",
        target_key=str(payload.get("base_version_no") or "NEW"),
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload=payload,
    )


@router.post("/test/erp/material-issues/query", status_code=202)
def test_material_issues(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    order_no = str(payload.get("order_no") or "").strip()
    mode = str(payload.get("mode") or "fast").strip().lower() or "fast"
    return enqueue_command_job(
        connection,
        job_type="LEGACY_TEST_MATERIAL_ISSUES_QUERY",
        target_type="ORDER",
        target_key=order_no or "UNKNOWN",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload={"order_no": order_no, "mode": mode},
    )


@router.post("/test/erp/material-supply/query", status_code=202)
def test_material_supply(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    material_code = str(payload.get("material_code") or "").strip()
    return enqueue_command_job(
        connection,
        job_type="LEGACY_TEST_MATERIAL_SUPPLY_QUERY",
        target_type="MATERIAL",
        target_key=material_code or "UNKNOWN",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload={"material_code": material_code},
    )


@router.post("/test/erp/material-inventory/query", status_code=202)
def test_material_inventory(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    material_code = str(payload.get("material_code") or "").strip()
    return enqueue_command_job(
        connection,
        job_type="LEGACY_TEST_MATERIAL_INVENTORY_QUERY",
        target_type="MATERIAL",
        target_key=material_code or "UNKNOWN",
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload={"material_code": material_code},
    )


@router.post("/test/import-production-orders", status_code=202)
def import_production_orders(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    _: Annotated[dict[str, Any], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    assert connection is not None
    return enqueue_command_job(
        connection,
        job_type="LEGACY_IMPORT_PRODUCTION_ORDERS",
        target_type="TEST_IMPORT",
        target_key=str(payload.get("material_code") or "GUIDEWIRE"),
        request_id=str(payload.get("request_id") or "").strip() or None,
        payload=payload,
    )
