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

    source_store = relationship("Store", foreign_keys=[source_store_id])
    destination_store = relationship("Store", foreign_keys=[destination_store_id])
    approver = relationship("User", foreign_keys=[approved_by])

    @property
    def source_store_name(self):
        return self.source_store.name if self.source_store else None

    @property
    def destination_store_name(self):
        return self.destination_store.name if self.destination_store else None

    @property
    def approved_by_name(self):
        return self.approver.full_name if self.approver else None

    @property
    def total_items(self) -> int:
        return len(self.items) if self.items else 0

    @property
    def total_quantity(self) -> int:
        if not self.items:
            return 0
        return int(sum(item.quantity for item in self.items))