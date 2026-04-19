from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.db import initialize_database
from backend.app.services.app_service import AppService
from backend.app.services.app_service_provider import create_app_service
from backend.app.services.legacy_runtime import LegacyAppRuntime


class AppServiceProviderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "app-service-provider.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_create_app_service_builds_default_runtime(self) -> None:
        service = create_app_service(self.connection)

        self.assertIsInstance(service, AppService)
        self.assertIs(service.connection, self.connection)
        self.assertIsNotNone(service.runtime)
        self.assertIs(service.factory, service.runtime.factory)
        self.assertIs(
            service.line_daily_capacity_service,
            service.runtime.line_daily_capacity_service,
        )

    def test_create_app_service_reuses_explicit_runtime(self) -> None:
        runtime = LegacyAppRuntime(
            factory=object(),
            line_daily_capacity_service=object(),
            masterdata_gateway=object(),
            order_gateway=object(),
            inventory_gateway=object(),
            supply_gateway=object(),
        )

        service = create_app_service(self.connection, runtime=runtime)

        self.assertIs(service.runtime, runtime)
        self.assertIs(service.factory, runtime.factory)
        self.assertIs(
            service.line_daily_capacity_service,
            runtime.line_daily_capacity_service,
        )
        self.assertIs(service.masterdata_gateway, runtime.masterdata_gateway)
        self.assertIs(service.order_gateway, runtime.order_gateway)
        self.assertIs(service.inventory_gateway, runtime.inventory_gateway)
        self.assertIs(service.supply_gateway, runtime.supply_gateway)


if __name__ == "__main__":
    unittest.main()
