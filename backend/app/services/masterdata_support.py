from __future__ import annotations

import sqlite3
from typing import Any

from ..db import fetch_all


ROLE_WORKSHOP_MANAGER = "WORKSHOP_MANAGER"


def list_enabled_workshop_manager_users(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    return fetch_all(
        connection,
        """
        SELECT
            user_id,
            username,
            display_name,
            role_code,
            enabled_flag
        FROM app_users
        WHERE role_code = ?
          AND enabled_flag = 1
        ORDER BY username ASC, user_id ASC
        """,
        (ROLE_WORKSHOP_MANAGER,),
    )


def list_workshop_manager_visibility_rows(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    return fetch_all(
        connection,
        """
        SELECT
            user_id,
            visible_flag
        FROM masterdata_workshop_manager_visibility
        ORDER BY user_id ASC
        """,
    )


def list_workshop_manager_line_scope_rows(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    return fetch_all(
        connection,
        """
        SELECT
            scope.user_id,
            scope.company_code,
            scope.workshop_code,
            scope.line_code
        FROM app_user_line_scopes scope
        JOIN app_users users
          ON users.user_id = scope.user_id
        WHERE users.role_code = ?
          AND users.enabled_flag = 1
        ORDER BY scope.user_id ASC, scope.company_code ASC, scope.workshop_code ASC, scope.line_code ASC
        """,
        (ROLE_WORKSHOP_MANAGER,),
    )


def list_line_skeleton_rows(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    return fetch_all(
        connection,
        """
        SELECT
            company_code,
            workshop_code,
            workshop_name,
            line_code,
            line_name,
            enabled_flag
        FROM masterdata_line_skeletons
        ORDER BY workshop_code ASC, line_code ASC
        """,
    )
