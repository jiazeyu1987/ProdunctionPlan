from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ERPProductionOrder(BaseModel):
    production_order_no: str
    material_code: str
    material_name: str
    material_specification: str | None = None
    production_qty: float
    status: str
    planned_start_date: str | None = None
    planned_end_date: str | None = None
    source_bill_no: str | None = None
    material_list_no: str | None = None


class ERPMaterialIssueItem(BaseModel):
    production_order_no: str
    child_material_code: str
    child_material_name: str
    spec_model: str | None = None
    issue_qty: float | None = None
    supply_type_code: str | None = None
    supply_type_name: str | None = None


class ERPBomChildItem(BaseModel):
    parent_material_code: str
    child_material_code: str
    child_material_name: str
    child_specification: str | None = None
    usage_numerator: float | None = None
    usage_denominator: float | None = None
    child_unit: str | None = None
    supply_type_code: str | None = None
    supply_type_name: str | None = None


class ERPInventorySnapshot(BaseModel):
    material_code: str
    inventory_qty: float | None = None
    inventory_status: Literal["KNOWN", "UNKNOWN"]


class ERPMaterialSupplyInfo(BaseModel):
    material_code: str
    supply_type_code: str
    supply_type_name: str
