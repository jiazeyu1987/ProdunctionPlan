from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from ...auth import ROLE_SCHEDULER, get_current_user, require_roles
from ...db import get_db
from ...errors import forbidden, not_found
from ...repositories.jobs import JobRepository
from ...schemas.common import ItemResponse, ListResponse
from ...schemas.jobs import JobRecord


router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_actor_user_id(job: dict[str, Any]) -> str | None:
    payload = job.get("payload")
    if not isinstance(payload, dict):
        return None
    actor = payload.get("actor")
    if not isinstance(actor, dict):
        return None
    user_id = str(actor.get("user_id") or "").strip()
    return user_id or None


def _assert_job_visible_to_user(
    job: dict[str, Any],
    current_user: dict[str, Any],
) -> None:
    role_code = str(current_user.get("role_code") or "").strip().upper()
    if role_code == ROLE_SCHEDULER:
        return

    current_user_id = str(current_user.get("user_id") or "").strip()
    if current_user_id and _job_actor_user_id(job) == current_user_id:
        return

    raise forbidden(
        code="JOB_ACCESS_FORBIDDEN",
        message="当前用户无权查看该任务。",
        details={"job_id": str(job.get("job_id") or "")},
    )


@router.get("", response_model=ListResponse[JobRecord])
def list_jobs(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None),
    target_key: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: Annotated[dict[str, str], Depends(require_roles(ROLE_SCHEDULER))] = None,
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
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> ItemResponse[JobRecord]:
    item = JobRepository(connection).get(job_id)
    if item is None:
        raise not_found(
            code="JOB_NOT_FOUND",
            message="任务不存在。",
            details={"job_id": job_id},
        )
    _assert_job_visible_to_user(item, current_user)
    return ItemResponse[JobRecord](item=item)
