from __future__ import annotations

from pydantic import BaseModel


class OrderSummary(BaseModel):
    production_order_no: str
    material_code: str
    material_name: str
    material_specification: str | None = None
    production_qty: int
    status: str
    material_list_no: str | None = None
    planned_start_date: str | None = None
    planned_end_date: str | None = None
    source_bill_no: str | None = None
    final_process_code: str | None = None
    final_process_name_cn: str | None = None
    final_process_completed_qty: float | None = None
    final_process_eta_date: str | None = None
