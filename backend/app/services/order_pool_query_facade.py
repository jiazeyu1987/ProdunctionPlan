from __future__ import annotations

from typing import Any

from .app_service import AppService


class OrderPoolQueryFacade:
    def __init__(self, app_service: AppService) -> None:
        self.app_service = app_service

    def list_order_pool(self, *, version_no: str | None = None) -> dict[str, Any]:
        return self.app_service.list_order_pool(version_no=version_no)

    def get_order_pool_item(
        self,
        order_no: str,
        *,
        version_no: str | None = None,
    ) -> dict[str, Any]:
        return self.app_service.get_order_pool_item(order_no, version_no=version_no)

    def get_order_pool_process_timeline(
        self,
        order_no: str,
        *,
        process_code: str | None = None,
    ) -> dict[str, Any]:
        return self.app_service.get_order_pool_process_timeline(
            order_no,
            process_code=process_code,
        )

    def list_order_pool_materials(
        self,
        order_no: str,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        return self.app_service.list_order_pool_materials(order_no, refresh=refresh)

    def list_material_children(
        self,
        parent_material_code: str,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        return self.app_service.list_material_children(
            parent_material_code,
            refresh=refresh,
        )
