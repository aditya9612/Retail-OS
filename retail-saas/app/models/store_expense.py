from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class StoreExpense(Base):
    __tablename__ = "store_expenses"

    id = Column(Integer, primary_key=True, index=True)

    store_id = Column(
        Integer,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    amount = Column(
        Numeric(12, 2),
        nullable=False,
    )

    category = Column(
        String(100),
        nullable=False,
        index=True,
    )

    description = Column(
        Text,
        nullable=True,
    )

    expense_date = Column(
        Date,
        nullable=False,
        index=True,
    )

    payment_method = Column(
        String(50),
        nullable=True,
    )

    reference_number = Column(
        String(100),
        nullable=True,
        index=True,
    )

    status = Column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
    )

    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    store = relationship(
        "Store",
        back_populates="expenses",
    )

    creator = relationship(
        "User",
        foreign_keys=[created_by],
    )