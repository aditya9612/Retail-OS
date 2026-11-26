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
from app.utils.constants import DEFAULT_ROLE_PERMISSIONS, DEFAULT_ROLE_DESCRIPTIONS

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
    "customer",
}


class RoleService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = RoleRepository(db)

    def list_roles(
        self,
        tenant_id: int,
        search: Optional[str] = None,
        name: Optional[str] = None,
        is_system: Optional[bool] = None,
        role_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[RoleDetailResponse]:
        if tenant_id is None:
            # Superadmin or unassigned tenant: query all system or tenant roles
            roles = (
                self.db.query(Role)
                .order_by(Role.id.asc())
                .all()
            )
        else:
            roles = self.repo.list_by_tenant(tenant_id)

        if role_id is not None:
            roles = [r for r in roles if r.id == role_id]

        if name is not None:
            name_clean = name.strip().lower()
            roles = [r for r in roles if (r.name or "").strip().lower() == name_clean]

        if search:
            search_clean = search.strip().lower()
            if search_clean.isdigit():
                s_id = int(search_clean)
                roles = [
                    r for r in roles
                    if r.id == s_id or search_clean in (r.name or "").lower()
                ]
            else:
                roles = [r for r in roles if search_clean in (r.name or "").lower()]

        if is_system is not None:
            roles = [
                r for r in roles
                if bool(r.is_system or (r.name or "").lower() in PROTECTED_CORE_ROLES) is is_system
            ]

        user_counts = self.repo.count_users_for_roles(tenant_id) if tenant_id else {}

        # Apply pagination
        paginated_roles = roles[skip : skip + limit]

        result: list[RoleDetailResponse] = []
        for role in paginated_roles:
            role_name_clean = (role.name or "").lower()
            is_core_sys = bool(role.is_system or role_name_clean in PROTECTED_CORE_ROLES)
            desc = getattr(role, "description", None) or DEFAULT_ROLE_DESCRIPTIONS.get(role_name_clean, None)
            result.append(
                RoleDetailResponse(
                    id=role.id,
                    tenant_id=role.tenant_id,
                    name=role.name,
                    description=desc,
                    is_system=is_core_sys,
                    permissions=role.permissions or [],
                    user_count=user_counts.get(role.id, 0),
                    created_at=role.created_at,
                )
            )
        return result

    def list_roles_with_counts(
        self,
        tenant_id: int,
        search: Optional[str] = None,
        name: Optional[str] = None,
        is_system: Optional[bool] = None,
        role_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> dict:
        from app.utils.pagination import compute_total_pages
        all_roles = self.repo.list_by_tenant(tenant_id) if tenant_id is not None else self.db.query(Role).order_by(Role.id.asc()).all()
        system_count = sum(1 for r in all_roles if bool(r.is_system or (r.name or "").lower() in PROTECTED_CORE_ROLES))
        total_all = len(all_roles)
        counts = {
            "total": total_all,
            "system_roles": system_count,
            "custom_roles": max(0, total_all - system_count),
        }

        filtered_all = self.list_roles(
            tenant_id=tenant_id,
            search=search,
            name=name,
            is_system=is_system,
            role_id=role_id,
            skip=0,
            limit=max(total_all, 1),
        )
        total = len(filtered_all)
        items = filtered_all[skip : skip + limit]
        page = (skip // limit) + 1 if limit > 0 else 1
        return {
            "success": True,
            "message": "Roles retrieved successfully" if items else "No roles found",
            "items": items,
            "total": total,
            "page": page,
            "page_size": limit,
            "total_pages": compute_total_pages(total, limit),
            "counts": counts,
        }

    def get_role(self, tenant_id: int, role_id: int | str) -> RoleDetailResponse:
        role = self.repo.get_by_id_or_name(role_id, tenant_id)
        if not role:
            raise NotFoundException(f"Role '{role_id}' not found")

        user_count = self.repo.count_users_by_role(role_id=role.id, tenant_id=tenant_id) if tenant_id else 0

        role_name_clean = (role.name or "").lower()
        is_core_sys = bool(role.is_system or role_name_clean in PROTECTED_CORE_ROLES)
        desc = getattr(role, "description", None) or DEFAULT_ROLE_DESCRIPTIONS.get(role_name_clean, None)

        return RoleDetailResponse(
            id=role.id,
            tenant_id=role.tenant_id,
            name=role.name,
            description=desc,
            is_system=is_core_sys,
            permissions=role.permissions or [],
            user_count=user_count,
            created_at=role.created_at,
        )

    def get_role_users(
        self,
        tenant_id: int,
        role_id: int | str,
        page: int = 1,
        page_size: int = 20,
        store_id: Optional[str | int] = None,
        is_active: Optional[bool] = None,
        current_user_store_id: Optional[int] = None,
    ) -> RoleUsersResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        role = self.repo.get_by_id_or_name(role_id, tenant_id)
        if not role:
            raise NotFoundException(f"Role '{role_id}' not found")

        from sqlalchemy.orm import joinedload
        query = (
            self.db.query(User)
            .options(joinedload(User.store))
            .filter(
                User.tenant_id == tenant_id,
                User.role_id == role.id,
                User.is_deleted.is_(False),
            )
        )

        effective_store_filter: Optional[str] = None
        if current_user_store_id is not None:
            if store_id is not None and str(store_id).strip() != str(current_user_store_id):
                raise ForbiddenException("Access denied to users of another store")
            effective_store_filter = str(current_user_store_id)
        elif store_id is not None:
            effective_store_filter = str(store_id).strip()

        if effective_store_filter is not None:
            clean_store = effective_store_filter.lower()
            if clean_store in ("null", "none", "unassigned", "0"):
                query = query.filter(User.store_id.is_(None))
            elif clean_store.isdigit():
                query = query.filter(User.store_id == int(clean_store))
            else:
                from app.models.store import Store
                query = query.join(User.store).filter(func.lower(Store.name) == clean_store)

        if is_active is not None:
            query = query.filter(User.is_active == is_active)

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
            description=data.description,
            permissions=clean_perms,
            is_system=False,
        )

        try:
            role = self.repo.create(role)
            self.db.commit()
            self.db.refresh(role)
        except Exception as exc:
            self.db.rollback()
            exc_str = str(exc).lower()
            if "unknown column 'description'" in exc_str or "no such column: description" in exc_str:
                role = Role(
                    tenant_id=tenant_id,
                    name=clean_name,
                    permissions=clean_perms,
                    is_system=False,
                )
                role = self.repo.create(role)
                self.db.commit()
                self.db.refresh(role)
            else:
                raise ConflictException(f"Failed to create role: {exc}") from exc

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
        role_id: int | str,
        data: RoleUpdate,
    ) -> RoleDetailResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        role = self.repo.get_by_id_or_name(role_id, tenant_id)
        if not role:
            raise NotFoundException(f"Role '{role_id}' not found")

        role_name_clean = (role.name or "").lower()

        if data.name is not None:
            new_name = data.name.strip().lower()
            if role_name_clean in {"owner", "admin"} or role.is_system:
                if new_name != role_name_clean:
                    raise ConflictException("Default administrator and system role names cannot be renamed")

            if new_name in {"superadmin", "owner", "admin"}:
                raise ConflictException(f"Cannot rename role to reserved system role '{new_name}'")

            if new_name != role_name_clean:
                existing = self.repo.get_by_name(name=new_name, tenant_id=tenant_id)
                if existing and existing.id != role.id:
                    raise ConflictException(f"Role '{new_name}' already exists in your organization")
                role.name = new_name

        if data.permissions is not None:
            if role_name_clean in {"owner", "superadmin"} and len(data.permissions) == 0:
                raise ForbiddenException("Cannot remove all permissions from Owner or Superadmin role")
            role.permissions = data.permissions

        desc_updated = False
        if data.description is not None:
            desc_updated = True
            role.description = data.description

        try:
            role = self.repo.update(role)
            self.db.commit()
            self.db.refresh(role)
        except Exception as exc:
            self.db.rollback()
            exc_str = str(exc).lower()
            if desc_updated and ("unknown column 'description'" in exc_str or "no such column: description" in exc_str):
                # Retry commit without modifying description column
                role = self.repo.get_by_id(role.id, tenant_id)
                if data.name is not None:
                    role.name = data.name.strip().lower()
                if data.permissions is not None:
                    role.permissions = data.permissions
                role = self.repo.update(role)
                self.db.commit()
                self.db.refresh(role)
            else:
                raise ConflictException(f"Failed to update role: {exc}") from exc

        user_count = self.repo.count_users_by_role(role_id=role.id, tenant_id=tenant_id)

        return RoleDetailResponse(
            id=role.id,
            tenant_id=role.tenant_id,
            name=role.name,
            description=getattr(role, "description", None) or DEFAULT_ROLE_DESCRIPTIONS.get(role_name_clean, None),
            is_system=bool(role.is_system or role_name_clean in PROTECTED_CORE_ROLES),
            permissions=role.permissions or [],
            user_count=user_count,
            created_at=role.created_at,
        )

    def reassign_users(
        self,
        tenant_id: int,
        role_id: int | str,
        target_role_id: int | str,
    ) -> RoleReassignUsersResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        source_role = self.repo.get_by_id_or_name(role_id, tenant_id)
        if not source_role:
            raise NotFoundException(f"Source role '{role_id}' not found")

        target_role = self.repo.get_by_id_or_name(target_role_id, tenant_id)
        if not target_role:
            raise NotFoundException(f"Target role '{target_role_id}' not found")

        if source_role.id == target_role.id:
            raise ConflictException("Source and target roles cannot be the same")

        source_name_clean = source_role.name.strip().lower()
        if source_name_clean in {"owner", "superadmin"}:
            raise ForbiddenException("Cannot bulk reassign users from Owner or Superadmin role")

        target_name_clean = target_role.name.strip().lower()
        if target_name_clean in {"owner", "superadmin"}:
            raise ForbiddenException("Cannot bulk reassign users to Owner or Superadmin role")

        try:
            reassigned_count = (
                self.db.query(User)
                .filter(
                    User.tenant_id == tenant_id,
                    User.role_id == source_role.id,
                    User.is_deleted.is_(False),
                )
                .update({"role_id": target_role.id}, synchronize_session=False)
            )
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise ConflictException(f"Failed to reassign users: {exc}") from exc

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
        role_id: int | str,
    ) -> RoleDetailResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        role = self.repo.get_by_id_or_name(role_id, tenant_id)
        if not role:
            raise NotFoundException(f"Role '{role_id}' not found")

        role_name_clean = role.name.strip().lower()
        if role_name_clean not in DEFAULT_ROLE_PERMISSIONS:
            raise ConflictException(
                f"Role '{role.name}' is a custom role and cannot be reset to system defaults"
            )

        default_perms = list(DEFAULT_ROLE_PERMISSIONS[role_name_clean])
        role.permissions = default_perms
        role.is_system = True
        desc = DEFAULT_ROLE_DESCRIPTIONS.get(role_name_clean, getattr(role, "description", None))
        try:
            if hasattr(role, "description"):
                role.description = desc
            role = self.repo.update(role)
            self.db.commit()
            self.db.refresh(role)
        except Exception as exc:
            self.db.rollback()
            exc_str = str(exc).lower()
            if "unknown column 'description'" in exc_str or "no such column: description" in exc_str:
                role = self.repo.get_by_id(role.id, tenant_id)
                role.permissions = default_perms
                role.is_system = True
                role = self.repo.update(role)
                self.db.commit()
                self.db.refresh(role)
            else:
                raise ConflictException(f"Failed to reset role: {exc}") from exc

        user_count = self.repo.count_users_by_role(role_id=role.id, tenant_id=tenant_id)

        return RoleDetailResponse(
            id=role.id,
            tenant_id=role.tenant_id,
            name=role.name,
            description=desc,
            is_system=True,
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
            RoleMatrixColumn(
                id=r.id,
                name=r.name,
                is_system=bool(r.is_system or (r.name or "").lower() in PROTECTED_CORE_ROLES),
            )
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

    def delete_role(self, tenant_id: int, role_id: int | str) -> RoleDeleteResponse:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        role = self.repo.get_by_id_or_name(role_id, tenant_id)
        if not role:
            raise NotFoundException(f"Role '{role_id}' not found")

        role_name_clean = (role.name or "").lower()
        if role.is_system or role_name_clean in PROTECTED_CORE_ROLES:
            raise ConflictException(f"Default role '{role.name}' is a core system role and cannot be deleted")

        user_count = self.repo.count_users_by_role(role_id=role.id, tenant_id=tenant_id, include_deleted=False)
        if user_count > 0:
            raise ConflictException(
                f"Cannot delete role '{role.name}' because {user_count} user(s) are currently assigned to it. "
                "Please reassign these users to another role before deleting."
            )

        # For any soft-deleted users referencing this role, reassign them to a safe fallback role
        fallback_role = self.repo.get_by_name("staff", tenant_id)
        if not fallback_role or fallback_role.id == role.id:
            all_tenant_roles = self.repo.list_by_tenant(tenant_id)
            for r in all_tenant_roles:
                if r.id != role.id and (r.name or "").lower() not in {"owner", "superadmin"}:
                    fallback_role = r
                    break

        try:
            if fallback_role and fallback_role.id != role.id:
                self.db.query(User).filter(
                    User.role_id == role.id,
                    User.tenant_id == tenant_id,
                ).update({"role_id": fallback_role.id}, synchronize_session=False)

            role_name = role.name
            del_id = role.id
            self.repo.delete(role)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise ConflictException(f"Failed to delete role: {exc}") from exc

        return RoleDeleteResponse(
            message=f"Role '{role_name}' deleted successfully",
            deleted_role_id=del_id,
        )

    @staticmethod
    def get_available_permissions(module: Optional[str] = None) -> list[dict]:
        if module:
            clean_mod = module.strip().lower()
            return [g for g in AVAILABLE_PERMISSIONS if g["module"].lower() == clean_mod]
        return AVAILABLE_PERMISSIONS

    @staticmethod
    def get_simple_permissions_map(module: Optional[str] = None) -> dict[str, list[str]]:
        groups = AVAILABLE_PERMISSIONS
        if module:
            clean_mod = module.strip().lower()
            groups = [g for g in AVAILABLE_PERMISSIONS if g["module"].lower() == clean_mod]
        return {
            group["module"]: [p["code"] for p in group["permissions"]]
            for group in groups
        }
