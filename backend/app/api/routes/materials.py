from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from ...db import get_db
from ...schemas.common import ListResponse
from ...schemas.materials import MaterialRow
from ...services.job_dispatcher import ServiceFactory


router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("/{parent_material_code}/children", response_model=ListResponse[MaterialRow])
def list_material_children(
    parent_material_code: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ListResponse[MaterialRow]:
    factory = ServiceFactory(connection)
    items = factory.build_material_query_service().list_bom_children(parent_material_code)
    return ListResponse[MaterialRow](items=items, total=len(items))
