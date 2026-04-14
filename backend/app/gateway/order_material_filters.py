from __future__ import annotations

from typing import Any

ALLOWED_ORDER_MATERIAL_CODE_PREFIXES = ("AW", "YXN", "YTN")


def normalize_order_material_code(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.upper()


def is_allowed_order_material_code(value: Any) -> bool:
    normalized = normalize_order_material_code(value)
    return bool(
        normalized
        and normalized.startswith(ALLOWED_ORDER_MATERIAL_CODE_PREFIXES)
    )
