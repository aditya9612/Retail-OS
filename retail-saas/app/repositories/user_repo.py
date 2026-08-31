from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
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
        query = (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(User.email == email.strip().lower())
        )

        if tenant_id is not None:
            query = query.filter(User.tenant_id == tenant_id)

        return query.first()

    def list_users(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        include_inactive: bool = False,
    ) -> list[User]:
        query = (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(User.tenant_id == tenant_id)
        )

        if not include_inactive:
            query = query.filter(User.is_active.is_(True))

        return (
            query
            .order_by(User.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(self, user: User) -> User:
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, user: User) -> None:
        user.is_active = False
        self.db.commit()

    def count(
        self,
        tenant_id: int,
        include_inactive: bool = False,
    ) -> int:
        query = self.db.query(User).filter(
            User.tenant_id == tenant_id
        )

        if not include_inactive:
            query = query.filter(User.is_active.is_(True))

        return query.count()