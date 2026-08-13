from getpass import getpass

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.role import Role
from app.models.user import User
from app.utils.constants import (
    DEFAULT_ROLE_PERMISSIONS,
    UserRole,
)


def create_superadmin():
    db = SessionLocal()

    try:
        email = input(
            "Enter SuperAdmin email: "
        ).strip()

        full_name = input(
            "Enter SuperAdmin name: "
        ).strip()

        password = getpass(
            "Enter SuperAdmin password: "
        )

        if not email or not full_name or not password:
            print("All fields are required.")
            return

        existing_user = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if existing_user:
            print(
                "A user with this email already exists."
            )
            return

        # Find existing platform-level SuperAdmin role
        role = (
            db.query(Role)
            .filter(
                Role.tenant_id.is_(None),
                Role.name == UserRole.SUPERADMIN.value,
            )
            .first()
        )

        # Create role if it does not exist
        if not role:
            role = Role(
                tenant_id=None,
                name=UserRole.SUPERADMIN.value,
                description="Platform SuperAdmin",
                permissions=DEFAULT_ROLE_PERMISSIONS[
                    UserRole.SUPERADMIN
                ],
            )

            db.add(role)
            db.flush()

        user = User(
            tenant_id=None,
            store_id=None,
            role_id=role.id,
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            phone=None,
            is_active=True,
        )

        db.add(user)
        db.commit()

        print(
            f"SuperAdmin created successfully. "
            f"User ID: {user.id}"
        )

    except Exception as exc:
        db.rollback()
        print(f"Error creating SuperAdmin: {exc}")

    finally:
        db.close()


if __name__ == "__main__":
    create_superadmin()