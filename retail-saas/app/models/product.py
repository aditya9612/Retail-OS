from datetime import date
from decimal import Decimal
from typing import Any, TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.models.product_variant import ProductVariant


from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_tenant_entitlement", "tenant_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id")
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    sku: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )

    barcode: Mapped[str | None] = mapped_column(
        String(100),
        index=True
    )

    description: Mapped[str | None] = mapped_column(
        Text
    )

    brand: Mapped[str | None] = mapped_column(
        String(100)
    )

    hsn_code: Mapped[str | None] = mapped_column(
        String(20)
    )

    selling_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False
    )

    cost_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal("0.00"),
        nullable=False
    )

    min_stock_alert: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False
    )

    stock_status: Mapped[str] = mapped_column(
        String(20),
        default="in_stock",
        nullable=False
    )

    unit: Mapped[str] = mapped_column(
        String(20),
        default="pcs",
        nullable=False
    )

    mrp: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    track_batch: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    track_expiry: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    batch_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    @property
    def price(self) -> Decimal:
        return self.selling_price

    @price.setter
    def price(self, val: Decimal | None) -> None:
        if val is not None:
            self.selling_price = val

    @property
    def gst_rate(self) -> Decimal:
        return self.tax_rate

    @gst_rate.setter
    def gst_rate(self, val: Decimal | None) -> None:
        if val is not None:
            self.tax_rate = val

    @property
    def variants(self) -> Any:
        explicit_variants = getattr(self, "_variants", None)
        if explicit_variants is not None:
            return explicit_variants
        if hasattr(self, "variant_list") and self.variant_list:
            return [
                {
                    "id": v.id,
                    "variant_name": v.variant_name,
                    "sku": v.sku,
                    "barcode": v.barcode,
                    "size": v.size,
                    "color": v.color,
                    "selling_price": str(v.selling_price) if v.selling_price is not None else str(self.selling_price),
                    "cost_price": str(v.cost_price) if v.cost_price is not None else str(self.cost_price),
                    "is_active": v.is_active,
                }
                for v in self.variant_list
            ]
        return None

    @variants.setter
    def variants(self, val: Any) -> None:
        self._variants = val

    @property
    def image_url(self) -> str | None:
        if self.images:
            return self.images[0].image_url
        return getattr(self, "_image_url", None)

    @image_url.setter
    def image_url(self, val: str | None) -> None:
        self._image_url = val

    category: Mapped["Category | None"] = relationship(
        "Category",
        back_populates="products"
    )

    inventory_items: Mapped[list["Inventory"]] = relationship(
        "Inventory",
        back_populates="product",
        cascade="all, delete-orphan"
    )

    images: Mapped[list["ProductImage"]] = relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete-orphan"
    )

    variant_list: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
    )


class ProductImage(Base, TimestampMixin):
    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    image_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="images"
    )