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
            query = query.filter(Role.tenant_id == tenant_id)
        return query.first()

    def get_by_name(
        self,
        name: str,
        tenant_id: int,
    ) -> Optional[Role]:
        name_clean = name.strip().lower()
        return (
            self.db.query(Role)
            .filter(
                func.lower(Role.name) == name_clean,
                Role.tenant_id == tenant_id,
            )
            .first()
        )

    def list_by_tenant(
        self,
        tenant_id: int,
    ) -> list[Role]:
        return (
            self.db.query(Role)
            .filter(Role.tenant_id == tenant_id)
            .order_by(Role.id.asc())
            .all()
        )

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
