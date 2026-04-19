from __future__ import annotations

import sqlite3

from .app_service_provider import create_app_service
from .reporting_query_facade import ReportingQueryFacade
from .reporting_query_service import ReportingQueryService


def create_reporting_query_facade(
    connection: sqlite3.Connection,
    *,
    app_service=None,
) -> ReportingQueryFacade:
    return ReportingQueryFacade(
        ReportingQueryService(app_service or create_app_service(connection))
    )
