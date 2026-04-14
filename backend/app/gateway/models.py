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


class ERPProductionOrderSyncRecord(BaseModel):
    production_order_no: str
    material_code: str
    material_name: str
    material_specification: str | None = None
    production_qty: float
    planned_start_date: str | None = None
    planned_end_date: str | None = None
    source_bill_no: str | None = None
    material_list_no: str | None = None
    business_status: str | None = None


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


class UpstreamProcessRoute(BaseModel):
    route_no: str
    product_code: str
    product_name_cn: str | None = None
    route_name_cn: str | None = None
    sequence_no: int
    process_code: str
    process_name_cn: str | None = None
    dependency_type: str | None = None
    capacity_per_shift: float | None = None
    required_manpower_per_group: int | None = None
    required_equipment_count: int | None = None
    enabled_flag: int | None = None


class UpstreamEquipmentProcessCapability(BaseModel):
    equipment_code: str
    process_code: str
    company_code: str | None = None
    line_code: str | None = None
    line_name: str | None = None
    workshop_code: str | None = None
    enabled_flag: int | None = None
    capacity_factor: float | None = None
    process_name_cn: str | None = None
