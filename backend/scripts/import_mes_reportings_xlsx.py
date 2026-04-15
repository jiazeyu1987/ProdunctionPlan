from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.db import managed_connection  # noqa: E402
from backend.app.services.app_service import AppService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Import MES work reports from a .xlsx file.")
    parser.add_argument(
        "--file-path",
        required=True,
        help="Absolute or relative path to the .xlsx file on the backend host.",
    )
    parser.add_argument(
        "--sheet",
        action="append",
        dest="sheet_names",
        default=None,
        help="Sheet name to import (can be specified multiple times).",
    )
    parser.add_argument(
        "--company-code",
        default="COMPANY-MAIN",
        help="Company code written into work_reports.company_code.",
    )
    parser.add_argument(
        "--create-missing-orders",
        action="store_true",
        help="Create minimal production_orders rows when they are missing (so work_reports can be inserted).",
    )
    args = parser.parse_args()

    payload = {
        "file_path": args.file_path,
        "sheet_names": args.sheet_names,
        "company_code": args.company_code,
        "create_missing_orders": 1 if args.create_missing_orders else None,
    }

    with managed_connection() as connection:
        service = AppService(connection)
        result = service.import_mes_reportings_from_xlsx(payload)

    imported_count = int(result.get("imported_count") or 0)
    skipped_existing_count = int(result.get("skipped_existing_count") or 0)
    failed_count = int(result.get("failed_count") or 0)
    total_row_count = int(result.get("total_row_count") or 0)
    created_missing_order_count = int(result.get("created_missing_order_count") or 0)
    failures = list(result.get("failures") or [])

    print(f"Workbook: {result.get('file_path')}")
    if str(result.get("file_sha256") or "").strip():
        print(f"SHA256: {result.get('file_sha256')}")
    print(f"Sheets: {', '.join(result.get('sheet_names') or [])}")
    print(
        "Summary:",
        f"total={total_row_count}, imported={imported_count}, skipped_existing={skipped_existing_count}, failed={failed_count}, created_missing_orders={created_missing_order_count}",
    )
    if failures:
        print("\nFailures (first 20):")
        for item in failures[:20]:
            print(json.dumps(item, ensure_ascii=False))
        remaining = len(failures) - 20
        if remaining > 0:
            print(f"... and {remaining} more")


if __name__ == "__main__":
    main()
