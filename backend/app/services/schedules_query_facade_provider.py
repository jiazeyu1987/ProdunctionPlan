from __future__ import annotations

import sqlite3

from .schedules_query_facade import SchedulesQueryFacade
from .schedules_query_service import SchedulesQueryService


def create_schedules_query_facade(
    connection: sqlite3.Connection,
) -> SchedulesQueryFacade:
    return SchedulesQueryFacade(SchedulesQueryService(connection))
