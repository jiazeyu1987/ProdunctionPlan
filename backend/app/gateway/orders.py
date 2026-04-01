from __future__ import annotations

from ..config import get_settings
from .erp_client import ERPClient
from .models import ERPProductionOrder


class ERPOrderGateway:
    def __init__(self, client: ERPClient | None = None) -> None:
        self.settings = get_settings()
        self.client = client or ERPClient(self.settings)

    def fetch_orders(self) -> list[dict[str, object]]:
        items = self.client.post_items(self.settings.erp_orders_path, {})
        return [ERPProductionOrder.model_validate(item).model_dump() for item in items]
