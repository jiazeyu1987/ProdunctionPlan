from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
DEFAULT_DB_PATH = BACKEND_ROOT / "data" / "production_plan.db"
DEFAULT_ENV_PATH = BACKEND_ROOT / ".env"


def _load_env_file() -> None:
    if not DEFAULT_ENV_PATH.exists():
        return
    for raw_line in DEFAULT_ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


def _read_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@dataclass(frozen=True)
class Settings:
    api_title: str
    api_version: str
    database_path: Path
    worker_poll_interval_seconds: float
    erp_base_url: str | None
    erp_timeout_seconds: float
    erp_authorization: str | None
    erp_orders_source: str
    erp_orders_method: str
    erp_orders_path: str | None
    erp_order_materials_source: str
    erp_bom_children_source: str
    erp_inventory_source: str
    erp_supply_source: str
    erp_k3cloud_base_url: str | None
    erp_k3cloud_acct_id: str | None
    erp_k3cloud_username: str | None
    erp_k3cloud_password: str | None
    erp_k3cloud_lcid: int
    erp_k3cloud_verify_ssl: bool
    erp_k3cloud_orders_form_id: str | None
    erp_k3cloud_orders_field_keys: str | None
    erp_k3cloud_orders_order_string: str | None
    erp_k3cloud_orders_limit: int
    erp_k3cloud_orders_material_field: str | None
    erp_k3cloud_orders_bill_no_field: str | None
    erp_k3cloud_orders_name_field: str | None
    erp_k3cloud_orders_spec_field: str | None
    erp_k3cloud_orders_qty_field: str | None
    erp_k3cloud_orders_status_field: str | None
    erp_k3cloud_orders_start_date_field: str | None
    erp_k3cloud_orders_end_date_field: str | None
    erp_k3cloud_orders_source_bill_field: str | None
    erp_k3cloud_orders_material_list_field: str | None
    erp_order_materials_method: str
    erp_order_materials_path: str | None
    erp_bom_children_method: str
    erp_bom_children_path: str | None
    erp_inventory_method: str
    erp_inventory_path: str | None
    erp_supply_method: str
    erp_supply_path: str | None
    masterdata_process_routes_method: str
    masterdata_process_routes_path: str | None
    masterdata_equipment_capabilities_method: str
    masterdata_equipment_capabilities_path: str | None


@lru_cache
def get_settings() -> Settings:
    _load_env_file()
    raw_path = os.getenv("PRODUCTION_PLAN_DB_PATH", str(DEFAULT_DB_PATH))
    database_path = Path(raw_path)
    if not database_path.is_absolute():
        database_path = (PROJECT_ROOT / database_path).resolve()

    return Settings(
        api_title="ProductionPlan API",
        api_version="0.2.0",
        database_path=database_path,
        worker_poll_interval_seconds=float(
            os.getenv("PRODUCTION_PLAN_WORKER_POLL_SECONDS", "1.0")
        ),
        erp_base_url=_read_env("PRODUCTION_PLAN_ERP_BASE_URL"),
        erp_timeout_seconds=float(
            os.getenv("PRODUCTION_PLAN_ERP_TIMEOUT_SECONDS", "30")
        ),
        erp_authorization=_read_env("PRODUCTION_PLAN_ERP_AUTHORIZATION"),
        erp_orders_source=str(
            os.getenv("PRODUCTION_PLAN_ERP_ORDERS_SOURCE", "HTTP_LIST")
        ).strip().upper()
        or "HTTP_LIST",
        erp_orders_method=str(
            os.getenv("PRODUCTION_PLAN_ERP_ORDERS_METHOD", "POST")
        ).strip().upper()
        or "POST",
        erp_orders_path=_read_env("PRODUCTION_PLAN_ERP_ORDERS_PATH"),
        erp_order_materials_source=str(
            os.getenv("PRODUCTION_PLAN_ERP_ORDER_MATERIALS_SOURCE", "HTTP")
        ).strip().upper()
        or "HTTP",
        erp_bom_children_source=str(
            os.getenv("PRODUCTION_PLAN_ERP_BOM_CHILDREN_SOURCE", "HTTP")
        ).strip().upper()
        or "HTTP",
        erp_inventory_source=str(
            os.getenv("PRODUCTION_PLAN_ERP_INVENTORY_SOURCE", "HTTP")
        ).strip().upper()
        or "HTTP",
        erp_supply_source=str(
            os.getenv("PRODUCTION_PLAN_ERP_SUPPLY_SOURCE", "HTTP")
        ).strip().upper()
        or "HTTP",
        erp_k3cloud_base_url=_read_env("PRODUCTION_PLAN_ERP_K3CLOUD_BASE_URL"),
        erp_k3cloud_acct_id=_read_env("PRODUCTION_PLAN_ERP_K3CLOUD_ACCT_ID"),
        erp_k3cloud_username=_read_env("PRODUCTION_PLAN_ERP_K3CLOUD_USERNAME"),
        erp_k3cloud_password=_read_env("PRODUCTION_PLAN_ERP_K3CLOUD_PASSWORD"),
        erp_k3cloud_lcid=int(
            os.getenv("PRODUCTION_PLAN_ERP_K3CLOUD_LCID", "2052")
        ),
        erp_k3cloud_verify_ssl=str(
            os.getenv("PRODUCTION_PLAN_ERP_K3CLOUD_VERIFY_SSL", "false")
        ).strip().lower()
        in {"1", "true", "yes", "on"},
        erp_k3cloud_orders_form_id=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_FORM_ID"
        ),
        erp_k3cloud_orders_field_keys=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_FIELD_KEYS"
        ),
        erp_k3cloud_orders_order_string=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_ORDER_STRING"
        ),
        erp_k3cloud_orders_limit=int(
            os.getenv("PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_LIMIT", "200")
        ),
        erp_k3cloud_orders_material_field=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_MATERIAL_FIELD"
        ),
        erp_k3cloud_orders_bill_no_field=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_BILL_NO_FIELD"
        ),
        erp_k3cloud_orders_name_field=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_NAME_FIELD"
        ),
        erp_k3cloud_orders_spec_field=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_SPEC_FIELD"
        ),
        erp_k3cloud_orders_qty_field=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_QTY_FIELD"
        ),
        erp_k3cloud_orders_status_field=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_STATUS_FIELD"
        ),
        erp_k3cloud_orders_start_date_field=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_START_DATE_FIELD"
        ),
        erp_k3cloud_orders_end_date_field=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_END_DATE_FIELD"
        ),
        erp_k3cloud_orders_source_bill_field=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_SOURCE_BILL_FIELD"
        ),
        erp_k3cloud_orders_material_list_field=_read_env(
            "PRODUCTION_PLAN_ERP_K3CLOUD_ORDERS_MATERIAL_LIST_FIELD"
        ),
        erp_order_materials_method=str(
            os.getenv("PRODUCTION_PLAN_ERP_ORDER_MATERIALS_METHOD", "POST")
        ).strip().upper()
        or "POST",
        erp_order_materials_path=_read_env("PRODUCTION_PLAN_ERP_ORDER_MATERIALS_PATH"),
        erp_bom_children_method=str(
            os.getenv("PRODUCTION_PLAN_ERP_BOM_CHILDREN_METHOD", "POST")
        ).strip().upper()
        or "POST",
        erp_bom_children_path=_read_env("PRODUCTION_PLAN_ERP_BOM_CHILDREN_PATH"),
        erp_inventory_method=str(
            os.getenv("PRODUCTION_PLAN_ERP_INVENTORY_METHOD", "POST")
        ).strip().upper()
        or "POST",
        erp_inventory_path=_read_env("PRODUCTION_PLAN_ERP_INVENTORY_PATH"),
        erp_supply_method=str(
            os.getenv("PRODUCTION_PLAN_ERP_SUPPLY_METHOD", "POST")
        ).strip().upper()
        or "POST",
        erp_supply_path=_read_env("PRODUCTION_PLAN_ERP_SUPPLY_PATH"),
        masterdata_process_routes_method=str(
            os.getenv("PRODUCTION_PLAN_MASTERDATA_PROCESS_ROUTES_METHOD", "GET")
        ).strip().upper()
        or "GET",
        masterdata_process_routes_path=_read_env(
            "PRODUCTION_PLAN_MASTERDATA_PROCESS_ROUTES_PATH"
        ),
        masterdata_equipment_capabilities_method=str(
            os.getenv(
                "PRODUCTION_PLAN_MASTERDATA_EQUIPMENT_CAPABILITIES_METHOD",
                "GET",
            )
        ).strip().upper()
        or "GET",
        masterdata_equipment_capabilities_path=_read_env(
            "PRODUCTION_PLAN_MASTERDATA_EQUIPMENT_CAPABILITIES_PATH"
        ),
    )
