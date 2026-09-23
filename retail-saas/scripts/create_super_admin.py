"""Bootstrap first Super Admin user via CLI."""

import sys
from app.core.database import SessionLocal
from app.schemas.super_admin import SuperAdminCreate
from app.services.super_admin_service import SuperAdminService


def main():
    if len(sys.argv) < 4:
        print("Usage: python scripts/create_super_admin.py <email> <full_name> <password> [phone]")
        sys.exit(1)

    email = sys.argv[1]
    full_name = sys.argv[2]
    password = sys.argv[3]
    phone = sys.argv[4] if len(sys.argv) > 4 else None

    db = SessionLocal()
    try:
        data = SuperAdminCreate(
            email=email,
            full_name=full_name,
            password=password,
            phone=phone,
        )
        super_admin = SuperAdminService(db).create_super_admin(data)
        print(f"Super Admin created successfully: id={super_admin.id}, email={super_admin.email}, name={super_admin.full_name}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
