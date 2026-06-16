"""Create MySQL database and tables for retail-saas."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import ensure_database_exists, get_database_name, init_db
from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    db_name = get_database_name(settings.DATABASE_URL)
    print(f"Using database: {db_name}")
    print("Creating database if missing...")
    ensure_database_exists()
    print("Creating tables...")
    init_db()
    print("Database ready.")


if __name__ == "__main__":
    main()
