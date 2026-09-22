from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.delivery import Delivery
    from app.models.invoice import Invoice
    from app.models.order_item import OrderItem
    from app.models.payment import Payment


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    order_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    order_type: Mapped[str] = mapped_column(String(20), default="pos", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivery_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivery_pincode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    customer: Mapped[Optional["Customer"]] = relationship("Customer", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    invoice: Mapped[Optional["Invoice"]] = relationship("Invoice", back_populates="order", uselist=False)
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="order")
    delivery: Mapped[Optional["Delivery"]] = relationship("Delivery", back_populates="order", uselist=False)
    tracking: Mapped[list["OrderTracking"]] = relationship("OrderTracking", back_populates="order", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        # Ignore phantom coupon_code / delivery_status kwargs if passed
        self._coupon_code = kwargs.pop("coupon_code", None)
        self._delivery_status = kwargs.pop("delivery_status", None)
        super().__init__(**kwargs)

    @property
    def coupon_code(self) -> Optional[str]:
        return getattr(self, "_coupon_code", None)

    @coupon_code.setter
    def coupon_code(self, val: Optional[str]) -> None:
        self._coupon_code = val

    @property
    def delivery_status(self) -> Optional[str]:
        return getattr(self, "_delivery_status", self.status)

    @delivery_status.setter
    def delivery_status(self, val: Optional[str]) -> None:
        self._delivery_status = val


class OrderTracking(Base):
    __tablename__ = "order_tracking"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(30), nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="tracking",
    )

    def __init__(self, **kwargs):
        if "remarks" in kwargs and "notes" not in kwargs:
            kwargs["notes"] = kwargs.pop("remarks")
        kwargs.pop("updated_at", None)
        super().__init__(**kwargs)

    @property
    def remarks(self) -> Optional[str]:
        return self.notes

    @remarks.setter
    def remarks(self, val: Optional[str]) -> None:
        self.notes = val