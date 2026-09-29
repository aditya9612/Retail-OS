"""Bootstrap first Super Admin user via CLI."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.super_admin import SuperAdmin
from app.schemas.super_admin import SuperAdminCreate
from app.services.super_admin_service import SuperAdminService


def main():
    args = [arg for arg in sys.argv[1:] if arg not in ("--reset", "--force")]
    reset_flag = any(arg in ("--reset", "--force") for arg in sys.argv[1:])

    if len(args) < 3:
        print("Usage: python scripts/create_super_admin.py <email> <full_name> <password> [phone] [--reset]")
        sys.exit(1)

    email = args[0]
    full_name = args[1]
    password = args[2]
    phone = args[3] if len(args) > 3 else None

    db = SessionLocal()
    try:
        data = SuperAdminCreate(
            email=email,
            full_name=full_name,
            password=password,
            phone=phone,
        )

        existing = db.query(SuperAdmin).first()
        if existing:
            if reset_flag:
                existing.email = data.email
                existing.full_name = data.full_name
                existing.hashed_password = get_password_hash(data.password)
                existing.phone = data.phone
                existing.is_active = True
                db.commit()
                db.refresh(existing)
                print(f"Existing Super Admin updated/reset successfully: id={existing.id}, email={existing.email}, name={existing.full_name}")
                return

            print(
                f"\n[WARNING] A Super Admin already exists in the system:\n"
                f"    ID: {existing.id}\n"
                f"    Email: {existing.email}\n"
                f"    Name: {existing.full_name}\n\n"
                f"The system allows only ONE Super Admin.\n"
                f"To overwrite/update this Super Admin with your new credentials, run with --reset:\n"
                f"python scripts/create_super_admin.py \"{email}\" \"{full_name}\" \"{password}\" {phone or ''} --reset\n"
            )
            sys.exit(1)

        super_admin = SuperAdminService(db).create_super_admin(data)
        print(f"Super Admin created successfully: id={super_admin.id}, email={super_admin.email}, name={super_admin.full_name}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
