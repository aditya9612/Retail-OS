from typing import Optional
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.role import Role
from app.repositories.role_repo import RoleRepository
from app.schemas.role import (
    AVAILABLE_PERMISSIONS,
    RoleCreate,
    RoleDetailResponse,
    RoleUpdate,
)

PROTECTED_CORE_ROLES = {"superadmin", "admin", "owner", "manager", "staff"}


class RoleService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = RoleRepository(db)

    def list_roles(self, tenant_id: int) -> list[RoleDetailResponse]:
        if tenant_id is None:
            raise ConflictException("Tenant ID is required")

        roles = self.repo.list_by_tenant(tenant_id)
        user_counts = self.repo.count_users_for_roles(tenant_id)

        result: list[RoleDetailResponse] = []
        for role in roles:
            result.append(
                RoleDetailResponse(
                    id=role.id,
                    tenant_id=role.tenant_id,
                    name=role.name,
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
            is_system=role.is_system,
            permissions=role.permissions or [],
            user_count=user_count,
            created_at=role.created_at,
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
            is_system=role.is_system,
            permissions=role.permissions or [],
            user_count=user_count,
            created_at=role.created_at,
        )

    def delete_role(self, tenant_id: int, role_id: int) -> dict:
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
        from app.models.user import User

        fallback_role = self.repo.get_by_name("staff", tenant_id)
        if fallback_role and fallback_role.id != role_id:
            self.db.query(User).filter(
                User.role_id == role_id,
                User.tenant_id == tenant_id,
            ).update({"role_id": fallback_role.id}, synchronize_session=False)

        role_name = role.name
        self.repo.delete(role)
        self.db.commit()

        return {"message": f"Role '{role_name}' deleted successfully", "deleted_role_id": role_id}

    @staticmethod
    def get_available_permissions() -> list[dict]:
        return AVAILABLE_PERMISSIONS
