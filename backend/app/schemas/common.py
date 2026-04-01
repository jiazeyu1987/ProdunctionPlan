from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class ListResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int


class ItemResponse(BaseModel, Generic[T]):
    item: T


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
