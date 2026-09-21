from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base


class Staff(Base):

    __tablename__ = "staff"

    id = Column(Integer, primary_key=True)

    name = Column(String(100), nullable=False)

    email = Column(
        String(100),
        unique=True,
        nullable=False
    )

    phone = Column(String(20))

    role_id = Column(
        Integer,
        ForeignKey("roles.id"),
        nullable=True
    )

    store_id = Column(
        Integer,
        ForeignKey("stores.id"),
        nullable=True
    )

    is_active = Column(
        Boolean,
        default=True
    )

    role_rel = relationship(
        "Role",
        foreign_keys=[role_id],
        lazy="joined"
    )

    @property
    def role(self) -> str:
        if self.role_rel and hasattr(self.role_rel, "name") and self.role_rel.name:
            return self.role_rel.name
        return "staff"

    @role.setter
    def role(self, value: str) -> None:
        pass