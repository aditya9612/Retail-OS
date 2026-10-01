import argparse
import getpass
import os
import sys

from pydantic import ValidationError

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.super_admin import SuperAdmin
from app.schemas.super_admin import SuperAdminCreate


def create_super_admin_bootstrap(
    email: str,
    full_name: str,
    password: str,
    phone: str | None = None,
    reset_password_if_exists: bool = False,
) -> None:
    """
    Creates the first and only Super Admin platform account.
    Enforces production SuperAdminCreate schema validations (including strict password rules).
    Enforces that ONLY ONE Super Admin is permitted in the entire system.
    """
    # 1. Validate data using production schema
    try:
        data = SuperAdminCreate(
            email=email,
            full_name=full_name,
            password=password,
            phone=phone,
        )
    except ValidationError as e:
        for err in e.errors():
            field = " -> ".join(str(loc) for loc in err.get("loc", []))
            print(f"Validation error ({field}): {err.get('msg')}", file=sys.stderr)
        sys.exit(1)

    # 2. Database transaction
    db = SessionLocal()
    try:
        clean_email = str(data.email).strip().lower()
        existing_any = db.query(SuperAdmin).first()

        if existing_any:
            if reset_password_if_exists and existing_any.email == clean_email:
                existing_any.hashed_password = get_password_hash(data.password)
                if data.full_name:
                    existing_any.full_name = data.full_name
                if data.phone:
                    existing_any.phone = data.phone
                existing_any.is_active = True
                db.commit()
                print(f"Super Admin password reset successfully: {existing_any.email}")
                return

            print(
                f"Error: Only ONE Super Admin is permitted in the system. A Super Admin already exists: {existing_any.email}",
                file=sys.stderr,
            )
            sys.exit(1)

        super_admin = SuperAdmin(
            email=clean_email,
            full_name=data.full_name,
            hashed_password=get_password_hash(data.password),
            phone=data.phone,
            is_active=True,
        )
        db.add(super_admin)
        db.commit()
        db.refresh(super_admin)

        print(f"Super Admin created successfully: {super_admin.email}")
    except Exception as e:
        db.rollback()
        print(f"Error creating Super Admin: {str(e)}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap canonical single Super Admin account"
    )
    parser.add_argument("--email", help="Super Admin email address", default=None)
    parser.add_argument("--full-name", help="Super Admin full name", default=None)
    parser.add_argument("--phone", help="Super Admin phone number (optional)", default=None)
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Reset password of existing single Super Admin if email matches",
        default=False,
    )

    args = parser.parse_args()

    email = args.email or os.getenv("SUPER_ADMIN_BOOTSTRAP_EMAIL")
    full_name = args.full_name or os.getenv("SUPER_ADMIN_BOOTSTRAP_NAME")
    phone = args.phone or os.getenv("SUPER_ADMIN_BOOTSTRAP_PHONE")

    # Interactive prompt if email or full_name not provided
    if not email:
        try:
            email = input("Enter Super Admin email: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.", file=sys.stderr)
            sys.exit(1)

    if not full_name:
        try:
            full_name = input("Enter Super Admin full name: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.", file=sys.stderr)
            sys.exit(1)

    # Password input: from environment variable (non-interactive) or getpass (interactive)
    password = os.getenv("SUPER_ADMIN_BOOTSTRAP_PASSWORD") or os.getenv("SUPER_ADMIN_PASSWORD")
    if not password:
        try:
            password = getpass.getpass("Enter Super Admin password: ")
            confirm_password = getpass.getpass("Confirm Super Admin password: ")
            if password != confirm_password:
                print("Error: Passwords do not match", file=sys.stderr)
                sys.exit(1)
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.", file=sys.stderr)
            sys.exit(1)

    create_super_admin_bootstrap(
        email=email,
        full_name=full_name,
        password=password,
        phone=phone,
        reset_password_if_exists=args.reset_password,
    )


if __name__ == "__main__":
    main()

