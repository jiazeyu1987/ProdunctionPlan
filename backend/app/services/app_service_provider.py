from __future__ import annotations

import sqlite3

from .app_service import AppService
from .legacy_runtime import LegacyAppRuntime, build_legacy_app_runtime


def create_app_service(
    connection: sqlite3.Connection,
    *,
    runtime: LegacyAppRuntime | None = None,
) -> AppService:
    return AppService(
        connection,
        runtime=runtime or build_legacy_app_runtime(connection),
    )
