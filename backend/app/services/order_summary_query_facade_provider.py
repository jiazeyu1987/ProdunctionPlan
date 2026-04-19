from __future__ import annotations

import sqlite3

from .app_service_provider import create_app_service
from .order_summary_query_facade import OrderSummaryQueryFacade
from .order_summary_query_service import OrderSummaryQueryService


def create_order_summary_query_facade(
    connection: sqlite3.Connection,
    *,
    app_service=None,
) -> OrderSummaryQueryFacade:
    return OrderSummaryQueryFacade(
        OrderSummaryQueryService(app_service or create_app_service(connection))
    )
