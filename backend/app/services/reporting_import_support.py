from __future__ import annotations

import binascii
import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from openpyxl.utils.datetime import from_excel


REPORTING_IMPORT_LOCAL_TIMEZONE = timezone(timedelta(hours=8))

WORK_REPORT_COLUMNS = (
    "report_id",
    "production_order_no",
    "process_code",
    "process_name",
    "company_code",
    "workshop_code",
    "workshop_name",
    "line_code",
    "line_name",
    "report_qty",
    "report_time",
    "operator_code",
    "operator_name",
    "section_leader_name",
    "dispatch_no",
    "product_code",
    "product_name",
    "product_specification",
    "resource_group_name",
    "resource_name",
    "department_name",
    "source_process_code",
    "source_process_name",
    "mold_code",
    "support_count",
    "weight_kg",
    "cavity_count",
    "total_cycle_time",
    "production_quota",
    "work_duration",
    "clamp_or_assembly_weight",
    "unit_weight",
    "source_sheet_name",
    "source_row_no",
    "source_file_name",
    "daily_capacity_compare_audit_id",
    "daily_capacity_compare_qty",
    "daily_capacity_compare_selected_at",
    "updated_at",
)

REPORTING_IMPORT_REQUIRED_HEADER_MAP = {
    "鎶ュ伐鏃ユ湡": "report_datetime",
    "报工日期": "report_datetime",
    "报工人编码": "operator_code",
    "鎶ュ伐浜虹紪鐮?": "operator_code",
    "报工人名称": "operator_name",
    "鎶ュ伐浜哄悕绉?": "operator_name",
    "工段长": "section_leader_name",
    "宸ユ闀?": "section_leader_name",
    "生产订单号": "production_order_no",
    "鐢熶骇璁㈠崟鍙?": "production_order_no",
    "生产资源组": "resource_group_name",
    "鐢熶骇璧勬簮缁?": "resource_group_name",
    "鐢熶骇璧勬簮": "resource_name",
    "生产资源": "resource_name",
    "娲惧伐鍗曞彿": "dispatch_no",
    "派工单号": "dispatch_no",
    "浜у搧缂栫爜": "product_code",
    "产品编码": "product_code",
    "浜у搧鍚嶇О": "product_name",
    "产品名称": "product_name",
    "瑙勬牸": "product_specification",
    "宸ュ簭缂栫爜": "source_process_code",
    "工序编码": "source_process_code",
    "宸ュ簭鍚嶇О": "source_process_name",
    "工序名称": "source_process_name",
    "所属部门": "department_name",
    "鎵€灞為儴闂?": "department_name",
    "报工数量": "report_qty",
    "鎶ュ伐鏁伴噺": "report_qty",
}

REPORTING_IMPORT_OPTIONAL_HEADER_MAP = {
    "妯″叿缂栫爜": "mold_code",
    "模具编码": "mold_code",
    "鏀暟": "support_count",
    "支数": "support_count",
    "公斤数": "weight_kg",
    "鍏枻鏁?": "weight_kg",
    "实穴数": "cavity_count",
    "实腔数": "cavity_count",
    "瀹炶厰鏁?": "cavity_count",
    "鍏ㄧ▼鏃堕棿": "total_cycle_time",
    "全程时间": "total_cycle_time",
    "鐢熶骇瀹氶": "production_quota",
    "生产定额": "production_quota",
    "宸ヤ綔鏃堕暱": "work_duration",
    "工作时长": "work_duration",
    "注塑合模/组装公斤数": "clamp_or_assembly_weight",
    "娉ㄥ鍚堟ā/缁勮鍏枻鏁?": "clamp_or_assembly_weight",
    "注塑个数/组装个重量": "unit_weight",
    "注塑个数/组装个重": "unit_weight",
    "娉ㄥ涓暟/缁勮涓噸": "unit_weight",
}


def normalize_sha256_text(value: object) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    text = raw[7:] if raw.startswith("sha256:") else raw
    if len(text) != 64:
        return None
    try:
        binascii.unhexlify(text)
    except binascii.Error:
        return None
    return text


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def parse_optional_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number == number else None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def parse_required_positive_number(value: object) -> float | None:
    number = parse_optional_number(value)
    if number is None or number <= 0:
        return None
    return number


def parse_report_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, (int, float)):
        try:
            parsed_excel = from_excel(value)
        except Exception:
            parsed_excel = None
        if isinstance(parsed_excel, datetime):
            return parsed_excel
        if isinstance(parsed_excel, date):
            return datetime.combine(parsed_excel, datetime.min.time())
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def to_utc_iso_text(value: datetime) -> str:
    parsed = value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=REPORTING_IMPORT_LOCAL_TIMEZONE)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
