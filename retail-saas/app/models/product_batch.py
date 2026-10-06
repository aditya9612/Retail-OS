from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Date, ForeignKey, Index, Integer, Numeric, String, Boolean, CheckConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base, TimestampMixin


class ProductBatch(Base, TimestampMixin):
    __tablename__ = "product_batches"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    store_id = Column(Integer, nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True, index=True)

    batch_number = Column(String(64), nullable=False)
    manufacturing_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)

    unit_cost = Column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    quantity = Column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    remaining_quantity = Column(Numeric(12, 4), nullable=False, default=Decimal("0"))

    is_active = Column(Boolean, nullable=False, default=True)

    # relationships (lazy loaded)
    product = relationship("Product", lazy="joined")
    variant = relationship("ProductVariant", lazy="joined", uselist=False)

    __table_args__ = (
        # MySQL‑compatible unique indexes – NULL variant_id counts as distinct, so we need two indexes
        Index(
            "uq_product_batches_variant",
            "tenant_id",
            "store_id",
            "product_id",
            "variant_id",
            "batch_number",
            unique=True,
        ),
        Index(
            "uq_product_batches_product",
            "tenant_id",
            "store_id",
            "product_id",
            "batch_number",
            unique=True,
        ),
        # Business constraints
        CheckConstraint("quantity >= 0", name="ck_batch_quantity_nonneg"),
        CheckConstraint("remaining_quantity >= 0", name="ck_batch_remaining_nonneg"),
        CheckConstraint("remaining_quantity <= quantity", name="ck_batch_remaining_le_quantity"),
        # FIFO and FEFO allocation query indexes
        Index(
            "ix_batch_fifo",
            "tenant_id",
            "store_id",
            "product_id",
            "is_active",
            "created_at",
            "id",
        ),
        Index(
            "ix_batch_fefo",
            "tenant_id",
            "store_id",
            "product_id",
            "is_active",
            "expiry_date",
            "created_at",
        ),
    )

    @property
    def status(self) -> str:
        """Derived status – never persisted.

        Rules:
        * INACTIVE – if ``is_active`` is False
        * DEPLETED – remaining_quantity <= 0
        * EXPIRED – expiry_date exists and is before today
        * ACTIVE – otherwise
        """
        if not self.is_active:
            return "INACTIVE"
        if self.remaining_quantity <= 0:
            return "DEPLETED"
        if self.expiry_date and self.expiry_date < date.today():
            return "EXPIRED"
        return "ACTIVE"
