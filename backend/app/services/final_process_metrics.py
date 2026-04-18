from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import sqlite3
from typing import Any

from ..db import fetch_all, fetch_one
from ..errors import server_error


def _to_number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _normalize_order_no(value: object) -> str:
    return str(value or "").strip()


def _normalize_product_code(value: object) -> str:
    return str(value or "").strip().upper()


def _normalize_process_code(value: object) -> str:
    return str(value or "").strip().upper()


def _normalize_date_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _normalize_shift_code(value: object) -> str:
    normalized = str(value or "").strip().upper()
    if normalized == "N":
        return "NIGHT"
    if normalized == "D":
        return "DAY"
    return "NIGHT" if normalized == "NIGHT" else "DAY"


def _pick_reference_schedule_version_no(connection: sqlite3.Connection) -> str | None:
    latest = fetch_one(
        connection,
        """
        SELECT version_no
        FROM schedule_versions
        ORDER BY
            CASE
                WHEN UPPER(TRIM(COALESCE(status, ''))) = 'CURRENT' THEN 0
                ELSE 1
            END ASC,
            COALESCE(NULLIF(TRIM(COALESCE(published_at, '')), ''), created_at) DESC,
            created_at DESC,
            version_no DESC
        LIMIT 1
        """,
    )
    if latest is None:
        return None
    version_no = str(latest.get("version_no") or "").strip()
    return version_no or None


def _load_final_process_by_product(
    connection: sqlite3.Connection,
    product_codes: set[str],
) -> dict[str, dict[str, Any]]:
    if not product_codes:
        return {}
    placeholders = ",".join("?" for _ in product_codes)
    rows = fetch_all(
        connection,
        f"""
        SELECT
            product_code,
            sequence_no,
            process_code,
            process_name_cn,
            COALESCE(is_final_process, 0) AS is_final_process
        FROM masterdata_process_routes
        WHERE product_code IN ({placeholders})
        ORDER BY product_code ASC, sequence_no ASC
        """,
        tuple(sorted(product_codes)),
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        product_code = _normalize_product_code(row.get("product_code"))
        process_code = _normalize_process_code(row.get("process_code"))
        sequence_no = int(_to_number(row.get("sequence_no"), 0))
        if not product_code or not process_code or sequence_no <= 0:
            continue
        grouped[product_code].append(
            {
                "product_code": product_code,
                "sequence_no": sequence_no,
                "process_code": process_code,
                "process_name_cn": str(row.get("process_name_cn") or process_code).strip()
                or process_code,
                "is_final_process": 1 if int(_to_number(row.get("is_final_process"), 0)) == 1 else 0,
            }
        )

    final_by_product: dict[str, dict[str, Any]] = {}
    for product_code, route_rows in grouped.items():
        ordered_rows = sorted(route_rows, key=lambda item: int(item["sequence_no"]))
        marked_rows = [
            row for row in ordered_rows if int(row.get("is_final_process") or 0) == 1
        ]
        if len(marked_rows) > 1:
            raise server_error(
                code="ROUTE_FINAL_PROCESS_DUPLICATED",
                message="Route has more than one final process step.",
                details={"product_code": product_code},
            )
        target_row = marked_rows[0] if marked_rows else ordered_rows[-1]
        final_by_product[product_code] = {
            "process_code": str(target_row["process_code"]),
            "process_name_cn": str(target_row["process_name_cn"]),
        }
    return final_by_product


def _load_report_qty_by_order_process(
    connection: sqlite3.Connection,
    order_nos: list[str],
) -> dict[tuple[str, str], float]:
    if not order_nos:
        return {}
    placeholders = ",".join("?" for _ in order_nos)
    rows = fetch_all(
        connection,
        f"""
        SELECT
            production_order_no,
            process_code,
            SUM(report_qty) AS completed_qty
        FROM work_reports
        WHERE production_order_no IN ({placeholders})
        GROUP BY production_order_no, process_code
        """,
        tuple(order_nos),
    )
    out: dict[tuple[str, str], float] = {}
    for row in rows:
        order_no = _normalize_order_no(row.get("production_order_no"))
        process_code = _normalize_process_code(row.get("process_code"))
        if not order_no or not process_code:
            continue
        out[(order_no, process_code)] = _to_number(row.get("completed_qty"), 0)
    return out


def _load_eta_date_by_order_process(
    connection: sqlite3.Connection,
    *,
    version_no: str | None,
    order_nos: list[str],
    target_pairs: set[tuple[str, str]],
) -> dict[tuple[str, str], str]:
    if not version_no or not order_nos or not target_pairs:
        return {}
    placeholders = ",".join("?" for _ in order_nos)
    rows = fetch_all(
        connection,
        f"""
        SELECT
            production_order_no,
            process_code,
            calendar_date,
            shift_code
        FROM schedule_tasks
        WHERE version_no = ?
          AND production_order_no IN ({placeholders})
        ORDER BY production_order_no ASC, task_no ASC
        """,
        (version_no, *order_nos),
    )
    completion_date_by_pair: dict[tuple[str, str], date] = {}
    for row in rows:
        order_no = _normalize_order_no(row.get("production_order_no"))
        process_code = _normalize_process_code(row.get("process_code"))
        pair = (order_no, process_code)
        if pair not in target_pairs:
            continue
        calendar_date = _normalize_date_text(row.get("calendar_date"))
        if not calendar_date:
            continue
        completion_date = date.fromisoformat(calendar_date)
        if _normalize_shift_code(row.get("shift_code")) == "NIGHT":
            completion_date = completion_date + timedelta(days=1)
        previous = completion_date_by_pair.get(pair)
        if previous is None or completion_date > previous:
            completion_date_by_pair[pair] = completion_date

    return {
        pair: completion_date.isoformat()
        for pair, completion_date in completion_date_by_pair.items()
    }


def build_order_final_process_metrics(
    connection: sqlite3.Connection,
    order_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    order_product_by_no: dict[str, str] = {}
    for row in order_rows:
        order_no = _normalize_order_no(
            row.get("production_order_no") or row.get("order_no")
        )
        if not order_no:
            continue
        product_code = _normalize_product_code(
            row.get("material_code") or row.get("product_code")
        )
        order_product_by_no[order_no] = product_code

    if not order_product_by_no:
        return {}

    order_nos = sorted(order_product_by_no)
    product_codes = {
        product_code
        for product_code in order_product_by_no.values()
        if product_code
    }
    final_process_by_product = _load_final_process_by_product(connection, product_codes)

    target_pairs: set[tuple[str, str]] = set()
    final_process_by_order: dict[str, dict[str, Any]] = {}
    for order_no, product_code in order_product_by_no.items():
        process_meta = final_process_by_product.get(product_code)
        if process_meta is None:
            continue
        process_code = _normalize_process_code(process_meta.get("process_code"))
        if not process_code:
            continue
        final_process_by_order[order_no] = {
            "process_code": process_code,
            "process_name_cn": str(
                process_meta.get("process_name_cn") or process_code
            ).strip()
            or process_code,
        }
        target_pairs.add((order_no, process_code))

    completed_qty_by_pair = _load_report_qty_by_order_process(connection, order_nos)
    reference_version_no = _pick_reference_schedule_version_no(connection)
    eta_date_by_pair = _load_eta_date_by_order_process(
        connection,
        version_no=reference_version_no,
        order_nos=order_nos,
        target_pairs=target_pairs,
    )

    out: dict[str, dict[str, Any]] = {}
    for order_no in order_nos:
        process_meta = final_process_by_order.get(order_no)
        process_code = (
            _normalize_process_code(process_meta.get("process_code"))
            if process_meta
            else None
        )
        process_name_cn = (
            str(process_meta.get("process_name_cn") or process_code or "").strip() or None
            if process_meta
            else None
        )
        completed_qty = (
            _to_number(completed_qty_by_pair.get((order_no, process_code), 0), 0)
            if process_code
            else 0.0
        )
        eta_date = (
            eta_date_by_pair.get((order_no, process_code))
            if process_code
            else None
        )
        out[order_no] = {
            "final_process_code": process_code,
            "final_process_name_cn": process_name_cn,
            "final_process_completed_qty": completed_qty,
            "final_process_eta_date": eta_date,
        }
    return out
