from __future__ import annotations

from pydantic import BaseModel


class MaterialRow(BaseModel):
    row_type: str
    production_order_no: str | None = None
    parent_material_code: str | None = None
    child_material_code: str
    child_material_name: str
    spec_model: str | None = None
    issue_qty: float | None = None
    usage_numerator: float | None = None
    usage_denominator: float | None = None
    child_unit: str | None = None
    supply_type_code: str
    supply_type_name: str
    inventory_qty: float | None = None
    inventory_status: str
    expandable: bool


class WorkReport(BaseModel):
    report_id: str
    production_order_no: str
    process_name: str
    workshop_name: str
    line_name: str
    report_qty: float
    report_time: str
    operator_name: str


class CapacityBinding(BaseModel):
    process_code: str
    process_name: str
    workshop_code: str
    workshop_name: str
    line_code: str
    line_name: str
    capacity_qty: float
