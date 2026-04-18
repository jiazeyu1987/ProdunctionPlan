from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Callable
from uuid import uuid4

import sqlite3
from fastapi import Depends, Header

from .db import fetch_one, get_db, transaction, utc_now
from .errors import bad_request, forbidden, unauthorized


ROLE_SCHEDULER = "SCHEDULER"
ROLE_WORKSHOP_MANAGER = "WORKSHOP_MANAGER"
SUPPORTED_ROLE_CODES = {ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER}
SESSION_TTL_DAYS = 14


def role_name(role_code: str) -> str:
    if role_code == ROLE_SCHEDULER:
        return "\u6392\u4ea7\u5458"
    if role_code == ROLE_WORKSHOP_MANAGER:
        return "\u8f66\u95f4\u4e3b\u4efb"
    return role_code


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _password_salt() -> str:
    return base64.b64encode(os.urandom(16)).decode("ascii")


def _hash_password(password: str, salt_text: str) -> str:
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_text.encode("utf-8"),
        120_000,
    )
    return base64.b64encode(dk).decode("ascii")


def _normalize_role_code(value: object) -> str:
    role_code = str(value or "").strip().upper()
    if role_code not in SUPPORTED_ROLE_CODES:
        raise bad_request(
            code="ROLE_CODE_INVALID",
            message="角色编码无效。",
            details={"supported": sorted(SUPPORTED_ROLE_CODES)},
        )
    return role_code


def _normalize_password(value: object) -> str:
    password = str(value or "")
    if len(password) < 6:
        raise bad_request(
            code="PASSWORD_TOO_SHORT",
            message="密码长度不能少于 6 个字符。",
        )
    return password


def _normalize_username(value: object) -> str:
    username = str(value or "").strip().lower()
    if not username:
        raise bad_request(code="USERNAME_REQUIRED", message="用户名不能为空。")
    if len(username) < 3:
        raise bad_request(
            code="USERNAME_TOO_SHORT",
            message="用户名长度不能少于 3 个字符。",
        )
    return username


def _public_user(row: dict[str, Any]) -> dict[str, Any]:
    role_code = str(row.get("role_code") or "").strip().upper()
    return {
        "user_id": str(row.get("user_id") or ""),
        "username": str(row.get("username") or ""),
        "display_name": str(row.get("display_name") or ""),
        "role_code": role_code,
        "role_name_cn": role_name(role_code),
        "enabled_flag": int(row.get("enabled_flag") or 0),
    }


def register_user(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    username = _normalize_username(payload.get("username"))
    password = _normalize_password(payload.get("password"))
    display_name = str(payload.get("display_name") or username).strip() or username
    role_code = _normalize_role_code(payload.get("role_code"))
    exists = fetch_one(
        connection,
        "SELECT user_id FROM app_users WHERE username = ? LIMIT 1",
        (username,),
    )
    if exists is not None:
        raise bad_request(
            code="USERNAME_ALREADY_EXISTS",
            message="用户名已存在。",
            details={"username": username},
        )
    user_id = f"USR-{uuid4().hex[:10].upper()}"
    salt_text = _password_salt()
    password_hash = _hash_password(password, salt_text)
    now_text = utc_now()
    with transaction(connection):
        connection.execute(
            """
            INSERT INTO app_users (
                user_id,
                username,
                display_name,
                password_hash,
                password_salt,
                role_code,
                enabled_flag,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                user_id,
                username,
                display_name,
                password_hash,
                salt_text,
                role_code,
                now_text,
                now_text,
            ),
        )
    user = fetch_one(connection, "SELECT * FROM app_users WHERE user_id = ?", (user_id,))
    assert user is not None
    return _public_user(user)


def create_session(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    username = _normalize_username(payload.get("username"))
    password = _normalize_password(payload.get("password"))
    user = fetch_one(
        connection,
        "SELECT * FROM app_users WHERE username = ? LIMIT 1",
        (username,),
    )
    if user is None:
        raise unauthorized(
            code="LOGIN_INVALID",
            message="用户名或密码不正确。",
        )
    if int(user.get("enabled_flag") or 0) != 1:
        raise forbidden(
            code="USER_DISABLED",
            message="当前用户已被禁用。",
            details={"username": username},
        )
    expected_hash = str(user.get("password_hash") or "")
    actual_hash = _hash_password(password, str(user.get("password_salt") or ""))
    if not hmac.compare_digest(expected_hash, actual_hash):
        raise unauthorized(
            code="LOGIN_INVALID",
            message="用户名或密码不正确。",
        )
    now_value = _now_utc()
    token = uuid4().hex + uuid4().hex
    with transaction(connection):
        connection.execute(
            "UPDATE app_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (now_value.isoformat(), str(user["user_id"])),
        )
        connection.execute(
            """
            INSERT INTO app_sessions (
                session_token,
                user_id,
                created_at,
                expires_at,
                revoked_at
            ) VALUES (?, ?, ?, ?, NULL)
            """,
            (
                token,
                str(user["user_id"]),
                now_value.isoformat(),
                (now_value + timedelta(days=SESSION_TTL_DAYS)).isoformat(),
            ),
        )
    return {
        "token": token,
        "token_type": "Bearer",
        "expires_at": (now_value + timedelta(days=SESSION_TTL_DAYS)).isoformat(),
        "user": _public_user(user),
    }


def revoke_session(connection: sqlite3.Connection, session_token: str) -> None:
    with transaction(connection):
        connection.execute(
            "UPDATE app_sessions SET revoked_at = ? WHERE session_token = ? AND revoked_at IS NULL",
            (utc_now(), session_token),
        )


def _parse_bearer_token(authorization: str | None) -> str:
    text = str(authorization or "").strip()
    if not text:
        raise unauthorized(code="AUTH_REQUIRED", message="缺少登录凭证。")
    if not text.lower().startswith("bearer "):
        raise unauthorized(code="AUTH_INVALID", message="登录凭证格式无效。")
    token = text[7:].strip()
    if not token:
        raise unauthorized(code="AUTH_INVALID", message="登录凭证格式无效。")
    return token


def get_current_user(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    token = _parse_bearer_token(authorization)
    session_row = fetch_one(
        connection,
        """
        SELECT
            s.session_token,
            s.expires_at,
            s.revoked_at,
            u.user_id,
            u.username,
            u.display_name,
            u.role_code,
            u.enabled_flag
        FROM app_sessions s
        JOIN app_users u
          ON u.user_id = s.user_id
        WHERE s.session_token = ?
        LIMIT 1
        """,
        (token,),
    )
    if session_row is None:
        raise unauthorized(code="AUTH_INVALID", message="登录会话无效。")
    if session_row.get("revoked_at"):
        raise unauthorized(code="AUTH_EXPIRED", message="登录会话已失效，请重新登录。")
    expires_at = str(session_row.get("expires_at") or "")
    if not expires_at:
        raise unauthorized(code="AUTH_EXPIRED", message="登录会话已失效，请重新登录。")
    try:
        expires_value = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise unauthorized(code="AUTH_EXPIRED", message="登录会话已失效，请重新登录。") from exc
    if expires_value <= _now_utc():
        raise unauthorized(code="AUTH_EXPIRED", message="登录会话已失效，请重新登录。")
    if int(session_row.get("enabled_flag") or 0) != 1:
        raise forbidden(code="USER_DISABLED", message="当前用户已被禁用。")
    return _public_user(session_row) | {"session_token": token}


def require_roles(*role_codes: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    allowed = {str(item).strip().upper() for item in role_codes if str(item).strip()}

    def dependency(
        current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    ) -> dict[str, Any]:
        role_code = str(current_user.get("role_code") or "").strip().upper()
        if role_code not in allowed:
            raise forbidden(
                code="ROLE_FORBIDDEN",
                message="当前用户角色无权访问该资源。",
                details={
                    "role_code": role_code,
                    "allowed_roles": sorted(allowed),
                },
            )
        return current_user

    return dependency

