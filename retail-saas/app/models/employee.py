from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from app.core.database import Base


class Employee(Base):

    __tablename__ = "employees"

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
        ForeignKey("roles.id")
    )

    store_id = Column(
        Integer,
        ForeignKey("stores.id")
    )

    is_active = Column(
        Boolean,
        default=True
    )