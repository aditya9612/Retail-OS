from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.tenant import Tenant


class ProductVariant(Base, TimestampMixin):
    __tablename__ = "product_variants"
    __table_args__ = (
        Index("ix_product_variants_tenant_sku", "tenant_id", "sku", unique=True),
        Index("ix_product_variants_tenant_barcode", "tenant_id", "barcode"),
        Index("ix_product_variants_product_active", "product_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    variant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    attributes: Mapped[Dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    selling_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="variant_list")
    tenant: Mapped["Tenant"] = relationship("Tenant")

    @property
    def effective_selling_price(self) -> Decimal:
        if self.selling_price is not None:
            return self.selling_price
        if self.product and getattr(self.product, "selling_price", None) is not None:
            return self.product.selling_price
        return Decimal("0.00")

    @property
    def effective_cost_price(self) -> Decimal:
        if self.cost_price is not None:
            return self.cost_price
        if self.product and getattr(self.product, "cost_price", None) is not None:
            return self.product.cost_price
        return Decimal("0.00")
