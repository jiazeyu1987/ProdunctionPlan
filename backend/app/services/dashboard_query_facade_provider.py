from __future__ import annotations

import sqlite3

from .app_service_provider import create_app_service
from .dashboard_query_facade import DashboardQueryFacade
from .dashboard_query_service import DashboardQueryService
from .order_summary_query_service import OrderSummaryQueryService


def create_dashboard_query_facade(
    connection: sqlite3.Connection,
    *,
    app_service=None,
) -> DashboardQueryFacade:
    host = app_service or create_app_service(connection)
    return DashboardQueryFacade(
        DashboardQueryService(host, OrderSummaryQueryService(host))
    )
