from sqlalchemy import Column, Integer, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from app.core.database import Base


class StoreTransferItem(Base):
    __tablename__ = "store_transfer_items"

    id = Column(Integer, primary_key=True)

    transfer_id = Column(
      
        Integer,
        ForeignKey("store_transfers.id"),
        nullable=False
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False
    )

    quantity = Column(
        Numeric(12, 2),
        nullable=False
    )

    transfer = relationship(
        "StoreTransfer",
        back_populates="items"
    )

    product = relationship("Product", foreign_keys=[product_id])

    @property
    def product_name(self):
        return self.product.name if self.product else None

    @property
    def sku(self):
        return self.product.sku if self.product else None