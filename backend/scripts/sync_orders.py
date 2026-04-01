from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.db import managed_connection
from backend.app.gateway.orders import ERPOrderGateway
from backend.app.repositories.orders import ProductionOrderRepository
from backend.app.services.order_sync_service import OrderSyncService


def main() -> None:
    with managed_connection() as connection:
        service = OrderSyncService(
            connection=connection,
            order_repository=ProductionOrderRepository(connection),
            order_gateway=ERPOrderGateway(),
        )
        result = service.sync_orders()
    print(result["message"])


if __name__ == "__main__":
    main()
