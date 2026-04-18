from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]


class RequestCommandBody(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)


class RefreshSelfMadeMaterialsBody(RequestCommandBody):
    parent_material_codes: list[str] = Field(min_length=1)


class RefreshInventoryBody(RequestCommandBody):
    material_codes: list[str] = Field(default_factory=list)


class BatchDispatchCommandBody(RequestCommandBody):
    order_nos: list[str] = Field(min_length=1)
    command_type: Literal["LOCK", "UNLOCK", "PRIORITY_UP", "PRIORITY_DOWN"]


class AcceptedCommandResponse(BaseModel):
    success: bool = True
    job_id: str
    status_url: str
    message: str


class JobRecord(BaseModel):
    job_id: str
    job_type: str
    target_type: str
    target_key: str
    request_id: str | None = None
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
