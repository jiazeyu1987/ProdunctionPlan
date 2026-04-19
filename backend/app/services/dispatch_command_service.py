from __future__ import annotations

from typing import Any

from ..db import fetch_one, transaction, utc_now
from ..errors import bad_request, not_found


def _to_number(value: object, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


def _normalize_priority_level(value: object, default: int = 5) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(5, level))


class DispatchCommandService:
    def __init__(self, host: Any) -> None:
        self.host = host
        self.connection = host.connection

    def create_dispatch_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        order_no = str(payload.get("target_order_no") or "").strip()
        command_type = str(payload.get("command_type") or "").strip().upper()
        if not order_no or not command_type:
            raise bad_request(
                code="DISPATCH_COMMAND_INVALID",
                message="target_order_no and command_type are required.",
            )
        self.host._require_order(order_no)
        with transaction(self.connection):
            command_id = self._insert_dispatch_command_record(
                target_order_no=order_no,
                command_type=command_type,
                payload=payload,
            )
        return {"command_id": command_id}

    def approve_dispatch_command(
        self,
        command_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = fetch_one(
            self.connection,
            """
            SELECT command_id, target_order_no, command_type, status
            FROM dispatch_commands
            WHERE command_id = ?
            """,
            (command_id,),
        )
        if row is None:
            raise not_found(
                code="DISPATCH_COMMAND_NOT_FOUND",
                message="Dispatch command does not exist.",
                details={"command_id": command_id},
            )
        with transaction(self.connection):
            self._approve_dispatch_command_record(
                command_id=command_id,
                target_order_no=str(row["target_order_no"]),
                command_type=str(row["command_type"]),
                previous_status=str(row["status"] or ""),
                payload=payload,
            )
        return {"ok": True}

    def batch_dispatch_commands(self, payload: dict[str, Any]) -> dict[str, Any]:
        command_type = str(payload.get("command_type") or "").strip().upper()
        if command_type not in {"LOCK", "UNLOCK", "PRIORITY_UP", "PRIORITY_DOWN"}:
            raise bad_request(
                code="ORDER_BATCH_DISPATCH_COMMAND_INVALID",
                message="command_type must be LOCK, UNLOCK, PRIORITY_UP or PRIORITY_DOWN.",
                details={"command_type": command_type or None},
            )

        order_nos = self._normalize_batch_dispatch_order_nos(payload.get("order_nos"))
        if len(order_nos) == 0:
            raise bad_request(
                code="ORDER_BATCH_DISPATCH_EMPTY",
                message="order_nos must contain at least one order.",
            )

        order_rows_by_no = self.host._get_order_rows_by_nos(order_nos)
        missing_order_nos = [order_no for order_no in order_nos if order_no not in order_rows_by_no]
        if len(missing_order_nos) > 0:
            raise not_found(
                code="ORDER_BATCH_DISPATCH_ORDER_NOT_FOUND",
                message="Some orders do not exist.",
                details={"order_nos": missing_order_nos},
            )

        state_rows_by_no = self.host._get_order_state_map(order_nos)
        completed_order_nos: list[str] = []
        frozen_order_nos: list[str] = []
        invalid_lock_state_order_nos: list[str] = []
        invalid_priority_state_order_nos: list[str] = []
        for order_no in order_nos:
            order_row = order_rows_by_no[order_no]
            state_row = state_rows_by_no.get(order_no)
            if self._is_order_completed_for_dispatch(order_row, state_row):
                completed_order_nos.append(order_no)
            if int(_to_number((state_row or {}).get("frozen_flag"), 0)) == 1:
                frozen_order_nos.append(order_no)
            is_locked = int(_to_number((state_row or {}).get("lock_flag"), 0)) == 1
            if command_type == "LOCK" and is_locked:
                invalid_lock_state_order_nos.append(order_no)
            if command_type == "UNLOCK" and not is_locked:
                invalid_lock_state_order_nos.append(order_no)
            if (
                command_type == "PRIORITY_UP"
                and _normalize_priority_level((state_row or {}).get("priority_level"), 5)
                <= 1
            ):
                invalid_priority_state_order_nos.append(order_no)
            if (
                command_type == "PRIORITY_DOWN"
                and _normalize_priority_level((state_row or {}).get("priority_level"), 5)
                >= 5
            ):
                invalid_priority_state_order_nos.append(order_no)

        if len(completed_order_nos) > 0:
            raise bad_request(
                code="ORDER_BATCH_DISPATCH_COMPLETED",
                message="Completed orders cannot be batch dispatched.",
                details={"order_nos": completed_order_nos, "command_type": command_type},
            )
        if len(frozen_order_nos) > 0:
            raise bad_request(
                code="ORDER_BATCH_DISPATCH_FROZEN",
                message="Frozen orders cannot be batch dispatched.",
                details={"order_nos": frozen_order_nos, "command_type": command_type},
            )
        if len(invalid_lock_state_order_nos) > 0:
            raise bad_request(
                code="ORDER_BATCH_DISPATCH_LOCK_STATE_INVALID",
                message=(
                    "Selected orders are already locked."
                    if command_type == "LOCK"
                    else "Selected orders are not locked."
                ),
                details={"order_nos": invalid_lock_state_order_nos, "command_type": command_type},
            )
        if len(invalid_priority_state_order_nos) > 0:
            raise bad_request(
                code="ORDER_BATCH_DISPATCH_PRIORITY_STATE_INVALID",
                message=(
                    "Selected orders are already at the highest priority."
                    if command_type == "PRIORITY_UP"
                    else "Selected orders are already at the lowest priority."
                ),
                details={"order_nos": invalid_priority_state_order_nos, "command_type": command_type},
            )

        actor_name = self._resolve_dispatch_actor_name(payload.get("actor"))
        reason = str(payload.get("reason") or "").strip() or (
            "Batch lock production orders"
            if command_type == "LOCK"
            else "Batch unlock production orders"
            if command_type == "UNLOCK"
            else "Batch priority-up production orders"
            if command_type == "PRIORITY_UP"
            else "Batch priority-down production orders"
        )
        decision_reason = str(payload.get("decision_reason") or "").strip() or "Batch dispatch auto approval"
        effective_time = payload.get("effective_time") or utc_now()
        decision_time = payload.get("decision_time") or effective_time
        command_ids: list[str] = []
        with transaction(self.connection):
            for order_no in order_nos:
                command_id = self._insert_dispatch_command_record(
                    target_order_no=order_no,
                    command_type=command_type,
                    payload={
                        "effective_time": effective_time,
                        "reason": reason,
                        "created_by": actor_name,
                    },
                )
                self._approve_dispatch_command_record(
                    command_id=command_id,
                    target_order_no=order_no,
                    command_type=command_type,
                    previous_status="PENDING",
                    payload={
                        "approver": actor_name,
                        "decision": "APPROVED",
                        "decision_reason": decision_reason,
                        "decision_time": decision_time,
                    },
                )
                command_ids.append(command_id)
        return {
            "command_ids": command_ids,
            "command_type": command_type,
            "order_nos": order_nos,
            "count": len(order_nos),
        }

    def _normalize_batch_dispatch_order_nos(self, value: object) -> list[str]:
        if not isinstance(value, list):
            raise bad_request(
                code="ORDER_BATCH_DISPATCH_ORDER_NOS_INVALID",
                message="order_nos must be an array.",
            )
        normalized_order_nos: list[str] = []
        seen_order_nos: set[str] = set()
        for item in value:
            order_no = str(item or "").strip()
            if not order_no or order_no in seen_order_nos:
                continue
            seen_order_nos.add(order_no)
            normalized_order_nos.append(order_no)
        return normalized_order_nos

    def _is_order_completed_for_dispatch(
        self,
        base_row: dict[str, Any],
        state_row: dict[str, Any] | None,
    ) -> bool:
        explicit_status = str(
            (state_row or {}).get("order_status") or (state_row or {}).get("status") or ""
        ).strip().upper()
        if explicit_status in {"OPEN", "IN_PROGRESS"}:
            return False
        if explicit_status in {"DONE", "COMPLETED", "CLOSED"}:
            return True

        production_qty = _to_number(base_row.get("production_qty"), 0)
        completed_qty = _to_number((state_row or {}).get("completed_qty"), 0)
        remaining_qty = (state_row or {}).get("remaining_qty")
        if remaining_qty is not None and _to_number(remaining_qty, 0) <= 1e-9:
            return True
        if production_qty > 1e-9 and completed_qty + 1e-9 >= production_qty:
            return True

        progress_rate = (state_row or {}).get("progress_rate")
        if progress_rate is not None and _to_number(progress_rate, 0) >= 99.999:
            return True
        return False

    def _resolve_dispatch_actor_name(self, actor: object) -> str:
        if isinstance(actor, dict):
            for field in ("username", "display_name", "user_id"):
                value = str(actor.get(field) or "").strip()
                if value:
                    return value
        return "system"

    def _insert_dispatch_command_record(
        self,
        *,
        target_order_no: str,
        command_type: str,
        payload: dict[str, Any],
    ) -> str:
        from uuid import uuid4

        command_id = f"CMD-{uuid4().hex[:10].upper()}"
        now = utc_now()
        self.connection.execute(
            """
            INSERT INTO dispatch_commands (
                command_id,
                target_order_no,
                command_type,
                status,
                effective_time,
                reason,
                created_by,
                approver,
                decision,
                decision_reason,
                decision_time,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                command_id,
                target_order_no,
                command_type,
                "PENDING",
                payload.get("effective_time"),
                payload.get("reason"),
                payload.get("created_by"),
                None,
                None,
                None,
                None,
                now,
                now,
            ),
        )
        return command_id

    def _approve_dispatch_command_record(
        self,
        *,
        command_id: str,
        target_order_no: str,
        command_type: str,
        previous_status: str,
        payload: dict[str, Any],
    ) -> None:
        decision = str(payload.get("decision") or "").strip().upper() or "APPROVED"
        now = utc_now()
        self.connection.execute(
            """
            UPDATE dispatch_commands
            SET status = ?,
                approver = ?,
                decision = ?,
                decision_reason = ?,
                decision_time = ?,
                updated_at = ?
            WHERE command_id = ?
            """,
            (
                decision,
                payload.get("approver"),
                decision,
                payload.get("decision_reason"),
                payload.get("decision_time") or now,
                now,
                command_id,
            ),
        )
        if decision == "APPROVED" and previous_status.strip().upper() != "APPROVED":
            self._apply_dispatch_command(
                target_order_no=target_order_no,
                command_type=command_type,
            )

    def _apply_dispatch_command(self, *, target_order_no: str, command_type: str) -> None:
        current = self.host._get_order_state(target_order_no) or {
            "production_order_no": target_order_no,
        }
        next_row = {
            "production_order_no": target_order_no,
            "promised_due_date": current.get("promised_due_date"),
            "expected_start_date": current.get("expected_start_date"),
            "expected_start_time": current.get("expected_start_time"),
            "expected_finish_time": current.get("expected_finish_time"),
            "priority_level": _normalize_priority_level(current.get("priority_level"), 5),
            "urgent_flag": 1 if _normalize_priority_level(current.get("priority_level"), 5) == 1 else 0,
            "lock_flag": int(current.get("lock_flag") or 0),
            "frozen_flag": int(current.get("frozen_flag") or 0),
            "status": current.get("status"),
            "order_status": current.get("order_status"),
            "completed_qty": current.get("completed_qty"),
            "remaining_qty": current.get("remaining_qty"),
            "progress_rate": current.get("progress_rate"),
            "production_batch_no": current.get("production_batch_no"),
        }
        normalized = str(command_type or "").strip().upper()
        if normalized == "LOCK":
            next_row["lock_flag"] = 1
        elif normalized == "UNLOCK":
            next_row["lock_flag"] = 0
        elif normalized == "PRIORITY_UP":
            next_row["priority_level"] = max(1, next_row["priority_level"] - 1)
            next_row["urgent_flag"] = 1 if next_row["priority_level"] == 1 else 0
        elif normalized == "PRIORITY_DOWN":
            next_row["priority_level"] = min(5, next_row["priority_level"] + 1)
            next_row["urgent_flag"] = 1 if next_row["priority_level"] == 1 else 0
        elif normalized == "PRIORITY":
            next_row["priority_level"] = 1
            next_row["urgent_flag"] = 1
        elif normalized == "UNPRIORITY":
            next_row["priority_level"] = 5
            next_row["urgent_flag"] = 0
        self.host._upsert_order_state(next_row)
