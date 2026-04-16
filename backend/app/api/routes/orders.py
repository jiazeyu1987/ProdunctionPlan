from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ...auth import ROLE_SCHEDULER, require_roles
from ...db import get_db
from ...repositories.jobs import JobRepository
from ...schemas.common import ItemResponse, ListResponse
from ...schemas.jobs import (
    AcceptedCommandResponse,
    RefreshSelfMadeMaterialsBody,
    RequestCommandBody,
)
from ...schemas.materials import CapacityBinding, MaterialRow, WorkReport
from ...schemas.orders import OrderSummary
from ...services.job_dispatcher import ServiceFactory


router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=ListResponse[OrderSummary])
def list_orders(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ListResponse[OrderSummary]:
    factory = ServiceFactory(connection)
    items, total = factory.build_order_query_service().list_orders(
        keyword=keyword,
        status=status,
        page=page,
        page_size=page_size,
    )
    return ListResponse[OrderSummary](items=items, total=total)


@router.get("/{order_no}", response_model=ItemResponse[OrderSummary])
def get_order(
    order_no: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ItemResponse[OrderSummary]:
    factory = ServiceFactory(connection)
    item = factory.build_order_query_service().get_order(order_no)
    return ItemResponse[OrderSummary](item=item)


@router.get("/{order_no}/materials", response_model=ListResponse[MaterialRow])
def list_order_materials(
    order_no: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ListResponse[MaterialRow]:
    factory = ServiceFactory(connection)
    items = factory.build_material_query_service().list_order_materials(order_no)
    return ListResponse[MaterialRow](items=items, total=len(items))


@router.get("/{order_no}/reports", response_model=ListResponse[WorkReport])
def list_order_reports(
    order_no: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ListResponse[WorkReport]:
    factory = ServiceFactory(connection)
    items = factory.build_report_query_service().list_reports(order_no)
    return ListResponse[WorkReport](items=items, total=len(items))


@router.get("/{order_no}/capacity", response_model=ListResponse[CapacityBinding])
def list_order_capacity(
    order_no: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ListResponse[CapacityBinding]:
    factory = ServiceFactory(connection)
    items = factory.build_capacity_query_service().list_capacity(order_no)
    return ListResponse[CapacityBinding](items=items, total=len(items))


@router.post(
    "/{order_no}/materials/refresh",
    response_model=AcceptedCommandResponse,
    status_code=202,
)
def refresh_order_materials(
    order_no: str,
    body: RequestCommandBody,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict[str, str], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    factory = ServiceFactory(connection)
    factory.build_order_query_service().get_order(order_no)
    job = JobRepository(connection).enqueue(
        job_type="ORDER_MATERIALS_REFRESH",
        target_type="ORDER",
        target_key=order_no,
        request_id=body.request_id,
        payload={"order_no": order_no},
    )
    return AcceptedCommandResponse(
        success=True,
        job_id=str(job["job_id"]),
        status_url=f"/api/jobs/{job['job_id']}",
        message="Task accepted.",
    )


@router.post(
    "/{order_no}/self-made-materials/refresh",
    response_model=AcceptedCommandResponse,
    status_code=202,
)
def refresh_self_made_materials(
    order_no: str,
    body: RefreshSelfMadeMaterialsBody,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict[str, str], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    factory = ServiceFactory(connection)
    factory.build_order_query_service().get_order(order_no)
    job = JobRepository(connection).enqueue(
        job_type="SELF_MADE_MATERIALS_REFRESH",
        target_type="ORDER",
        target_key=order_no,
        request_id=body.request_id,
        payload={
            "order_no": order_no,
            "parent_material_codes": body.parent_material_codes,
        },
    )
    return AcceptedCommandResponse(
        success=True,
        job_id=str(job["job_id"]),
        status_url=f"/api/jobs/{job['job_id']}",
        message="Task accepted.",
    )


@router.post(
    "/sync-from-erp/apply",
    response_model=AcceptedCommandResponse,
    status_code=202,
)
def apply_orders_sync_from_erp(
    body: RequestCommandBody,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict[str, str], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    job = JobRepository(connection).enqueue(
        job_type="ORDERS_SYNC_FROM_ERP",
        target_type="ORDER",
        target_key="ALL",
        request_id=body.request_id,
        payload={},
    )
    return AcceptedCommandResponse(
        success=True,
        job_id=str(job["job_id"]),
        status_url=f"/api/jobs/{job['job_id']}",
        message="Task accepted.",
    )


@router.post(
    "/sync-from-erp",
    response_model=AcceptedCommandResponse,
    status_code=202,
)
def sync_orders_from_erp(
    body: RequestCommandBody,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict[str, str], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> AcceptedCommandResponse:
    return apply_orders_sync_from_erp(body, connection, _)


@router.get("/sync-from-erp/preview")
def preview_orders_sync_from_erp(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict[str, str], Depends(require_roles(ROLE_SCHEDULER))] = None,
) -> dict[str, object]:
    factory = ServiceFactory(connection)
    return factory.build_order_sync_service().preview_orders_from_erp_incremental_sync()
