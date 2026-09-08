from datetime import datetime

from sqlalchemy import Column, Integer, Numeric, String, DateTime, ForeignKey

from app.core.database import Base


class StoreTarget(Base):
    __tablename__ = "store_targets"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True
    )

    store_id = Column(
        Integer,
        ForeignKey("stores.id"),
        nullable=False,
        index=True
    )

    target_type = Column(
        String(30),
        nullable=False
    )

    target_value = Column(
        Numeric(12, 2),
        nullable=False
    )

    period = Column(
        String(20),
        nullable=False
    )

    start_date = Column(
        DateTime,
        nullable=False
    )

    end_date = Column(
        DateTime,
        nullable=False
    )

    status = Column(
        String(20),
        nullable=False,
        default="active"
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )