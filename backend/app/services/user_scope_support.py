from __future__ import annotations

import sqlite3
from typing import Any

from ..db import fetch_all, fetch_one
from ..errors import bad_request, forbidden


DEFAULT_COMPANY_CODE = "COMPANY-MAIN"
ROLE_SCHEDULER = "SCHEDULER"
ROLE_WORKSHOP_MANAGER = "WORKSHOP_MANAGER"


def current_user_role_code(user: dict[str, Any] | None) -> str:
    return str((user or {}).get("role_code") or "").strip().upper()


def is_workshop_manager(user: dict[str, Any] | None) -> bool:
    return current_user_role_code(user) == ROLE_WORKSHOP_MANAGER


def resolve_manager_user_id(user: dict[str, Any] | None) -> str | None:
    if not is_workshop_manager(user):
        return None
    user_id = str((user or {}).get("user_id") or "").strip()
    if not user_id:
        raise forbidden(
            code="WORKSHOP_MANAGER_USER_ID_REQUIRED",
            message="Current workshop manager user_id is missing.",
        )
    return user_id


def validate_order_summary_scheduler_filter_target(
    connection: sqlite3.Connection,
    workshop_manager_user_id: str,
) -> str:
    normalized_user_id = str(workshop_manager_user_id or "").strip()
    if not normalized_user_id:
        raise bad_request(
            code="ORDER_SUMMARY_WORKSHOP_MANAGER_USER_ID_REQUIRED",
            message="workshop_manager_user_id must be non-empty when provided.",
        )
    row = fetch_one(
        connection,
        """
        SELECT
            users.user_id,
            users.role_code,
            users.enabled_flag,
            COALESCE(visibility.visible_flag, 1) AS visible_flag,
            COUNT(scope.line_code) AS line_scope_count
        FROM app_users users
        LEFT JOIN masterdata_workshop_manager_visibility visibility
          ON visibility.user_id = users.user_id
        LEFT JOIN app_user_line_scopes scope
          ON scope.user_id = users.user_id
        WHERE users.user_id = ?
        GROUP BY users.user_id, users.role_code, users.enabled_flag, COALESCE(visibility.visible_flag, 1)
        LIMIT 1
        """,
        (normalized_user_id,),
    )
    if row is None:
        raise bad_request(
            code="ORDER_SUMMARY_WORKSHOP_MANAGER_NOT_FOUND",
            message="workshop_manager_user_id does not exist.",
            details={"workshop_manager_user_id": normalized_user_id},
        )
    role_code = str(row.get("role_code") or "").strip().upper()
    if role_code != ROLE_WORKSHOP_MANAGER:
        raise bad_request(
            code="ORDER_SUMMARY_WORKSHOP_MANAGER_ROLE_INVALID",
            message="workshop_manager_user_id must reference an enabled workshop manager user.",
            details={"workshop_manager_user_id": normalized_user_id},
        )
    if int(row.get("enabled_flag") or 0) != 1:
        raise bad_request(
            code="ORDER_SUMMARY_WORKSHOP_MANAGER_DISABLED",
            message="workshop_manager_user_id references a disabled workshop manager user.",
            details={"workshop_manager_user_id": normalized_user_id},
        )
    if int(row.get("visible_flag") or 0) != 1:
        raise bad_request(
            code="ORDER_SUMMARY_WORKSHOP_MANAGER_HIDDEN",
            message="workshop_manager_user_id references a hidden workshop manager user.",
            details={"workshop_manager_user_id": normalized_user_id},
        )
    if int(row.get("line_scope_count") or 0) <= 0:
        raise bad_request(
            code="ORDER_SUMMARY_WORKSHOP_MANAGER_LINE_SCOPE_EMPTY",
            message="workshop_manager_user_id must have at least one assigned line scope.",
            details={"workshop_manager_user_id": normalized_user_id},
        )
    return normalized_user_id


def resolve_order_summary_scope_manager_user_id(
    connection: sqlite3.Connection,
    *,
    current_user: dict[str, Any] | None,
    workshop_manager_user_id: str | None,
) -> str | None:
    role_code = current_user_role_code(current_user)
    requested_user_id = str(workshop_manager_user_id or "").strip()
    if workshop_manager_user_id is not None and not requested_user_id:
        raise bad_request(
            code="ORDER_SUMMARY_WORKSHOP_MANAGER_USER_ID_REQUIRED",
            message="workshop_manager_user_id must be non-empty when provided.",
        )
    if role_code == ROLE_WORKSHOP_MANAGER:
        actor_user_id = resolve_manager_user_id(current_user)
        assert actor_user_id is not None
        if requested_user_id and requested_user_id != actor_user_id:
            raise forbidden(
                code="ORDER_SUMMARY_WORKSHOP_MANAGER_FILTER_FORBIDDEN",
                message="Current workshop manager is not allowed to access another workshop manager scope.",
                details={
                    "requested_user_id": requested_user_id,
                    "allowed_user_id": actor_user_id,
                },
            )
        return actor_user_id
    if role_code == ROLE_SCHEDULER:
        if not requested_user_id:
            return None
        return validate_order_summary_scheduler_filter_target(connection, requested_user_id)
    raise forbidden(
        code="ORDER_SUMMARY_ROLE_FORBIDDEN",
        message="Current role is not allowed to access order summary.",
        details={"role_code": role_code},
    )


def list_user_line_scope_rows(
    connection: sqlite3.Connection,
    user_id: str,
) -> list[dict[str, Any]]:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return []
    return fetch_all(
        connection,
        """
        SELECT
            user_id,
            company_code,
            workshop_code,
            line_code
        FROM app_user_line_scopes
        WHERE user_id = ?
        """,
        (normalized_user_id,),
    )


def build_line_scope_key(
    *,
    company_code: str | None,
    workshop_code: str | None,
    line_code: str | None,
) -> tuple[str, str, str]:
    return (
        str(company_code or DEFAULT_COMPANY_CODE).strip().upper() or DEFAULT_COMPANY_CODE,
        str(workshop_code or "").strip().upper(),
        str(line_code or "").strip().upper(),
    )


def user_line_scope_key_set(
    connection: sqlite3.Connection,
    user_id: str,
) -> set[tuple[str, str, str]]:
    rows = list_user_line_scope_rows(connection, user_id)
    return {
        build_line_scope_key(
            company_code=row.get("company_code"),
            workshop_code=row.get("workshop_code"),
            line_code=row.get("line_code"),
        )
        for row in rows
    }


def assert_actor_can_access_line(
    connection: sqlite3.Connection,
    actor: dict[str, Any] | None,
    *,
    company_code: str,
    workshop_code: str,
    line_code: str,
    missing_user_error_code: str,
    forbidden_error_code: str,
    forbidden_message: str,
) -> None:
    if not is_workshop_manager(actor):
        return
    actor_user_id = str((actor or {}).get("user_id") or "").strip()
    if not actor_user_id:
        raise forbidden(
            code=missing_user_error_code,
            message="workshop manager actor.user_id is required.",
        )
    scope_key = build_line_scope_key(
        company_code=company_code,
        workshop_code=workshop_code,
        line_code=line_code,
    )
    allowed_scope_keys = user_line_scope_key_set(connection, actor_user_id)
    if scope_key not in allowed_scope_keys:
        raise forbidden(
            code=forbidden_error_code,
            message=forbidden_message,
            details={
                "user_id": actor_user_id,
                "company_code": scope_key[0],
                "workshop_code": scope_key[1],
                "line_code": scope_key[2],
            },
        )
