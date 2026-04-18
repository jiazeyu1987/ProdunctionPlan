from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from ...db import get_db
from ...repositories.jobs import JobRepository
from ...schemas.jobs import AcceptedCommandResponse, RefreshInventoryBody


router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.post("/refresh", response_model=AcceptedCommandResponse, status_code=202)
def refresh_inventory(
    body: RefreshInventoryBody,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> AcceptedCommandResponse:
    target_key = ",".join(body.material_codes) if body.material_codes else "ALL"
    job = JobRepository(connection).enqueue(
        job_type="INVENTORY_REFRESH",
        target_type="MATERIAL",
        target_key=target_key,
        request_id=body.request_id,
        payload={"material_codes": body.material_codes},
    )
    return AcceptedCommandResponse(
        success=True,
        job_id=str(job["job_id"]),
        status_url=f"/api/jobs/{job['job_id']}",
        message="任务已受理。",
    )
