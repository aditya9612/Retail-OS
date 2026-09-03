from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
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

    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id"),
        nullable=False,
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

    purchase_order = relationship(
        "PurchaseOrder",
    )

    items = relationship(
        "PurchaseOrderReturnItem",
        back_populates="purchase_order_return",
        cascade="all, delete-orphan",
    )


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

    purchase_order_return = relationship(
        "PurchaseOrderReturn",
        back_populates="items",
    )

    purchase_order_item = relationship(
        "PurchaseOrderItem",
    )

    product = relationship(
        "Product",
    )