from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import get_password_hash
from app.models.role import Role
from app.models.saas_plan_entitlement import EntitlementDimension
from app.models.store import Store
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.user import MyProfileUpdate, UserCreate, UserUpdate
from app.services.saas_entitlement_service import SaaSEntitlementService
from app.utils.phone import normalize_phone_number


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = UserRepository(db)

    def create_user(
        self,
        tenant_id: int,
        data: UserCreate,
    ) -> User:
        if tenant_id is None:
            raise ConflictException("Tenant is required")

        email = str(data.email).strip().lower()

        existing = self.repo.get_by_email(
            email,
            tenant_id,
        )

        if existing:
            raise ConflictException(
                "Email already registered"
            )

        role = None
        if data.role_id is not None:
            role = (
                self.db.query(Role)
                .filter(
                    Role.id == data.role_id,
                    Role.tenant_id == tenant_id,
                )
                .first()
            )
        elif getattr(data, "role", None):
            role_str = str(data.role).strip().lower()
            role = (
                self.db.query(Role)
                .filter(
                    Role.name == role_str,
                    Role.tenant_id == tenant_id,
                )
                .first()
            )

        if not role:
            raise NotFoundException(
                "Role not found. Use GET /api/v1/roles to get valid Roles."
            )

        resolved_role_id = role.id

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
                raise NotFoundException(
                    "Store not found"
                )

        # Atomic tenant lock & quota check
        entitlement_svc = SaaSEntitlementService(self.db)
        entitlement_svc.require_limit(
            tenant_id=tenant_id,
            dimension=EntitlementDimension.USERS,
            requested_amount=1,
            lock_tenant=True,
        )

        canonical_phone = None
        if data.phone:
            canonical_phone = normalize_phone_number(data.phone)
            existing_phone_user = self.repo.get_active_user_by_phone(canonical_phone)
            if existing_phone_user:
                raise ConflictException("Phone number is already registered")

        user = User(
            tenant_id=tenant_id,
            email=email,
            full_name=data.full_name.strip(),
            phone=canonical_phone,
            store_id=data.store_id,
            role_id=resolved_role_id,
            hashed_password=get_password_hash(
                data.password
            ),
            is_active=True,
            is_deleted=False,
            pancard=getattr(data, "pancard", None),
            addhar_card=getattr(data, "addhar_card", None),
            profile_photo=getattr(data, "profile_photo", None),
            pan_number=getattr(data, "pan_number", None),
            addhar_number=getattr(data, "addhar_number", None),
        )

        try:
            user = self.repo.create(user)
            self.db.commit()
            self.db.refresh(user)
            return user
        except IntegrityError as exc:
            self.db.rollback()
            if "uq_users_active_phone" in str(exc) or "active_phone" in str(exc).lower():
                raise ConflictException("Phone number is already registered") from exc
            raise ConflictException("User already exists") from exc

    def list_roles(
        self,
        tenant_id: int,
    ) -> list[Role]:
        if tenant_id is None:
            raise ConflictException(
                "Tenant is required"
            )

        roles = (
            self.db.query(Role)
            .filter(
                Role.tenant_id == tenant_id,
            )
            .order_by(Role.id.asc())
            .all()
        )

        for role in roles:
            if role.permissions is None:
                role.permissions = []

        return roles

    def get_user(
        self,
        tenant_id: int,
        user_id: int,
    ) -> User:
        if user_id <= 0:
            raise NotFoundException(
                "User not found"
            )

        user = self.repo.get_by_id(
            user_id=user_id,
            tenant_id=tenant_id,
            include_deleted=False,
        )

        if not user:
            raise NotFoundException(
                "User not found"
            )

        if user.role is not None and user.role.permissions is None:
            user.role.permissions = []

        return user

    def list_users(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        include_inactive: bool = False,
        store_id: int | None = None,
    ) -> list[User]:
        if skip < 0:
            skip = 0

        if limit < 1:
            limit = 20

        if limit > 100:
            limit = 100

        users = self.repo.list_users(
            tenant_id=tenant_id,
            skip=skip,
            limit=limit,
            include_inactive=include_inactive,
            store_id=store_id,
        )

        return users

    def update_user(
        self,
        tenant_id: int,
        user_id: int,
        data: UserUpdate,
    ) -> User:
        user = self.get_user(
            tenant_id,
            user_id,
        )

        update_data = data.model_dump(
            exclude_unset=True
        )

        if not update_data:
            raise ConflictException(
                "No fields provided for update"
            )

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
                raise NotFoundException(
                    "Role not found. Use GET /api/v1/roles to get valid Role IDs."
                )

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
                    raise NotFoundException(
                        "Store not found"
                    )

        if "full_name" in update_data:
            full_name = update_data[
                "full_name"
            ].strip()

            if not full_name:
                raise ConflictException(
                    "Full name cannot be empty"
                )

            update_data["full_name"] = full_name

        if "password" in update_data:
            password = update_data.pop(
                "password"
            )

            if password:
                update_data[
                    "hashed_password"
                ] = get_password_hash(password)

        if "phone" in update_data:
            raw_phone = update_data["phone"]
            if raw_phone:
                canonical_phone = normalize_phone_number(raw_phone)
                update_data["phone"] = canonical_phone
                if canonical_phone != user.phone:
                    existing_phone_user = self.repo.get_active_user_by_phone(canonical_phone)
                    if existing_phone_user and existing_phone_user.id != user.id:
                        raise ConflictException("Phone number is already in use")
            else:
                update_data["phone"] = None

        try:
            for key, value in update_data.items():
                setattr(
                    user,
                    key,
                    value,
                )

            user = self.repo.update(user)
            self.db.commit()
            self.db.refresh(user)
            return user
        except IntegrityError as exc:
            self.db.rollback()
            if "uq_users_active_phone" in str(exc) or "active_phone" in str(exc).lower():
                raise ConflictException("Phone number is already in use") from exc
            raise ConflictException("Failed to update user due to a conflict") from exc

    def update_my_profile(
        self,
        tenant_id: int,
        user_id: int,
        data: MyProfileUpdate,
    ) -> User:
        user = self.get_user(
            tenant_id,
            user_id,
        )

        update_data = data.model_dump(
            exclude_unset=True
        )

        if not update_data:
            raise ConflictException(
                "No fields provided for update"
            )

        if "full_name" in update_data:
            full_name = update_data[
                "full_name"
            ].strip()

            if not full_name:
                raise ConflictException(
                    "Full name cannot be empty"
                )

            update_data["full_name"] = full_name

        if "phone" in update_data:
            raw_phone = update_data["phone"]
            if raw_phone:
                canonical_phone = normalize_phone_number(raw_phone)
                update_data["phone"] = canonical_phone
                if canonical_phone != user.phone:
                    existing_phone_user = self.repo.get_active_user_by_phone(canonical_phone)
                    if existing_phone_user and existing_phone_user.id != user.id:
                        raise ConflictException("Phone number is already in use")
            else:
                update_data["phone"] = None

        try:
            for key, value in update_data.items():
                setattr(
                    user,
                    key,
                    value,
                )

            user = self.repo.update(user)
            self.db.commit()
            self.db.refresh(user)
            return user
        except IntegrityError as exc:
            self.db.rollback()
            if "uq_users_active_phone" in str(exc) or "active_phone" in str(exc).lower():
                raise ConflictException("Phone number is already in use") from exc
            raise ConflictException("Failed to update profile due to a conflict") from exc

    def activate_user(
        self,
        tenant_id: int,
        user_id: int,
    ) -> User:
        user = self.repo.get_by_id(
            user_id=user_id,
            tenant_id=tenant_id,
            include_deleted=True,
        )

        if not user:
            raise NotFoundException(
                "User not found"
            )

        if user.is_deleted:
            raise ConflictException(
                "Deleted user cannot be activated"
            )

        if user.is_active:
            raise ConflictException(
                "User is already active"
            )

        # Atomic tenant lock & quota check
        entitlement_svc = SaaSEntitlementService(self.db)
        entitlement_svc.require_limit(
            tenant_id=tenant_id,
            dimension=EntitlementDimension.USERS,
            requested_amount=1,
            lock_tenant=True,
        )

        user.is_active = True
        user = self.repo.update(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def deactivate_user(
        self,
        tenant_id: int,
        user_id: int,
        current_user_id: int,
    ) -> User:
        user = self.get_user(
            tenant_id,
            user_id,
        )

        if user.id == current_user_id:
            raise ConflictException(
                "You cannot deactivate your own account"
            )

        if not user.is_active:
            raise ConflictException(
                "User is already inactive"
            )

        user.is_active = False
        user = self.repo.update(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete_user(
        self,
        tenant_id: int,
        user_id: int,
        current_user_id: int,
    ) -> None:
        user = self.repo.get_by_id(
            user_id=user_id,
            tenant_id=tenant_id,
            include_deleted=True,
        )

        if not user:
            raise NotFoundException(
                "User not found"
            )

        if user.id == current_user_id:
            raise ConflictException(
                "You cannot delete your own account"
            )

        if user.is_deleted:
            raise ConflictException(
                "User is already deleted"
            )

        user.is_deleted = True
        user.is_active = False

        self.repo.update(user)
        self.db.commit()

    def assign_store(
        self,
        tenant_id: int,
        user_id: int,
        store_id: int,
    ) -> User:
        user = self.get_user(
            tenant_id,
            user_id,
        )

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
            raise NotFoundException(
                "Store not found or inactive"
            )

        user.store_id = store.id
        user = self.repo.update(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def remove_store(
        self,
        tenant_id: int,
        user_id: int,
        store_id: Optional[int] = None,
    ) -> tuple[User, int]:
        user = self.get_user(
            tenant_id,
            user_id,
        )

        if user.store_id is None:
            raise ConflictException(
                "User is not currently assigned to any store"
            )

        if store_id is not None and user.store_id != store_id:
            raise ConflictException(
                f"User is assigned to store {user.store_id}, not store {store_id}"
            )

        previous_store_id = user.store_id
        user.store_id = None
        user = self.repo.update(user)
        self.db.commit()
        self.db.refresh(user)
        return user, previous_store_id

    def get_users_by_store(
        self,
        tenant_id: int,
        current_user_store_id: Optional[int] = None,
        store_id: Optional[int] = None,
        role: Optional[str] = None,
        role_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
        include_unassigned: bool = True,
    ):
        from collections import defaultdict
        from sqlalchemy import func, or_
        from sqlalchemy.orm import joinedload
        from app.core.exceptions import ForbiddenException, NotFoundException
        from app.models.role import Role
        from app.models.store import Store
        from app.schemas.user import StoreUserItem, StoreUsersSummary, UsersByStoreResponse

        # Determine effective store filter
        effective_store_id = store_id
        if current_user_store_id is not None:
            if store_id is not None and store_id != current_user_store_id:
                raise ForbiddenException("Access denied to another store")
            effective_store_id = current_user_store_id
            include_unassigned = False

        # 1. Fetch stores belonging to tenant
        store_query = self.db.query(Store).filter(
            Store.tenant_id == tenant_id,
            Store.is_active.is_(True),
        )
        if effective_store_id is not None:
            store_query = store_query.filter(Store.id == effective_store_id)

        stores = store_query.order_by(Store.id.asc()).all()

        if effective_store_id is not None and not stores:
            raise NotFoundException("Store not found or inactive")

        # 2. Fetch non-deleted users belonging to tenant
        user_query = (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(
                User.tenant_id == tenant_id,
                User.is_deleted.is_(False),
            )
        )
        if effective_store_id is not None:
            user_query = user_query.filter(User.store_id == effective_store_id)

        if role_id is not None:
            user_query = user_query.filter(User.role_id == role_id)

        if role is not None and role.strip():
            role_clean = role.strip().lower()
            user_query = user_query.join(User.role).filter(func.lower(Role.name) == role_clean)

        if is_active is not None:
            user_query = user_query.filter(User.is_active.is_(is_active))

        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            user_query = user_query.filter(
                or_(
                    func.lower(User.full_name).like(term),
                    func.lower(User.email).like(term),
                    User.phone.like(term),
                )
            )

        users = user_query.order_by(User.id.asc()).all()

        # 3. Group users by store_id
        users_by_store: dict[Optional[int], list[StoreUserItem]] = defaultdict(list)
        for u in users:
            role_name = u.role.name if u.role else "unknown"
            item = StoreUserItem(
                id=u.id,
                full_name=u.full_name,
                email=u.email,
                phone=u.phone,
                role_id=u.role_id,
                role_name=role_name,
                is_active=u.is_active,
                created_at=u.created_at,
            )
            users_by_store[u.store_id].append(item)

        # 4. Build store summaries
        store_summaries: list[StoreUsersSummary] = []
        total_assigned_count = 0
        for s in stores:
            s_users = users_by_store.get(s.id, [])
            total_assigned_count += len(s_users)
            store_summaries.append(
                StoreUsersSummary(
                    store_id=s.id,
                    store_name=s.name,
                    store_code=s.code,
                    is_main=s.is_main,
                    total_users=len(s_users),
                    users=s_users,
                )
            )

        # 5. Handle unassigned users (Head Office / Store-less)
        if include_unassigned and effective_store_id is None and current_user_store_id is None:
            unassigned_users = users_by_store.get(None, [])
            if unassigned_users or not stores:
                total_assigned_count += len(unassigned_users)
                store_summaries.append(
                    StoreUsersSummary(
                        store_id=None,
                        store_name="Unassigned / Head Office",
                        store_code=None,
                        is_main=False,
                        total_users=len(unassigned_users),
                        users=unassigned_users,
                    )
                )

        return UsersByStoreResponse(
            total_stores=len(stores),
            total_users=total_assigned_count,
            stores=store_summaries,
        )

