from __future__ import annotations

from typing import Any


def _localized_text(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("Value") or item.get("Name") or "").strip()
                if text:
                    return text
    return None


def material_number(material: dict[str, Any] | None) -> str | None:
    if not isinstance(material, dict):
        return None
    text = str(material.get("Number") or "").strip()
    return text or None


def material_name(material: dict[str, Any] | None) -> str | None:
    if not isinstance(material, dict):
        return None
    return _localized_text(material.get("Name"))


def material_spec(material: dict[str, Any] | None) -> str | None:
    if not isinstance(material, dict):
        return None
    return _localized_text(material.get("Specification"))


def material_unit_number(unit: dict[str, Any] | None) -> str | None:
    if not isinstance(unit, dict):
        return None
    text = str(unit.get("Number") or "").strip()
    return text or None


def material_supply_type(material: dict[str, Any] | None) -> tuple[str, str]:
    if not isinstance(material, dict):
        return ("PURCHASED", "外购")
    material_base = material.get("MaterialBase")
    first_base = material_base[0] if isinstance(material_base, list) and material_base else {}
    is_produce = bool(first_base.get("IsProduce"))
    if is_produce:
        return ("SELF_MADE", "自制")
    return ("PURCHASED", "外购")
