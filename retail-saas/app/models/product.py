from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, Numeric, String, Text
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

    gst_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal("18.00")
    )

    selling_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False
    )

    mrp: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00")
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

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    @property
    def price(self) -> Decimal:
        return self.selling_price

    @price.setter
    def price(self, val: Decimal) -> None:
        self.selling_price = val

    @property
    def gst_rate(self) -> Decimal:
        return self.tax_rate

    @gst_rate.setter
    def gst_rate(self, val: Decimal) -> None:
        self.tax_rate = val

    @property
    def variants(self) -> dict | None:
        return getattr(self, "_variants", None)

    @variants.setter
    def variants(self, val: dict | None) -> None:
        self._variants = val

    @property
    def track_batch(self) -> bool:
        return getattr(self, "_track_batch", False)

    @track_batch.setter
    def track_batch(self, val: bool) -> None:
        self._track_batch = bool(val)

    @property
    def track_expiry(self) -> bool:
        return getattr(self, "_track_expiry", False)

    @track_expiry.setter
    def track_expiry(self, val: bool) -> None:
        self._track_expiry = bool(val)

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
        back_populates="product"
    )

    images: Mapped[list["ProductImage"]] = relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete-orphan"
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