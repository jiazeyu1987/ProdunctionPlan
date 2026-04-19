from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..gateway.inventory import ERPInventoryGateway
from ..gateway.masterdata import UpstreamMasterdataGateway
from ..gateway.orders import ERPOrderGateway
from ..gateway.supply import ERPSupplyGateway
from .job_dispatcher import ServiceFactory
from .line_daily_capacity_service import LineDailyCapacityService


@dataclass(frozen=True)
class LegacyAppRuntime:
    factory: ServiceFactory
    line_daily_capacity_service: LineDailyCapacityService
    masterdata_gateway: UpstreamMasterdataGateway
    order_gateway: ERPOrderGateway
    inventory_gateway: ERPInventoryGateway
    supply_gateway: ERPSupplyGateway


def build_legacy_app_runtime(connection: sqlite3.Connection) -> LegacyAppRuntime:
    return LegacyAppRuntime(
        factory=ServiceFactory(connection),
        line_daily_capacity_service=LineDailyCapacityService(connection),
        masterdata_gateway=UpstreamMasterdataGateway(),
        order_gateway=ERPOrderGateway(),
        inventory_gateway=ERPInventoryGateway(),
        supply_gateway=ERPSupplyGateway(),
    )
