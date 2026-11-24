from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.user import User


class RoleRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, role: Role) -> Role:
        self.db.add(role)
        self.db.flush()
        return role

    def get_by_id(
        self,
        role_id: int,
        tenant_id: Optional[int] = None,
    ) -> Optional[Role]:
        query = self.db.query(Role).filter(Role.id == role_id)
        if tenant_id is not None:
            query = query.filter(
                (Role.tenant_id == tenant_id)
                | (Role.tenant_id.is_(None) & (Role.is_system == True))
            )
        return query.first()

    def get_by_name(
        self,
        name: str,
        tenant_id: int,
    ) -> Optional[Role]:
        name_clean = name.strip().lower()
        roles = (
            self.db.query(Role)
            .filter(
                func.lower(Role.name) == name_clean,
                (Role.tenant_id == tenant_id)
                | (Role.tenant_id.is_(None) & (Role.is_system == True)),
            )
            .order_by(Role.tenant_id.desc().nullslast())
            .all()
        )
        return roles[0] if roles else None

    def get_by_id_or_name(
        self,
        identifier: int | str,
        tenant_id: int,
    ) -> Optional[Role]:
        if isinstance(identifier, int):
            return self.get_by_id(identifier, tenant_id)
        ident_str = str(identifier).strip()
        if ident_str.isdigit():
            role = self.get_by_id(int(ident_str), tenant_id)
            if role:
                return role
        return self.get_by_name(ident_str, tenant_id)

    def list_by_tenant(
        self,
        tenant_id: int,
    ) -> list[Role]:
        roles = (
            self.db.query(Role)
            .filter(
                (Role.tenant_id == tenant_id)
                | (Role.tenant_id.is_(None) & (Role.is_system == True))
            )
            .order_by(Role.id.asc())
            .all()
        )
        # Deduplicate by role name (case-insensitive), giving priority to tenant-specific roles
        seen_names: set[str] = set()
        deduped: list[Role] = []
        # Sort tenant-specific first so they take precedence over global roles with same name
        sorted_roles = sorted(roles, key=lambda r: 0 if r.tenant_id == tenant_id else 1)
        for r in sorted_roles:
            r_name = (r.name or "").lower()
            if r_name not in seen_names:
                seen_names.add(r_name)
                deduped.append(r)
        deduped.sort(key=lambda r: r.id)
        return deduped

    def count_users_by_role(
        self,
        role_id: int,
        tenant_id: int,
        include_deleted: bool = False,
    ) -> int:
        query = self.db.query(func.count(User.id)).filter(
            User.role_id == role_id,
            User.tenant_id == tenant_id,
        )
        if not include_deleted:
            query = query.filter(User.is_deleted.is_(False))
        return query.scalar() or 0

    def count_users_for_roles(
        self,
        tenant_id: int,
    ) -> dict[int, int]:
        counts = (
            self.db.query(User.role_id, func.count(User.id))
            .filter(
                User.tenant_id == tenant_id,
                User.is_deleted.is_(False),
            )
            .group_by(User.role_id)
            .all()
        )
        return {role_id: count for role_id, count in counts}

    def update(self, role: Role) -> Role:
        self.db.add(role)
        self.db.flush()
        return role

    def delete(self, role: Role) -> None:
        self.db.delete(role)
        self.db.flush()
