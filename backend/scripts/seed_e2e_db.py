from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth import ROLE_SCHEDULER, ROLE_WORKSHOP_MANAGER, register_user
from app.db import initialize_database, transaction


COMPANY_CODE = "COMPANY-MAIN"
WORKSHOP_CODE = "WS-CATH"
WORKSHOP_NAME = "导管车间"
ACCESSIBLE_LINE_CODE = "LINE-ALPHA"
ACCESSIBLE_LINE_NAME = "成型一线"
INACCESSIBLE_LINE_CODE = "LINE-OMEGA"
INACCESSIBLE_LINE_NAME = "成型二线"

PRODUCT_CODE = "PROD_CATH"
PRODUCT_NAME = "导管组件"
ROUTE_NO = "ROUTE-CATH-001"
ROUTE_NAME = "导管标准工艺"

BASE_DATE = "2026-04-10"
PREVIOUS_DATE = "2026-04-09"
NEXT_DATE = "2026-04-11"
UPDATED_AT = "2026-04-10T00:00:00+00:00"
PREVIOUS_REPORT_TIME = "2026-04-09T08:30:00+08:00"

SCHEDULER_ACCOUNT = {
    "username": "scheduler_e2e",
    "password": "Passw0rd!",
    "display_name": "E2E排产员",
    "role_code": ROLE_SCHEDULER,
}

MANAGER_ACCOUNT = {
    "username": "manager_e2e",
    "password": "Passw0rd!",
    "display_name": "E2E车间主任",
    "role_code": ROLE_WORKSHOP_MANAGER,
}

PROCESS_ROUTES = [
    {
        "sequence_no": 1,
        "process_code": "PROC_TUBE",
        "process_name_cn": "成型",
        "dependency_type": "FS",
        "is_final_process": 0,
    },
    {
        "sequence_no": 2,
        "process_code": "PROC_COAT",
        "process_name_cn": "涂层",
        "dependency_type": "FS",
        "is_final_process": 0,
    },
    {
        "sequence_no": 3,
        "process_code": "PROC_PACK",
        "process_name_cn": "包装",
        "dependency_type": "FS",
        "is_final_process": 1,
    },
]

LINE_TOPOLOGY_ROWS = [
    {
        "company_code": COMPANY_CODE,
        "workshop_code": WORKSHOP_CODE,
        "workshop_name": WORKSHOP_NAME,
        "line_code": ACCESSIBLE_LINE_CODE,
        "line_name": ACCESSIBLE_LINE_NAME,
        "process_code": "PROC_TUBE",
        "capacity_per_shift": 120,
        "required_workers": 6,
        "required_machines": 2,
    },
    {
        "company_code": COMPANY_CODE,
        "workshop_code": WORKSHOP_CODE,
        "workshop_name": WORKSHOP_NAME,
        "line_code": ACCESSIBLE_LINE_CODE,
        "line_name": ACCESSIBLE_LINE_NAME,
        "process_code": "PROC_COAT",
        "capacity_per_shift": 90,
        "required_workers": 5,
        "required_machines": 0,
    },
    {
        "company_code": COMPANY_CODE,
        "workshop_code": WORKSHOP_CODE,
        "workshop_name": WORKSHOP_NAME,
        "line_code": ACCESSIBLE_LINE_CODE,
        "line_name": ACCESSIBLE_LINE_NAME,
        "process_code": "PROC_PACK",
        "capacity_per_shift": 150,
        "required_workers": 4,
        "required_machines": 0,
    },
    {
        "company_code": COMPANY_CODE,
        "workshop_code": WORKSHOP_CODE,
        "workshop_name": WORKSHOP_NAME,
        "line_code": INACCESSIBLE_LINE_CODE,
        "line_name": INACCESSIBLE_LINE_NAME,
        "process_code": "PROC_TUBE",
        "capacity_per_shift": 110,
        "required_workers": 6,
        "required_machines": 2,
    },
    {
        "company_code": COMPANY_CODE,
        "workshop_code": WORKSHOP_CODE,
        "workshop_name": WORKSHOP_NAME,
        "line_code": INACCESSIBLE_LINE_CODE,
        "line_name": INACCESSIBLE_LINE_NAME,
        "process_code": "PROC_COAT",
        "capacity_per_shift": 80,
        "required_workers": 5,
        "required_machines": 0,
    },
    {
        "company_code": COMPANY_CODE,
        "workshop_code": WORKSHOP_CODE,
        "workshop_name": WORKSHOP_NAME,
        "line_code": INACCESSIBLE_LINE_CODE,
        "line_name": INACCESSIBLE_LINE_NAME,
        "process_code": "PROC_PACK",
        "capacity_per_shift": 140,
        "required_workers": 4,
        "required_machines": 0,
    },
]

ORDERS = [
    {
        "order_no": "MO-CATH-001",
        "qty": 180,
        "planned_start_date": BASE_DATE,
        "planned_end_date": NEXT_DATE,
        "source_bill_no": "SO-E2E-001",
        "material_list_no": "BOM-E2E-001",
        "priority_level": 1,
    },
    {
        "order_no": "MO-CATH-002",
        "qty": 120,
        "planned_start_date": BASE_DATE,
        "planned_end_date": NEXT_DATE,
        "source_bill_no": "SO-E2E-002",
        "material_list_no": "BOM-E2E-002",
        "priority_level": 3,
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an isolated SQLite database for E2E runs.")
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the SQLite database file to create.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output database if it already exists.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output.",
    )
    return parser.parse_args()


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def remove_existing_database(database_path: Path, force: bool) -> None:
    if not database_path.exists():
        return
    if not force:
        raise SystemExit(
            f"Output database already exists: {database_path}. Re-run with --force to overwrite it."
        )
    database_path.unlink()


def register_seed_user(connection: sqlite3.Connection, account: dict[str, str]) -> dict[str, str]:
    register_user(connection, account)
    row = connection.execute(
        """
        SELECT user_id, username, display_name, role_code
        FROM app_users
        WHERE username = ?
        """,
        (account["username"],),
    ).fetchone()
    if row is None:
        raise SystemExit(f"Failed to locate seeded user: {account['username']}")
    return {
        "user_id": str(row["user_id"]),
        "username": str(row["username"]),
        "display_name": str(row["display_name"]),
        "role_code": str(row["role_code"]),
    }


def seed_masterdata(connection: sqlite3.Connection) -> None:
    with transaction(connection):
        connection.executemany(
            """
            INSERT INTO masterdata_process_routes (
                product_code,
                sequence_no,
                process_code,
                process_name_cn,
                dependency_type,
                route_no,
                route_name_cn,
                product_name_cn,
                is_final_process,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    PRODUCT_CODE,
                    row["sequence_no"],
                    row["process_code"],
                    row["process_name_cn"],
                    row["dependency_type"],
                    ROUTE_NO,
                    ROUTE_NAME,
                    PRODUCT_NAME,
                    row["is_final_process"],
                    UPDATED_AT,
                )
                for row in PROCESS_ROUTES
            ],
        )
        connection.executemany(
            """
            INSERT INTO masterdata_line_skeletons (
                company_code,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                enabled_flag,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            [
                (
                    COMPANY_CODE,
                    WORKSHOP_CODE,
                    WORKSHOP_NAME,
                    ACCESSIBLE_LINE_CODE,
                    ACCESSIBLE_LINE_NAME,
                    UPDATED_AT,
                ),
                (
                    COMPANY_CODE,
                    WORKSHOP_CODE,
                    WORKSHOP_NAME,
                    INACCESSIBLE_LINE_CODE,
                    INACCESSIBLE_LINE_NAME,
                    UPDATED_AT,
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO masterdata_line_topology (
                company_code,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                process_code,
                capacity_per_shift,
                required_workers,
                required_machines,
                enabled_flag,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            [
                (
                    row["company_code"],
                    row["workshop_code"],
                    row["workshop_name"],
                    row["line_code"],
                    row["line_name"],
                    row["process_code"],
                    row["capacity_per_shift"],
                    row["required_workers"],
                    row["required_machines"],
                    UPDATED_AT,
                )
                for row in LINE_TOPOLOGY_ROWS
            ],
        )


def seed_orders(connection: sqlite3.Connection) -> None:
    with transaction(connection):
        connection.executemany(
            """
            INSERT INTO production_orders (
                production_order_no,
                material_code,
                material_name,
                material_specification,
                production_qty,
                status,
                planned_start_date,
                planned_end_date,
                source_bill_no,
                material_list_no,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    order["order_no"],
                    PRODUCT_CODE,
                    PRODUCT_NAME,
                    "6F",
                    order["qty"],
                    "OPEN",
                    order["planned_start_date"],
                    order["planned_end_date"],
                    order["source_bill_no"],
                    order["material_list_no"],
                    UPDATED_AT,
                )
                for order in ORDERS
            ],
        )
        connection.executemany(
            """
            INSERT INTO order_pool_state (
                production_order_no,
                promised_due_date,
                expected_start_date,
                expected_start_time,
                expected_finish_time,
                priority_level,
                urgent_flag,
                lock_flag,
                frozen_flag,
                status,
                order_status,
                completed_qty,
                remaining_qty,
                progress_rate,
                production_batch_no,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, 0, ?, 0, ?, ?)
            """,
            [
                (
                    order["order_no"],
                    order["planned_end_date"],
                    order["planned_start_date"],
                    f"{order['planned_start_date']}T08:00:00+08:00",
                    f"{order['planned_end_date']}T18:00:00+08:00",
                    order["priority_level"],
                    1 if order["priority_level"] == 1 else 0,
                    "OPEN",
                    "OPEN",
                    order["qty"],
                    f"{order['source_bill_no']}-B1",
                    UPDATED_AT,
                )
                for order in ORDERS
            ],
        )
        capacity_rows: list[tuple[object, ...]] = []
        for order in ORDERS:
            for route in PROCESS_ROUTES:
                topology = next(
                    item
                    for item in LINE_TOPOLOGY_ROWS
                    if item["line_code"] == ACCESSIBLE_LINE_CODE
                    and item["process_code"] == route["process_code"]
                )
                capacity_rows.append(
                    (
                        order["order_no"],
                        route["process_code"],
                        route["process_name_cn"],
                        WORKSHOP_CODE,
                        WORKSHOP_NAME,
                        ACCESSIBLE_LINE_CODE,
                        ACCESSIBLE_LINE_NAME,
                        topology["capacity_per_shift"],
                        UPDATED_AT,
                    )
                )
        connection.executemany(
            """
            INSERT INTO capacity_bindings (
                production_order_no,
                process_code,
                workshop_code,
                line_code,
                process_name,
                workshop_name,
                line_name,
                capacity_qty,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            capacity_rows,
        )
        connection.executemany(
            """
            INSERT INTO material_issue_items (
                production_order_no,
                child_material_code,
                child_material_name,
                spec_model,
                issue_qty,
                supply_type_code,
                supply_type_name,
                inventory_qty,
                inventory_status,
                usage_numerator,
                usage_denominator,
                child_unit,
                expandable,
                display_order,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "MO-CATH-001",
                    "SUBASSY-E2E-001",
                    "自制芯轴",
                    "A",
                    180,
                    "SELF_MADE",
                    "自制",
                    500,
                    "OK",
                    1,
                    1,
                    "EA",
                    1,
                    1,
                    UPDATED_AT,
                ),
                (
                    "MO-CATH-001",
                    "MAT-E2E-002",
                    "外购包材",
                    "B",
                    180,
                    "PURCHASED",
                    "外购",
                    1000,
                    "OK",
                    1,
                    1,
                    "EA",
                    0,
                    2,
                    UPDATED_AT,
                ),
                (
                    "MO-CATH-002",
                    "SUBASSY-E2E-001",
                    "自制芯轴",
                    "A",
                    120,
                    "SELF_MADE",
                    "自制",
                    500,
                    "OK",
                    1,
                    1,
                    "EA",
                    1,
                    1,
                    UPDATED_AT,
                ),
                (
                    "MO-CATH-002",
                    "MAT-E2E-003",
                    "外购涂层剂",
                    "C",
                    120,
                    "PURCHASED",
                    "外购",
                    600,
                    "OK",
                    1,
                    1,
                    "EA",
                    0,
                    2,
                    UPDATED_AT,
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO bom_children (
                parent_material_code,
                child_material_code,
                child_material_name,
                child_specification,
                usage_numerator,
                usage_denominator,
                child_unit,
                supply_type_code,
                supply_type_name,
                inventory_qty,
                inventory_status,
                expandable,
                display_order,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "SUBASSY-E2E-001",
                    "MAT-WIRE-001",
                    "钢丝",
                    "0.2mm",
                    1,
                    1,
                    "EA",
                    "PURCHASED",
                    "外购",
                    800,
                    "OK",
                    0,
                    1,
                    UPDATED_AT,
                ),
                (
                    "SUBASSY-E2E-001",
                    "MAT-TIP-001",
                    "头端组件",
                    "STD",
                    1,
                    1,
                    "EA",
                    "PURCHASED",
                    "外购",
                    800,
                    "OK",
                    0,
                    2,
                    UPDATED_AT,
                ),
            ],
        )


def seed_capacity_baseline(connection: sqlite3.Connection) -> None:
    previous_plan_rows: list[tuple[object, ...]] = []
    for topology in LINE_TOPOLOGY_ROWS:
        previous_plan_rows.append(
            (
                PREVIOUS_DATE,
                "DAY",
                topology["company_code"],
                topology["workshop_code"],
                topology["line_code"],
                topology["process_code"],
                topology["capacity_per_shift"],
                topology["required_workers"],
                topology["required_machines"],
                "SEEDED_PREVIOUS_DAY",
                UPDATED_AT,
            )
        )
    with transaction(connection):
        connection.executemany(
            """
            INSERT INTO daily_line_capacity_plan (
                calendar_date,
                shift_code,
                company_code,
                workshop_code,
                line_code,
                process_code,
                planned_capacity_qty,
                worker_count,
                machine_count,
                source_note,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            previous_plan_rows,
        )
        connection.execute(
            """
            INSERT INTO work_reports (
                report_id,
                production_order_no,
                process_code,
                process_name,
                workshop_code,
                workshop_name,
                line_code,
                line_name,
                report_qty,
                report_time,
                operator_name,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "RPT-SEED-0001",
                "MO-CATH-001",
                "PROC_PACK",
                "包装",
                WORKSHOP_CODE,
                WORKSHOP_NAME,
                ACCESSIBLE_LINE_CODE,
                ACCESSIBLE_LINE_NAME,
                15,
                PREVIOUS_REPORT_TIME,
                "系统种子",
                UPDATED_AT,
            ),
        )


def seed_user_scope(
    connection: sqlite3.Connection,
    *,
    manager_user_id: str,
) -> None:
    with transaction(connection):
        connection.execute(
            """
            INSERT INTO app_user_line_scopes (
                user_id,
                company_code,
                workshop_code,
                line_code,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                manager_user_id,
                COMPANY_CODE,
                WORKSHOP_CODE,
                ACCESSIBLE_LINE_CODE,
                UPDATED_AT,
            ),
        )
        connection.execute(
            """
            INSERT INTO masterdata_workshop_manager_visibility (
                user_id,
                visible_flag,
                updated_at
            ) VALUES (?, 1, ?)
            """,
            (manager_user_id, UPDATED_AT),
        )


def seed_runtime_state(connection: sqlite3.Connection) -> None:
    with transaction(connection):
        connection.execute(
            """
            INSERT INTO simulation_state (
                singleton_key,
                current_date,
                updated_at
            ) VALUES ('default', ?, ?)
            ON CONFLICT(singleton_key) DO UPDATE SET
                current_date = excluded.current_date,
                updated_at = excluded.updated_at
            """,
            (BASE_DATE, UPDATED_AT),
        )
        connection.execute(
            """
            INSERT INTO schedule_calendar_rules (
                singleton_key,
                horizon_start_date,
                horizon_days,
                skip_statutory_holidays,
                weekend_rest_mode,
                date_shift_mode_by_date_json,
                updated_at
            ) VALUES ('default', ?, 31, 0, 'DOUBLE', '{}', ?)
            ON CONFLICT(singleton_key) DO UPDATE SET
                horizon_start_date = excluded.horizon_start_date,
                horizon_days = excluded.horizon_days,
                skip_statutory_holidays = excluded.skip_statutory_holidays,
                weekend_rest_mode = excluded.weekend_rest_mode,
                date_shift_mode_by_date_json = excluded.date_shift_mode_by_date_json,
                updated_at = excluded.updated_at
            """,
            (BASE_DATE, UPDATED_AT),
        )


def build_summary(database_path: Path, scheduler_user: dict[str, str], manager_user: dict[str, str]) -> dict[str, object]:
    return {
        "database_path": str(database_path),
        "base_date": BASE_DATE,
        "accounts": {
            "scheduler": {
                "username": SCHEDULER_ACCOUNT["username"],
                "password": SCHEDULER_ACCOUNT["password"],
                "display_name": scheduler_user["display_name"],
                "user_id": scheduler_user["user_id"],
            },
            "workshop_manager": {
                "username": MANAGER_ACCOUNT["username"],
                "password": MANAGER_ACCOUNT["password"],
                "display_name": manager_user["display_name"],
                "user_id": manager_user["user_id"],
            },
        },
        "orders": [order["order_no"] for order in ORDERS],
        "accessible_line": {
            "workshop_code": WORKSHOP_CODE,
            "line_code": ACCESSIBLE_LINE_CODE,
            "process_codes": [row["process_code"] for row in PROCESS_ROUTES],
        },
        "inaccessible_line": {
            "workshop_code": WORKSHOP_CODE,
            "line_code": INACCESSIBLE_LINE_CODE,
            "process_codes": [row["process_code"] for row in PROCESS_ROUTES],
        },
    }


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    remove_existing_database(output_path, args.force)
    initialize_database(output_path)

    connection = connect(output_path)
    try:
        scheduler_user = register_seed_user(connection, SCHEDULER_ACCOUNT)
        manager_user = register_seed_user(connection, MANAGER_ACCOUNT)
        seed_masterdata(connection)
        seed_orders(connection)
        seed_capacity_baseline(connection)
        seed_user_scope(connection, manager_user_id=manager_user["user_id"])
        seed_runtime_state(connection)
        summary = build_summary(output_path, scheduler_user, manager_user)
    finally:
        connection.close()

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Created E2E database: {summary['database_path']}")
        print(f"Base date: {summary['base_date']}")
        print(
            "Scheduler account: "
            f"{SCHEDULER_ACCOUNT['username']} / {SCHEDULER_ACCOUNT['password']}"
        )
        print(
            "Workshop manager account: "
            f"{MANAGER_ACCOUNT['username']} / {MANAGER_ACCOUNT['password']}"
        )
        print("Orders: " + ", ".join(summary["orders"]))
        print(
            "Accessible line: "
            f"{WORKSHOP_CODE}/{ACCESSIBLE_LINE_CODE} "
            f"({', '.join(summary['accessible_line']['process_codes'])})"
        )
        print(
            "Inaccessible line: "
            f"{WORKSHOP_CODE}/{INACCESSIBLE_LINE_CODE} "
            f"({', '.join(summary['inaccessible_line']['process_codes'])})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
