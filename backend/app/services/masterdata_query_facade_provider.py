from __future__ import annotations

import sqlite3

from .app_service_provider import create_app_service
from .masterdata_query_facade import MasterdataQueryFacade
from .masterdata_query_service import MasterdataQueryService


def create_masterdata_query_facade(
    connection: sqlite3.Connection,
    *,
    app_service=None,
) -> MasterdataQueryFacade:
    return MasterdataQueryFacade(
        MasterdataQueryService(app_service or create_app_service(connection))
    )
