from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def get_by_id(
        self,
        user_id: int,
        tenant_id: Optional[int] = None,
        include_deleted: bool = False,
    ) -> Optional[User]:
        query = (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(User.id == user_id)
        )

        if tenant_id is not None:
            query = query.filter(User.tenant_id == tenant_id)

        if not include_deleted:
            query = query.filter(User.is_deleted.is_(False))

        return query.first()

    def get_by_email(
        self,
        email: str,
        tenant_id: Optional[int] = None,
        include_deleted: bool = False,
    ) -> Optional[User]:
        email = email.strip().lower()

        query = (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(func.lower(User.email) == email)
        )

        if tenant_id is not None:
            query = query.filter(User.tenant_id == tenant_id)

        if not include_deleted:
            query = query.filter(User.is_deleted.is_(False))

        return query.first()

    def list_users(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 100,
        include_inactive: bool = False,
    ) -> list[User]:
        query = (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(
                User.tenant_id == tenant_id,
                User.is_deleted.is_(False),
            )
        )

        if not include_inactive:
            query = query.filter(
                User.is_active.is_(True)
            )

        users = (
            query
            .order_by(User.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        for user in users:
            if user.role is not None:
                if user.role.permissions is None:
                    user.role.permissions = []

        return users

    def update(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def delete(self, user: User) -> None:
        self.db.delete(user)
        self.db.flush()

    def count(self, tenant_id: int) -> int:
        return (
            self.db.query(User)
            .filter(
                User.tenant_id == tenant_id,
                User.is_deleted.is_(False),
            )
            .count()
        )