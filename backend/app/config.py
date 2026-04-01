from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
DEFAULT_DB_PATH = BACKEND_ROOT / "data" / "production_plan.db"


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
    erp_orders_path: str | None
    erp_order_materials_path: str | None
    erp_bom_children_path: str | None
    erp_inventory_path: str | None
    erp_supply_path: str | None


@lru_cache
def get_settings() -> Settings:
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
            os.getenv("PRODUCTION_PLAN_ERP_TIMEOUT_SECONDS", "15")
        ),
        erp_authorization=_read_env("PRODUCTION_PLAN_ERP_AUTHORIZATION"),
        erp_orders_path=_read_env("PRODUCTION_PLAN_ERP_ORDERS_PATH"),
        erp_order_materials_path=_read_env("PRODUCTION_PLAN_ERP_ORDER_MATERIALS_PATH"),
        erp_bom_children_path=_read_env("PRODUCTION_PLAN_ERP_BOM_CHILDREN_PATH"),
        erp_inventory_path=_read_env("PRODUCTION_PLAN_ERP_INVENTORY_PATH"),
        erp_supply_path=_read_env("PRODUCTION_PLAN_ERP_SUPPLY_PATH"),
    )
