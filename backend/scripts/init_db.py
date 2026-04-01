from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.db import initialize_database


def main() -> None:
    database_path = initialize_database()
    print(f"Initialized SQLite database: {database_path}")


if __name__ == "__main__":
    main()
