from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.api.routes import app_queries
from backend.app.db import initialize_database
from backend.app.services.app_service import AppService
from backend.app.services.order_pool_query_facade import OrderPoolQueryFacade
from backend.app.services.order_pool_query_facade_provider import create_order_pool_query_facade


class _StubOrderPoolFacade:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def list_order_pool(self, *, version_no: str | None = None) -> dict[str, object]:
        self.calls.append(("list_order_pool", (), {"version_no": version_no}))
        return {"items": [], "version_no": version_no}

    def get_order_pool_item(
        self,
        order_no: str,
        *,
        version_no: str | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            ("get_order_pool_item", (order_no,), {"version_no": version_no}),
        )
        return {"order_no": order_no, "version_no": version_no}

    def get_order_pool_process_timeline(
        self,
        order_no: str,
        *,
        process_code: str | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "get_order_pool_process_timeline",
                (order_no,),
                {"process_code": process_code},
            ),
        )
        return {"order_no": order_no, "process_code": process_code}

    def list_order_pool_materials(
        self,
        order_no: str,
        *,
        refresh: bool = False,
    ) -> dict[str, object]:
        self.calls.append(
            ("list_order_pool_materials", (order_no,), {"refresh": refresh}),
        )
        return {"order_no": order_no, "refresh": refresh}

    def list_material_children(
        self,
        parent_material_code: str,
        *,
        refresh: bool = False,
    ) -> dict[str, object]:
        self.calls.append(
            ("list_material_children", (parent_material_code,), {"refresh": refresh}),
        )
        return {"parent_material_code": parent_material_code, "refresh": refresh}


class AppQueriesOrderPoolFacadeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "order-pool-facade.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_create_order_pool_query_facade_wraps_app_service(self) -> None:
        facade = create_order_pool_query_facade(self.connection)

        self.assertIsInstance(facade, OrderPoolQueryFacade)
        self.assertIsInstance(facade.app_service, AppService)
        self.assertIs(facade.app_service.connection, self.connection)

    def test_order_pool_endpoints_delegate_to_facade(self) -> None:
        facade = _StubOrderPoolFacade()

        self.assertEqual(
            app_queries.list_order_pool(service=facade),
            {"items": [], "version_no": None},
        )
        self.assertEqual(
            app_queries.get_order_pool_item("MO-001", service=facade),
            {"order_no": "MO-001", "version_no": None},
        )
        self.assertEqual(
            app_queries.get_order_pool_process_timeline(
                "MO-001",
                service=facade,
                process_code="PROC-A",
            ),
            {"order_no": "MO-001", "process_code": "PROC-A"},
        )
        self.assertEqual(
            app_queries.list_order_pool_materials(
                "MO-001",
                service=facade,
                refresh=True,
            ),
            {"order_no": "MO-001", "refresh": True},
        )
        self.assertEqual(
            app_queries.list_material_children(
                "MAT-001",
                service=facade,
                refresh=True,
            ),
            {"parent_material_code": "MAT-001", "refresh": True},
        )
        self.assertEqual(
            [call[0] for call in facade.calls],
            [
                "list_order_pool",
                "get_order_pool_item",
                "get_order_pool_process_timeline",
                "list_order_pool_materials",
                "list_material_children",
            ],
        )


if __name__ == "__main__":
    unittest.main()
