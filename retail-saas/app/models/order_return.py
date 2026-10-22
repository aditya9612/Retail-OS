from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.order import Order
    from app.models.customer import Customer
    from app.models.user import User
    from app.models.order_item import OrderItem
    from app.models.product import Product


class OrderReturn(Base, TimestampMixin):
    __tablename__ = "order_returns"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
        index=True,
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        nullable=False,
        index=True,
    )

    return_number: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        unique=True,
        index=True,
    )

    return_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="refund",
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

    refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    exchange_order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id"),
        nullable=True,
        index=True,
    )

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    approved_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    rejected_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    rejected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    rejection_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    completed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
    )

    order: Mapped["Order"] = relationship(
        "Order",
        foreign_keys=[order_id],
    )

    customer: Mapped["Customer"] = relationship(
        "Customer",
    )

    items: Mapped[list["OrderReturnItem"]] = relationship(
        "OrderReturnItem",
        back_populates="order_return",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __init__(self, **kwargs):
        if not kwargs.get("return_number"):
            kwargs["return_number"] = f"RMA-{uuid.uuid4().hex[:8].upper()}"
        super().__init__(**kwargs)


class OrderReturnItem(Base, TimestampMixin):
    __tablename__ = "order_return_items"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    order_return_id: Mapped[int] = mapped_column(
        ForeignKey("order_returns.id"),
        nullable=False,
        index=True,
    )

    order_item_id: Mapped[int] = mapped_column(
        ForeignKey("order_items.id"),
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
        default=1,
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    condition: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="sellable",
    )

    reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    order_return: Mapped["OrderReturn"] = relationship(
        "OrderReturn",
        back_populates="items",
    )

    order_item: Mapped[Optional["OrderItem"]] = relationship(
        "OrderItem",
        lazy="joined",
    )

    product: Mapped[Optional["Product"]] = relationship(
        "Product",
        lazy="joined",
    )

    @property
    def product_name(self) -> str:
        if self.product:
            return self.product.name
        if self.order_item:
            return self.order_item.product_name
        return ""

    @property
    def sku(self) -> str:
        if self.product:
            return self.product.sku
        if self.order_item:
            return self.order_item.sku
        return ""
