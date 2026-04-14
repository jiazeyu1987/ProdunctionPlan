from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any

from ..config import Settings, get_settings
from ..db import fetch_one, transaction, utc_now
from ..errors import server_error
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

    def sync_orders_from_erp_full_reset(self) -> dict[str, object]:
        excluded_statuses = self._normalized_excluded_statuses()
        raw_items = [
            ERPProductionOrderSyncRecord.model_validate(item)
            for item in self.order_gateway.fetch_sync_orders()
        ]
        if not raw_items:
            raise server_error(
                code="ERP_SYNC_SOURCE_EMPTY",
                message="ERP 未返回任何生产订单，已中止 ERP 全量同步。",
            )

        kept_items: list[ERPProductionOrderSyncRecord] = []
        filtered_out_count = 0
        missing_status_order_nos: list[str] = []
        for item in raw_items:
            business_status = _normalize_text(item.business_status)
            if not business_status:
                missing_status_order_nos.append(item.production_order_no)
                continue
            if business_status.casefold() in excluded_statuses:
                filtered_out_count += 1
                continue
            kept_items.append(item.model_copy(update={"business_status": business_status}))

        if missing_status_order_nos:
            raise server_error(
                code="ERP_SYNC_BUSINESS_STATUS_UNRECOGNIZED",
                message="ERP 生产订单存在无法识别的业务状态，已中止 ERP 全量同步。",
                details={"order_nos": sorted(set(missing_status_order_nos))},
            )

        deduplicated_items = self._deduplicate_orders(kept_items)
        updated_at = utc_now()
        order_rows = [
            self._build_order_row(item, updated_at=updated_at) for item in deduplicated_items
        ]
        order_state_rows = [
            self._build_order_state_row(item, updated_at=updated_at)
            for item in deduplicated_items
        ]

        with transaction(self.connection):
            deleted_before_import_count = self._count_existing_orders()
            self.connection.execute("DELETE FROM production_orders")
            self._insert_orders(order_rows)
            self._insert_order_pool_state(order_state_rows)

        order_nos = [row["production_order_no"] for row in order_rows]
        return {
            "message": (
                "ERP 全量同步完成，"
                f"已删除 {deleted_before_import_count} 条旧生产订单，"
                f"导入 {len(order_rows)} 条生产订单，"
                f"过滤 {filtered_out_count} 条已结算/结案/完工订单。"
            ),
            "imported_count": len(order_rows),
            "filtered_out_count": filtered_out_count,
            "deleted_before_import_count": deleted_before_import_count,
            "order_nos": order_nos,
        }

    def _normalized_excluded_statuses(self) -> set[str]:
        values = {
            status.casefold()
            for status in self.settings.erp_orders_excluded_statuses
            if _normalize_text(status)
        }
        if not values:
            raise server_error(
                code="ERP_SYNC_EXCLUDED_STATUSES_MISSING",
                message="未配置 ERP 生产订单排除状态，无法执行 ERP 全量同步。",
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
                message="ERP 返回了重复且内容冲突的生产订单，已中止 ERP 全量同步。",
                details={"order_nos": sorted(conflicting_order_nos)},
            )

        deduplicated_items.sort(key=lambda item: item.production_order_no)
        return deduplicated_items

    def _count_existing_orders(self) -> int:
        row = fetch_one(
            self.connection,
            "SELECT COUNT(1) AS total FROM production_orders",
        )
        return int((row or {}).get("total") or 0)

    def _insert_orders(self, rows: list[dict[str, object]]) -> None:
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

    def _insert_order_pool_state(self, rows: list[dict[str, object]]) -> None:
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
                message="ERP 生产订单存在无法识别的业务状态，已中止 ERP 全量同步。",
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

    def _build_order_state_row(
        self,
        item: ERPProductionOrderSyncRecord,
        *,
        updated_at: str,
    ) -> dict[str, object]:
        planned_start_date = _normalize_date_text(item.planned_start_date)
        planned_end_date = _normalize_date_text(item.planned_end_date)
        promised_due_date = planned_end_date or planned_start_date
        source_bill_no = _normalize_text(item.source_bill_no)
        production_qty = float(item.production_qty)
        return {
            "production_order_no": item.production_order_no,
            "promised_due_date": promised_due_date,
            "expected_start_date": planned_start_date,
            "expected_start_time": _iso_at(planned_start_date, "08:00:00"),
            "expected_finish_time": _iso_at(promised_due_date, "18:00:00"),
            "priority_level": 5,
            "urgent_flag": 0,
            "lock_flag": 0,
            "frozen_flag": 0,
            "status": "OPEN",
            "order_status": "OPEN",
            "completed_qty": 0.0,
            "remaining_qty": production_qty,
            "progress_rate": 0.0,
            "production_batch_no": f"{source_bill_no}-B1" if source_bill_no else None,
            "updated_at": updated_at,
        }
