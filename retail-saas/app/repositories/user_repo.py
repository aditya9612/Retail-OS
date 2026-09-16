
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
    ) -> Optional[User]:
        query = (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(User.id == user_id)
        )

        if tenant_id is not None:
            query = query.filter(User.tenant_id == tenant_id)

        return query.first()

    def get_by_email(
        self,
        email: str,
        tenant_id: Optional[int] = None,
    ) -> Optional[User]:
        email = email.strip()

        query = (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(
                func.binary(User.email) == func.binary(email)
            )
        )

        if tenant_id is not None:
            query = query.filter(User.tenant_id == tenant_id)

        return query.first()

    def list_users(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 100,
    ):
        return (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(User.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

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
            .filter(User.tenant_id == tenant_id)
            .count()
        )
