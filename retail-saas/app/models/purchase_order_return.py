from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class PurchaseOrderReturn(Base, TimestampMixin):
    __tablename__ = "purchase_order_returns"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    return_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    debit_note_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id"),
        nullable=False,
        index=True,
    )

    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id"),
        nullable=True,
        index=True,
    )

    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id"),
        nullable=True,
        index=True,
    )

    warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.id"),
        nullable=True,
        index=True,
    )

    reason: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    remarks: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="requested",
        index=True,
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    rejected_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    purchase_order = relationship(
        "PurchaseOrder",
        lazy="joined",
    )

    supplier = relationship(
        "Supplier",
        lazy="joined",
    )

    store = relationship(
        "Store",
        lazy="joined",
    )

    warehouse = relationship(
        "Warehouse",
        lazy="joined",
    )

    created_by = relationship(
        "User",
        foreign_keys=[created_by_id],
        lazy="joined",
    )

    approved_by = relationship(
        "User",
        foreign_keys=[approved_by_id],
        lazy="joined",
    )

    items = relationship(
        "PurchaseOrderReturnItem",
        back_populates="purchase_order_return",
        cascade="all, delete-orphan",
        lazy="joined",
    )

    @property
    def purchase_order_number(self) -> str | None:
        return self.purchase_order.order_number if getattr(self, "purchase_order", None) else None

    @property
    def supplier_name(self) -> str | None:
        if getattr(self, "supplier", None) and self.supplier:
            return self.supplier.name
        if getattr(self, "purchase_order", None) and getattr(self.purchase_order, "supplier", None):
            return self.purchase_order.supplier.name
        return None

    @property
    def store_name(self) -> str | None:
        return self.store.name if getattr(self, "store", None) and self.store else None

    @property
    def warehouse_name(self) -> str | None:
        return self.warehouse.name if getattr(self, "warehouse", None) and self.warehouse else None


class PurchaseOrderReturnItem(Base, TimestampMixin):
    __tablename__ = "purchase_order_return_items"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    purchase_order_return_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_order_returns.id"),
        nullable=False,
        index=True,
    )

    purchase_order_item_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_order_items.id"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    batch_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    item_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    purchase_order_return = relationship(
        "PurchaseOrderReturn",
        back_populates="items",
    )

    purchase_order_item = relationship(
        "PurchaseOrderItem",
        lazy="joined",
    )

    product = relationship(
        "Product",
        lazy="joined",
    )

    @property
    def product_name(self) -> str | None:
        return self.product.name if getattr(self, "product", None) else None

    @property
    def product_sku(self) -> str | None:
        return self.product.sku if getattr(self, "product", None) else None