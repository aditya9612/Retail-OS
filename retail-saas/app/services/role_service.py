from typing import Optional
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.models.role import Role
from app.models.user import User
from app.repositories.role_repo import RoleRepository
from app.schemas.role import (
    AVAILABLE_PERMISSIONS,
    ModuleMatrixGroup,
    PermissionMatrixRow,
    RoleCreate,
    RoleDeleteResponse,
    RoleDetailResponse,
    RoleMatrixColumn,
    RoleMatrixResponse,
    RoleReassignUsersResponse,
    RoleUpdate,
    RoleUserItem,
    RoleUsersResponse,
)
from app.utils.constants import DEFAULT_ROLE_PERMISSIONS

PROTECTED_CORE_ROLES = {
    "superadmin",
    "admin",
    "owner",
    "manager",
    "cashier",
    "inventory_manager",
    "warehouse_staff",
    "purchase_manager",
    "sales_executive",
    "crm_support",
    "staff",
    "accountant",
}


class RoleService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = RoleRepository(db)

    def list_roles(
        self,
        tenant_id: int,
        search: Optional[str] = None,
        is_system: Optional[bool] = None,
    ) -> list[RoleDetailResponse]:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        roles = self.repo.list_by_tenant(tenant_id)
        if search:
            search_clean = search.strip().lower()
            roles = [r for r in roles if search_clean in (r.name or "").lower()]
        if is_system is not None:
            roles = [r for r in roles if bool(r.is_system) is is_system]

        user_counts = self.repo.count_users_for_roles(tenant_id)

        result: list[RoleDetailResponse] = []
        for role in roles:
            result.append(
                RoleDetailResponse(
                    id=role.id,
                    tenant_id=role.tenant_id,
                    name=role.name,
                    description=getattr(role, "description", None),
                    is_system=role.is_system,
                    permissions=role.permissions or [],
                    user_count=user_counts.get(role.id, 0),
                    created_at=role.created_at,
                )
            )
        return result

    def get_role(self, tenant_id: int, role_id: int) -> RoleDetailResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        role = self.repo.get_by_id(role_id=role_id, tenant_id=tenant_id)
        if not role:
            raise NotFoundException("Role not found")

        user_count = self.repo.count_users_by_role(role_id=role.id, tenant_id=tenant_id)

        return RoleDetailResponse(
            id=role.id,
            tenant_id=role.tenant_id,
            name=role.name,
            description=getattr(role, "description", None),
            is_system=role.is_system,
            permissions=role.permissions or [],
            user_count=user_count,
            created_at=role.created_at,
        )

    def get_role_users(
        self,
        tenant_id: int,
        role_id: int,
        page: int = 1,
        page_size: int = 20,
        store_id: Optional[int] = None,
        current_user_store_id: Optional[int] = None,
    ) -> RoleUsersResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        role = self.repo.get_by_id(role_id=role_id, tenant_id=tenant_id)
        if not role:
            raise NotFoundException("Role not found")

        effective_store_id = store_id
        if current_user_store_id is not None:
            if store_id is not None and store_id != current_user_store_id:
                raise ForbiddenException("Access denied to users of another store")
            effective_store_id = current_user_store_id

        query = self.db.query(User).filter(
            User.tenant_id == tenant_id,
            User.role_id == role_id,
            User.is_deleted.is_(False),
        )
        if effective_store_id is not None:
            query = query.filter(User.store_id == effective_store_id)

        total_users = query.count()
        offset = max(0, (page - 1) * page_size)
        users = query.order_by(User.id.asc()).offset(offset).limit(page_size).all()

        items: list[RoleUserItem] = []
        for u in users:
            items.append(
                RoleUserItem(
                    id=u.id,
                    full_name=u.full_name,
                    email=u.email,
                    phone=u.phone,
                    store_id=u.store_id,
                    store_name=u.store.name if getattr(u, "store", None) else None,
                    is_active=u.is_active,
                    created_at=u.created_at,
                )
            )

        return RoleUsersResponse(
            role_id=role.id,
            role_name=role.name,
            total_users=total_users,
            page=page,
            page_size=page_size,
            users=items,
        )

    def create_role(self, tenant_id: int, data: RoleCreate) -> RoleDetailResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        clean_name = data.name.strip().lower()
        if clean_name in {"superadmin", "owner", "admin"}:
            raise ConflictException(f"Cannot create reserved system role '{clean_name}'")

        existing = self.repo.get_by_name(name=clean_name, tenant_id=tenant_id)
        if existing:
            raise ConflictException(f"Role '{clean_name}' already exists in your organization")

        clean_perms = data.permissions or []

        role = Role(
            tenant_id=tenant_id,
            name=clean_name,
            permissions=clean_perms,
            is_system=False,
        )

        role = self.repo.create(role)
        self.db.commit()
        self.db.refresh(role)

        return RoleDetailResponse(
            id=role.id,
            tenant_id=role.tenant_id,
            name=role.name,
            description=getattr(role, "description", None),
            is_system=role.is_system,
            permissions=role.permissions or [],
            user_count=0,
            created_at=role.created_at,
        )

    def update_role(
        self,
        tenant_id: int,
        role_id: int,
        data: RoleUpdate,
    ) -> RoleDetailResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        role = self.repo.get_by_id(role_id=role_id, tenant_id=tenant_id)
        if not role:
            raise NotFoundException("Role not found")

        if data.name is not None:
            new_name = data.name.strip().lower()
            if role.name in {"owner", "admin"} or role.is_system:
                if new_name != role.name:
                    raise ConflictException("Default administrator role names cannot be renamed")

            if new_name in {"superadmin", "owner", "admin"}:
                raise ConflictException(f"Cannot rename role to reserved system role '{new_name}'")

            if new_name != role.name:
                existing = self.repo.get_by_name(name=new_name, tenant_id=tenant_id)
                if existing and existing.id != role.id:
                    raise ConflictException(f"Role '{new_name}' already exists in your organization")
                role.name = new_name

        if data.permissions is not None:
            role.permissions = data.permissions

        role = self.repo.update(role)
        self.db.commit()
        self.db.refresh(role)

        user_count = self.repo.count_users_by_role(role_id=role.id, tenant_id=tenant_id)

        return RoleDetailResponse(
            id=role.id,
            tenant_id=role.tenant_id,
            name=role.name,
            description=getattr(role, "description", None),
            is_system=role.is_system,
            permissions=role.permissions or [],
            user_count=user_count,
            created_at=role.created_at,
        )

    def reassign_users(
        self,
        tenant_id: int,
        role_id: int,
        target_role_id: int,
    ) -> RoleReassignUsersResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        source_role = self.repo.get_by_id(role_id=role_id, tenant_id=tenant_id)
        if not source_role:
            raise NotFoundException("Source role not found")

        target_role = self.repo.get_by_id(role_id=target_role_id, tenant_id=tenant_id)
        if not target_role:
            raise NotFoundException("Target role not found")

        if source_role.id == target_role.id:
            raise ConflictException("Source and target roles cannot be the same")

        target_name_clean = target_role.name.strip().lower()
        if target_name_clean in {"owner", "superadmin"}:
            raise ForbiddenException("Cannot bulk reassign users to Owner or Superadmin role")

        reassigned_count = (
            self.db.query(User)
            .filter(
                User.tenant_id == tenant_id,
                User.role_id == role_id,
                User.is_deleted.is_(False),
            )
            .update({"role_id": target_role.id}, synchronize_session=False)
        )
        self.db.commit()

        return RoleReassignUsersResponse(
            message=f"Successfully reassigned {reassigned_count} user(s) to role '{target_role.name}'",
            source_role_id=source_role.id,
            source_role_name=source_role.name,
            target_role_id=target_role.id,
            target_role_name=target_role.name,
            reassigned_count=reassigned_count,
        )

    def reset_default_role(
        self,
        tenant_id: int,
        role_id: int,
    ) -> RoleDetailResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        role = self.repo.get_by_id(role_id=role_id, tenant_id=tenant_id)
        if not role:
            raise NotFoundException("Role not found")

        role_name_clean = role.name.strip().lower()
        if role_name_clean not in DEFAULT_ROLE_PERMISSIONS:
            raise ConflictException(
                f"Role '{role.name}' is a custom role and cannot be reset to system defaults"
            )

        default_perms = list(DEFAULT_ROLE_PERMISSIONS[role_name_clean])
        role.permissions = default_perms
        role = self.repo.update(role)
        self.db.commit()
        self.db.refresh(role)

        user_count = self.repo.count_users_by_role(role_id=role.id, tenant_id=tenant_id)

        return RoleDetailResponse(
            id=role.id,
            tenant_id=role.tenant_id,
            name=role.name,
            description=getattr(role, "description", None),
            is_system=role.is_system,
            permissions=role.permissions or [],
            user_count=user_count,
            created_at=role.created_at,
        )

    def get_roles_matrix(
        self,
        tenant_id: int,
    ) -> RoleMatrixResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        roles = self.repo.list_by_tenant(tenant_id)
        columns = [
            RoleMatrixColumn(id=r.id, name=r.name, is_system=bool(r.is_system))
            for r in roles
        ]

        module_groups: list[ModuleMatrixGroup] = []
        for group in AVAILABLE_PERMISSIONS:
            perm_rows: list[PermissionMatrixRow] = []
            for p in group["permissions"]:
                p_code = p["code"]
                role_access: dict[str, bool] = {}
                for r in roles:
                    r_perms = r.permissions or []
                    has_perm = ("*" in r_perms) or (p_code in r_perms)
                    role_access[r.name] = has_perm

                perm_rows.append(
                    PermissionMatrixRow(
                        code=p_code,
                        label=p["label"],
                        description=p["description"],
                        role_access=role_access,
                    )
                )

            module_groups.append(
                ModuleMatrixGroup(
                    module=group["module"],
                    label=group["label"],
                    permissions=perm_rows,
                )
            )

        return RoleMatrixResponse(
            roles=columns,
            modules=module_groups,
        )

    def delete_role(self, tenant_id: int, role_id: int) -> RoleDeleteResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        role = self.repo.get_by_id(role_id=role_id, tenant_id=tenant_id)
        if not role:
            raise NotFoundException("Role not found")

        if role.is_system or role.name in PROTECTED_CORE_ROLES:
            raise ConflictException(f"Default role '{role.name}' is a core system role and cannot be deleted")

        user_count = self.repo.count_users_by_role(role_id=role.id, tenant_id=tenant_id, include_deleted=False)
        if user_count > 0:
            raise ConflictException(
                f"Cannot delete role '{role.name}' because {user_count} user(s) are currently assigned to it. "
                "Please reassign these users to another role before deleting."
            )

        # For any soft-deleted users referencing this role, reassign them to default 'staff' role
        fallback_role = self.repo.get_by_name("staff", tenant_id)
        if fallback_role and fallback_role.id != role_id:
            self.db.query(User).filter(
                User.role_id == role_id,
                User.tenant_id == tenant_id,
            ).update({"role_id": fallback_role.id}, synchronize_session=False)

        role_name = role.name
        self.repo.delete(role)
        self.db.commit()

        return RoleDeleteResponse(
            message=f"Role '{role_name}' deleted successfully",
            deleted_role_id=role_id,
        )

    @staticmethod
    def get_available_permissions() -> list[dict]:
        return AVAILABLE_PERMISSIONS
