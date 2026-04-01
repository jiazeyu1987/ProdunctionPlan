from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ...db import get_db
from ...errors import not_found
from ...repositories.jobs import JobRepository
from ...schemas.common import ItemResponse, ListResponse
from ...schemas.jobs import JobRecord


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=ListResponse[JobRecord])
def list_jobs(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None),
    target_key: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> ListResponse[JobRecord]:
    items = JobRepository(connection).list(
        status=status,
        job_type=job_type,
        target_key=target_key,
        limit=limit,
    )
    return ListResponse[JobRecord](items=items, total=len(items))


@router.get("/{job_id}", response_model=ItemResponse[JobRecord])
def get_job(
    job_id: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ItemResponse[JobRecord]:
    item = JobRepository(connection).get(job_id)
    if item is None:
        raise not_found(
            code="JOB_NOT_FOUND",
            message="Job does not exist.",
            details={"job_id": job_id},
        )
    return ItemResponse[JobRecord](item=item)
