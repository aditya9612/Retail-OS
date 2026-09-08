from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime


class StoreTransfer(Base):
    __tablename__ = "store_transfers"

    id = Column(Integer, primary_key=True)

    transfer_number = Column(
        String(100),
        unique=True,
        nullable=False
    )

    source_store_id = Column(
        Integer,
        ForeignKey("stores.id"),
        nullable=False
    )

    destination_store_id = Column(
        Integer,
        ForeignKey("stores.id"),
        nullable=False
    )

    status = Column(
        String(20),
        default="Draft",
        nullable=False
    )

    approved_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    items = relationship(
        "StoreTransferItem",
        back_populates="transfer",
        cascade="all, delete-orphan"
    )