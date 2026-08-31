from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import get_password_hash
from app.models.role import Role
from app.models.store import Store
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = UserRepository(db)

    def create_user(self, tenant_id: int, data: UserCreate) -> User:
        if tenant_id is None:
            raise ConflictException("Tenant is required")

        email = str(data.email).strip().lower()

        existing = self.repo.get_by_email(email, tenant_id)

        if existing:
            raise ConflictException("Email already registered")

        role = (
            self.db.query(Role)
            .filter(
                Role.id == data.role_id,
                Role.tenant_id == tenant_id,
            )
            .first()
        )

        if not role:
            raise NotFoundException("Role not found")

        if data.store_id is not None:
            store = (
                self.db.query(Store)
                .filter(
                    Store.id == data.store_id,
                    Store.tenant_id == tenant_id,
                    Store.is_active.is_(True),
                )
                .first()
            )

            if not store:
                raise NotFoundException("Store not found")

        user = User(
            tenant_id=tenant_id,
            email=email,
            full_name=data.full_name.strip(),
            phone=data.phone,
            store_id=data.store_id,
            role_id=data.role_id,
            hashed_password=get_password_hash(data.password),
            is_active=True,
        )

        return self.repo.create(user)

    def get_user(self, tenant_id: int, user_id: int) -> User:
        if user_id <= 0:
            raise NotFoundException("User not found")

        user = self.repo.get_by_id(user_id, tenant_id)

        if not user:
            raise NotFoundException("User not found")

        return user

    def list_users(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        include_inactive: bool = False,
    ) -> list[User]:
        if skip < 0:
            skip = 0

        if limit < 1:
            limit = 20

        if limit > 100:
            limit = 100

        return self.repo.list_users(
            tenant_id=tenant_id,
            skip=skip,
            limit=limit,
            include_inactive=include_inactive,
        )

    def update_user(
        self,
        tenant_id: int,
        user_id: int,
        data: UserUpdate,
    ) -> User:
        user = self.get_user(tenant_id, user_id)

        update_data = data.model_dump(exclude_unset=True)

        if not update_data:
            raise ConflictException("No fields provided for update")

        if "role_id" in update_data:
            role = (
                self.db.query(Role)
                .filter(
                    Role.id == update_data["role_id"],
                    Role.tenant_id == tenant_id,
                )
                .first()
            )

            if not role:
                raise NotFoundException("Role not found")

        if "store_id" in update_data:
            store_id = update_data["store_id"]

            if store_id is not None:
                store = (
                    self.db.query(Store)
                    .filter(
                        Store.id == store_id,
                        Store.tenant_id == tenant_id,
                        Store.is_active.is_(True),
                    )
                    .first()
                )

                if not store:
                    raise NotFoundException("Store not found")

        if "full_name" in update_data:
            full_name = update_data["full_name"].strip()

            if not full_name:
                raise ConflictException("Full name cannot be empty")

            update_data["full_name"] = full_name

        if "phone" in update_data:
            phone = update_data["phone"]

            if phone is not None:
                phone = phone.strip()

                if not phone.isdigit():
                    raise ConflictException("Phone must contain digits only")

                if len(phone) < 10 or len(phone) > 15:
                    raise ConflictException(
                        "Phone must contain 10 to 15 digits"
                    )

                update_data["phone"] = phone

        if "password" in update_data:
            password = update_data.pop("password")

            if password:
                update_data["hashed_password"] = get_password_hash(password)

        for key, value in update_data.items():
            setattr(user, key, value)

        return self.repo.update(user)

    def activate_user(self, tenant_id: int, user_id: int) -> User:
        user = self.get_user(tenant_id, user_id)

        if user.is_active:
            raise ConflictException("User is already active")

        user.is_active = True

        return self.repo.update(user)

    def deactivate_user(
        self,
        tenant_id: int,
        user_id: int,
        current_user_id: int,
    ) -> User:
        user = self.get_user(tenant_id, user_id)

        if user.id == current_user_id:
            raise ConflictException(
                "You cannot deactivate your own account"
            )

        if not user.is_active:
            raise ConflictException("User is already inactive")

        user.is_active = False

        return self.repo.update(user)

    def delete_user(
        self,
        tenant_id: int,
        user_id: int,
        current_user_id: int,
    ) -> None:
        user = self.get_user(tenant_id, user_id)

        if user.id == current_user_id:
            raise ConflictException(
                "You cannot delete your own account"
            )

        if not user.is_active:
            raise ConflictException("User is already inactive")

        user.is_active = False

        self.repo.update(user)