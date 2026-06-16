from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int, tenant_id: int) -> Optional[User]:
        return (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(User.id == user_id, User.tenant_id == tenant_id)
            .first()
        )

    def get_by_email(self, email: str, tenant_id: Optional[int] = None) -> Optional[User]:
        query = self.db.query(User).options(joinedload(User.role)).filter(User.email == email)
        if tenant_id:
            query = query.filter(User.tenant_id == tenant_id)
        return query.first()

    def list_users(self, tenant_id: int, skip: int = 0, limit: int = 20) -> List[User]:
        return (
            self.db.query(User)
            .options(joinedload(User.role))
            .filter(User.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update(self, user: User) -> User:
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, user: User) -> None:
        self.db.delete(user)
        self.db.commit()
