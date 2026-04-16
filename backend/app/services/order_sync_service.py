from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any

from ..config import Settings, get_settings
from ..db import fetch_all, fetch_one, transaction, utc_now
from ..errors import bad_request, server_error
from ..gateway.models import ERPProductionOrderSyncRecord
from ..gateway.orders import ERPOrderGateway
from ..repositories.orders import ProductionOrderRepository


def _normalize_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_date_text(value: object) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    if "T" in text:
        return text.split("T", 1)[0]
    if " " in text:
        return text.split(" ", 1)[0]
    return text


def _iso_at(date_text: str | None, clock_text: str) -> str | None:
    if not date_text:
        return None
    return f"{date_text}T{clock_text}+08:00"


def _to_number(value: object, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number == number else fallback


ACTIVE_ORDER_STATUSES = {"OPEN", "IN_PROGRESS", "DELAY"}
CLOSE_ORDER_STATUSES = {"CLOSED", "DONE", "COMPLETED"}


class OrderSyncService:
    def __init__(
        self,
        *,
        connection: sqlite3.Connection,
        order_repository: ProductionOrderRepository,
        order_gateway: ERPOrderGateway,
        settings: Settings | None = None,
    ) -> None:
        self.connection = connection
        self.order_repository = order_repository
        self.order_gateway = order_gateway
        self.settings = settings or get_settings()

    def sync_orders(self) -> dict[str, object]:
        items = self.order_gateway.fetch_orders()
        updated_at = utc_now()
        rows_to_store = [
            {
                "production_order_no": item["production_order_no"],
                "material_code": item["material_code"],
                "material_name": item["material_name"],
                "material_specification": item.get("material_specification"),
                "production_qty": item["production_qty"],
                "status": item["status"],
                "planned_start_date": item.get("planned_start_date"),
                "planned_end_date": item.get("planned_end_date"),
                "source_bill_no": item.get("source_bill_no"),
                "material_list_no": item.get("material_list_no"),
                "updated_at": updated_at,
            }
            for item in items
        ]

        with transaction(self.connection):
            self.order_repository.replace_all(rows_to_store)

        return {"message": f"Synchronized {len(rows_to_store)} production orders."}

    def preview_orders_from_erp_incremental_sync(self) -> dict[str, object]:
        normalized = self._load_normalized_sync_source()
        return self._build_incremental_sync_preview(normalized)

    def sync_orders_from_erp_incremental(self) -> dict[str, object]:
        normalized = self._load_normalized_sync_source()
        preview = self._build_incremental_sync_preview(normalized)
        conflict_items = preview["conflict_items"]
        if conflict_items:
            raise bad_request(
                code="ERP_SYNC_CONFLICTS_BLOCKED",
                message="ERP 增量同步存在待处理冲突，请先处理冲突订单后再执行。",
                details=preview,
            )

        updated_at = utc_now()
        incoming_by_no = normalized["incoming_by_no"]
        local_rows_by_no = preview["local_rows_by_no"]
        local_state_by_no = preview["local_state_by_no"]
        order_rows = [
            self._build_order_row(item, updated_at=updated_at)
            for item in incoming_by_no.values()
        ]
        order_state_rows = [
            self._build_incremental_order_state_row(
                item,
                current_state=local_state_by_no.get(item.production_order_no),
                updated_at=updated_at,
            )
            for item in incoming_by_no.values()
        ]
        close_order_rows = [
            self._build_closed_order_state_row(
                order_no=item["production_order_no"],
                base_row=local_rows_by_no[str(item["production_order_no"])],
                state_row=local_state_by_no.get(str(item["production_order_no"])),
                updated_at=updated_at,
            )
            for item in preview["close_items"]
        ]

        with transaction(self.connection):
            self._upsert_orders(order_rows)
            self._upsert_order_pool_state(order_state_rows + close_order_rows)

        return {
            "message": (
                "ERP 增量同步完成，"
                f"新增 {preview['summary']['new_order_count']} 条，"
                f"更新 {preview['summary']['updated_order_count']} 条，"
                f"关闭 {preview['summary']['close_order_count']} 条订单。"
            ),
            "summary": preview["summary"],
            "new_items": preview["new_items"],
            "updated_items": preview["updated_items"],
            "close_items": preview["close_items"],
            "conflict_items": preview["conflict_items"],
        }

    def sync_orders_from_erp_full_reset(self) -> dict[str, object]:
        return self.sync_orders_from_erp_incremental()

    def _load_normalized_sync_source(self) -> dict[str, Any]:
        excluded_statuses = self._normalized_excluded_statuses()
        raw_items = [
            ERPProductionOrderSyncRecord.model_validate(item)
            for item in self.order_gateway.fetch_sync_orders()
        ]
        if not raw_items:
            raise server_error(
                code="ERP_SYNC_SOURCE_EMPTY",
                message="ERP 未返回任何生产订单，已中止同步。",
            )

        kept_items: list[ERPProductionOrderSyncRecord] = []
        excluded_items: list[ERPProductionOrderSyncRecord] = []
        missing_status_order_nos: list[str] = []
        for item in raw_items:
            business_status = _normalize_text(item.business_status)
            if not business_status:
                missing_status_order_nos.append(item.production_order_no)
                continue
            normalized_item = item.model_copy(update={"business_status": business_status})
            if business_status.casefold() in excluded_statuses:
                excluded_items.append(normalized_item)
                continue
            kept_items.append(normalized_item)

        if missing_status_order_nos:
            raise server_error(
                code="ERP_SYNC_BUSINESS_STATUS_UNRECOGNIZED",
                message="ERP 生产订单存在无法识别的业务状态，已中止同步。",
                details={"order_nos": sorted(set(missing_status_order_nos))},
            )

        deduplicated_items = self._deduplicate_orders(kept_items)
        deduplicated_excluded_items = self._deduplicate_orders(excluded_items)
        incoming_by_no = {
            item.production_order_no: item
            for item in deduplicated_items
        }
        excluded_by_no = {
            item.production_order_no: item
            for item in deduplicated_excluded_items
        }
        return {
            "incoming_by_no": incoming_by_no,
            "excluded_by_no": excluded_by_no,
        }

    def _build_incremental_sync_preview(self, normalized: dict[str, Any]) -> dict[str, object]:
        incoming_by_no = normalized["incoming_by_no"]
        excluded_by_no = normalized["excluded_by_no"]
        local_rows = fetch_all(
            self.connection,
            """
            SELECT
                production_order_no,
                material_code,
                material_name,
                material_specification,
                production_qty,
                status,
                planned_start_date,
                planned_end_date,
                source_bill_no,
                material_list_no
            FROM production_orders
            """
        )
        local_rows_by_no = {
            str(row["production_order_no"]): row
            for row in local_rows
        }
        local_order_nos = sorted(local_rows_by_no)
        local_state_by_no = self._get_order_state_map(local_order_nos)

        new_items: list[dict[str, Any]] = []
        updated_items: list[dict[str, Any]] = []
        close_items: list[dict[str, Any]] = []
        conflict_items: list[dict[str, Any]] = []

        for order_no, item in sorted(incoming_by_no.items()):
            preview_row = self._build_order_row(item, updated_at="")
            local_row = local_rows_by_no.get(order_no)
            if local_row is None:
                new_items.append(
                    {
                        **preview_row,
                        "change_fields": [
                            "material_code",
                            "material_name",
                            "material_specification",
                            "production_qty",
                            "status",
                            "planned_start_date",
                            "planned_end_date",
                        ],
                    }
                )
                continue
            changed_fields = self._detect_changed_order_fields(local_row, preview_row)
            if changed_fields:
                updated_items.append(
                    {
                        "production_order_no": order_no,
                        "current": local_row,
                        "incoming": preview_row,
                        "change_fields": changed_fields,
                    }
                )

        missing_or_excluded_order_nos = (
            set(local_rows_by_no) - set(incoming_by_no)
        )
        for order_no in sorted(missing_or_excluded_order_nos):
            state_row = local_state_by_no.get(order_no) or {}
            current_status = str(
                state_row.get("order_status") or state_row.get("status") or ""
            ).strip().upper()
            if current_status in CLOSE_ORDER_STATUSES:
                continue
            blockers = self._collect_close_blockers(order_no, state_row=state_row)
            source = excluded_by_no.get(order_no)
            item = {
                "production_order_no": order_no,
                "business_status": _normalize_text(getattr(source, "business_status", None)),
                "reason": "ERP 已排除" if order_no in excluded_by_no else "ERP 未返回",
                "blockers": blockers,
            }
            if blockers:
                conflict_items.append(item)
            else:
                close_items.append(item)

        return {
            "summary": {
                "new_order_count": len(new_items),
                "updated_order_count": len(updated_items),
                "close_order_count": len(close_items),
                "conflict_order_count": len(conflict_items),
                "source_order_count": len(incoming_by_no),
                "excluded_order_count": len(excluded_by_no),
            },
            "new_items": new_items,
            "updated_items": updated_items,
            "close_items": close_items,
            "conflict_items": conflict_items,
            "local_rows_by_no": local_rows_by_no,
            "local_state_by_no": local_state_by_no,
        }

    def _detect_changed_order_fields(
        self,
        current_row: dict[str, Any],
        incoming_row: dict[str, Any],
    ) -> list[str]:
        fields = [
            "material_code",
            "material_name",
            "material_specification",
            "production_qty",
            "status",
            "planned_start_date",
            "planned_end_date",
            "source_bill_no",
            "material_list_no",
        ]
        changed_fields: list[str] = []
        for field in fields:
            current_value = current_row.get(field)
            incoming_value = incoming_row.get(field)
            if field == "production_qty":
                if abs(_to_number(current_value, 0) - _to_number(incoming_value, 0)) > 1e-9:
                    changed_fields.append(field)
            elif _normalize_text(current_value) != _normalize_text(incoming_value):
                changed_fields.append(field)
        return changed_fields

    def _collect_close_blockers(
        self,
        order_no: str,
        *,
        state_row: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        blockers: list[dict[str, Any]] = []
        report_row = fetch_one(
            self.connection,
            """
            SELECT COUNT(1) AS total
            FROM work_reports
            WHERE production_order_no = ?
            """,
            (order_no,),
        )
        task_row = fetch_one(
            self.connection,
            """
            SELECT COUNT(1) AS total
            FROM schedule_tasks
            WHERE production_order_no = ?
            """,
            (order_no,),
        )
        report_count = int(_to_number((report_row or {}).get("total"), 0))
        task_count = int(_to_number((task_row or {}).get("total"), 0))
        lock_flag = int(_to_number((state_row or {}).get("lock_flag"), 0))
        frozen_flag = int(_to_number((state_row or {}).get("frozen_flag"), 0))
        if report_count > 0:
            blockers.append({"type": "WORK_REPORTS", "count": report_count})
        if task_count > 0:
            blockers.append({"type": "SCHEDULE_TASKS", "count": task_count})
        if lock_flag == 1:
            blockers.append({"type": "LOCKED", "count": 1})
        if frozen_flag == 1:
            blockers.append({"type": "FROZEN", "count": 1})
        return blockers

    def _normalized_excluded_statuses(self) -> set[str]:
        values = {
            status.casefold()
            for status in self.settings.erp_orders_excluded_statuses
            if _normalize_text(status)
        }
        if not values:
            raise server_error(
                code="ERP_SYNC_EXCLUDED_STATUSES_MISSING",
                message="未配置 ERP 生产订单排除状态，无法执行 ERP 同步。",
            )
        return values

    def _deduplicate_orders(
        self,
        items: list[ERPProductionOrderSyncRecord],
    ) -> list[ERPProductionOrderSyncRecord]:
        grouped: dict[str, list[ERPProductionOrderSyncRecord]] = defaultdict(list)
        for item in items:
            grouped[item.production_order_no].append(item)

        conflicting_order_nos: list[str] = []
        deduplicated_items: list[ERPProductionOrderSyncRecord] = []
        for order_no, rows in grouped.items():
            if len(rows) == 1:
                deduplicated_items.append(rows[0])
                continue
            first_dump = rows[0].model_dump(mode="python")
            if any(row.model_dump(mode="python") != first_dump for row in rows[1:]):
                conflicting_order_nos.append(order_no)
                continue
            deduplicated_items.append(rows[0])

        if conflicting_order_nos:
            raise server_error(
                code="ERP_SYNC_DUPLICATE_ORDER_CONFLICT",
                message="ERP 返回了重复且内容冲突的生产订单，已中止同步。",
                details={"order_nos": sorted(conflicting_order_nos)},
            )

        deduplicated_items.sort(key=lambda item: item.production_order_no)
        return deduplicated_items

    def _upsert_orders(self, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        self.connection.executemany(
            """
            INSERT INTO production_orders (
                production_order_no,
                material_code,
                material_name,
                material_specification,
                production_qty,
                status,
                planned_start_date,
                planned_end_date,
                source_bill_no,
                material_list_no,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(production_order_no) DO UPDATE SET
                material_code = excluded.material_code,
                material_name = excluded.material_name,
                material_specification = excluded.material_specification,
                production_qty = excluded.production_qty,
                status = excluded.status,
                planned_start_date = excluded.planned_start_date,
                planned_end_date = excluded.planned_end_date,
                source_bill_no = excluded.source_bill_no,
                material_list_no = excluded.material_list_no,
                updated_at = excluded.updated_at
            """,
            [
                (
                    row["production_order_no"],
                    row["material_code"],
                    row["material_name"],
                    row.get("material_specification"),
                    row["production_qty"],
                    row["status"],
                    row.get("planned_start_date"),
                    row.get("planned_end_date"),
                    row.get("source_bill_no"),
                    row.get("material_list_no"),
                    row["updated_at"],
                )
                for row in rows
            ],
        )

    def _upsert_order_pool_state(self, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        self.connection.executemany(
            """
            INSERT INTO order_pool_state (
                production_order_no,
                promised_due_date,
                expected_start_date,
                expected_start_time,
                expected_finish_time,
                priority_level,
                urgent_flag,
                lock_flag,
                frozen_flag,
                status,
                order_status,
                completed_qty,
                remaining_qty,
                progress_rate,
                production_batch_no,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(production_order_no) DO UPDATE SET
                promised_due_date = excluded.promised_due_date,
                expected_start_date = excluded.expected_start_date,
                expected_start_time = excluded.expected_start_time,
                expected_finish_time = excluded.expected_finish_time,
                priority_level = excluded.priority_level,
                urgent_flag = excluded.urgent_flag,
                lock_flag = excluded.lock_flag,
                frozen_flag = excluded.frozen_flag,
                status = excluded.status,
                order_status = excluded.order_status,
                completed_qty = excluded.completed_qty,
                remaining_qty = excluded.remaining_qty,
                progress_rate = excluded.progress_rate,
                production_batch_no = excluded.production_batch_no,
                updated_at = excluded.updated_at
            """,
            [
                (
                    row["production_order_no"],
                    row.get("promised_due_date"),
                    row.get("expected_start_date"),
                    row.get("expected_start_time"),
                    row.get("expected_finish_time"),
                    row["priority_level"],
                    row["urgent_flag"],
                    row["lock_flag"],
                    row["frozen_flag"],
                    row["status"],
                    row["order_status"],
                    row["completed_qty"],
                    row["remaining_qty"],
                    row["progress_rate"],
                    row.get("production_batch_no"),
                    row["updated_at"],
                )
                for row in rows
            ],
        )

    def _get_order_state_map(self, order_nos: list[str]) -> dict[str, dict[str, Any]]:
        if not order_nos:
            return {}
        placeholders = ",".join("?" for _ in order_nos)
        rows = fetch_all(
            self.connection,
            f"""
            SELECT
                production_order_no,
                promised_due_date,
                expected_start_date,
                expected_start_time,
                expected_finish_time,
                priority_level,
                urgent_flag,
                lock_flag,
                frozen_flag,
                status,
                order_status,
                completed_qty,
                remaining_qty,
                progress_rate,
                production_batch_no
            FROM order_pool_state
            WHERE production_order_no IN ({placeholders})
            """,
            tuple(order_nos),
        )
        return {str(row["production_order_no"]): row for row in rows}

    def _build_order_row(
        self,
        item: ERPProductionOrderSyncRecord,
        *,
        updated_at: str,
    ) -> dict[str, object]:
        business_status = _normalize_text(item.business_status)
        if not business_status:
            raise server_error(
                code="ERP_SYNC_BUSINESS_STATUS_UNRECOGNIZED",
                message="ERP 生产订单存在无法识别的业务状态，已中止同步。",
                details={"order_nos": [item.production_order_no]},
            )
        return {
            "production_order_no": item.production_order_no,
            "material_code": item.material_code,
            "material_name": item.material_name,
            "material_specification": item.material_specification,
            "production_qty": float(item.production_qty),
            "status": business_status,
            "planned_start_date": _normalize_date_text(item.planned_start_date),
            "planned_end_date": _normalize_date_text(item.planned_end_date),
            "source_bill_no": _normalize_text(item.source_bill_no),
            "material_list_no": _normalize_text(item.material_list_no),
            "updated_at": updated_at,
        }

    def _build_incremental_order_state_row(
        self,
        item: ERPProductionOrderSyncRecord,
        *,
        current_state: dict[str, Any] | None,
        updated_at: str,
    ) -> dict[str, object]:
        planned_start_date = _normalize_date_text(item.planned_start_date)
        planned_end_date = _normalize_date_text(item.planned_end_date)
        current_state = current_state or {}
        promised_due_date = _normalize_date_text(
            current_state.get("promised_due_date")
        ) or planned_end_date or planned_start_date
        expected_start_date = _normalize_date_text(
            current_state.get("expected_start_date")
        ) or planned_start_date
        expected_start_time = str(current_state.get("expected_start_time") or "").strip() or _iso_at(
            expected_start_date,
            "08:00:00",
        )
        expected_finish_time = str(current_state.get("expected_finish_time") or "").strip() or _iso_at(
            promised_due_date,
            "18:00:00",
        )
        priority_level = int(_to_number(current_state.get("priority_level"), 5))
        source_bill_no = _normalize_text(item.source_bill_no)
        current_status = str(
            current_state.get("order_status") or current_state.get("status") or ""
        ).strip().upper()
        normalized_status = current_status if current_status in ACTIVE_ORDER_STATUSES else "OPEN"
        production_qty = float(item.production_qty)
        completed_qty = _to_number(current_state.get("completed_qty"), 0)
        remaining_qty = current_state.get("remaining_qty")
        if remaining_qty is None:
            remaining_qty = max(0.0, production_qty - completed_qty)
        progress_rate = current_state.get("progress_rate")
        if progress_rate is None:
            progress_rate = (completed_qty / production_qty * 100) if production_qty > 0 else 0
        return {
            "production_order_no": item.production_order_no,
            "promised_due_date": promised_due_date,
            "expected_start_date": expected_start_date,
            "expected_start_time": expected_start_time,
            "expected_finish_time": expected_finish_time,
            "priority_level": max(1, min(5, priority_level)),
            "urgent_flag": 1 if priority_level <= 1 else 0,
            "lock_flag": int(_to_number(current_state.get("lock_flag"), 0)),
            "frozen_flag": int(_to_number(current_state.get("frozen_flag"), 0)),
            "status": normalized_status,
            "order_status": normalized_status,
            "completed_qty": completed_qty,
            "remaining_qty": max(0.0, _to_number(remaining_qty, 0)),
            "progress_rate": max(0.0, _to_number(progress_rate, 0)),
            "production_batch_no": str(current_state.get("production_batch_no") or "").strip()
            or (f"{source_bill_no}-B1" if source_bill_no else None),
            "updated_at": updated_at,
        }

    def _build_closed_order_state_row(
        self,
        *,
        order_no: str,
        base_row: dict[str, Any],
        state_row: dict[str, Any] | None,
        updated_at: str,
    ) -> dict[str, object]:
        state_row = state_row or {}
        promised_due_date = _normalize_date_text(
            state_row.get("promised_due_date") or base_row.get("planned_end_date")
        )
        expected_start_date = _normalize_date_text(
            state_row.get("expected_start_date") or base_row.get("planned_start_date")
        )
        return {
            "production_order_no": order_no,
            "promised_due_date": promised_due_date,
            "expected_start_date": expected_start_date,
            "expected_start_time": str(state_row.get("expected_start_time") or "").strip()
            or _iso_at(expected_start_date, "08:00:00"),
            "expected_finish_time": str(state_row.get("expected_finish_time") or "").strip()
            or _iso_at(promised_due_date, "18:00:00"),
            "priority_level": max(1, min(5, int(_to_number(state_row.get("priority_level"), 5)))),
            "urgent_flag": int(_to_number(state_row.get("urgent_flag"), 0)),
            "lock_flag": 0,
            "frozen_flag": 0,
            "status": "CLOSED",
            "order_status": "CLOSED",
            "completed_qty": _to_number(state_row.get("completed_qty"), 0),
            "remaining_qty": _to_number(state_row.get("remaining_qty"), 0),
            "progress_rate": _to_number(state_row.get("progress_rate"), 0),
            "production_batch_no": str(state_row.get("production_batch_no") or "").strip() or None,
            "updated_at": updated_at,
        }
