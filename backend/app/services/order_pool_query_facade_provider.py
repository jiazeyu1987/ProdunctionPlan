from __future__ import annotations

import sqlite3

from .app_service import AppService
from .app_service_provider import create_app_service
from .order_pool_query_facade import OrderPoolQueryFacade


def create_order_pool_query_facade(
    connection: sqlite3.Connection,
    *,
    app_service: AppService | None = None,
) -> OrderPoolQueryFacade:
    return OrderPoolQueryFacade(app_service or create_app_service(connection))
