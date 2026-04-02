from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from ...auth import create_session, get_current_user, register_user, revoke_session
from ...db import get_db


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
) -> dict[str, Any]:
    assert connection is not None
    user = register_user(connection, payload)
    return {"user": user}


@router.post("/login")
def login(
    payload: dict[str, Any] = Body(default_factory=dict),
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
) -> dict[str, Any]:
    assert connection is not None
    return create_session(connection, payload)


@router.post("/logout")
def logout(
    connection: Annotated[sqlite3.Connection, Depends(get_db)] = None,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)] = None,
) -> dict[str, bool]:
    assert connection is not None
    assert current_user is not None
    revoke_session(connection, str(current_user.get("session_token") or ""))
    return {"ok": True}


@router.get("/me")
def me(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    return {"user": {key: value for key, value in current_user.items() if key != "session_token"}}
