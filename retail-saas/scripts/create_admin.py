"""Bootstrap first tenant and admin user."""

import sys

from app.core.database import SessionLocal
from app.services.auth_service import AuthService


def main():
    if len(sys.argv) < 6:
        print("Usage: python scripts/create_admin.py <tenant_name> <slug> <email> <admin_name> <password>")
        sys.exit(1)

    tenant_name, slug, email, admin_name, password = sys.argv[1:6]
    db = SessionLocal()
    try:
        user = AuthService(db).register_tenant(tenant_name, slug, email, admin_name, password)
        print(f"Admin created: user_id={user.id}, tenant_id={user.tenant_id}, email={user.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
