from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.order_item import OrderItem
    from app.models.invoice import Invoice
    from app.models.payment import Payment
    from app.models.delivery import Delivery
    
class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    order_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    order_type: Mapped[str] = mapped_column(String(20), default="pos")
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    coupon_code: Mapped[str | None] = mapped_column(String(50))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    delivery_address: Mapped[str | None] = mapped_column(Text)
    delivery_status: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)

    customer: Mapped["Customer | None"] = relationship("Customer", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    invoice: Mapped["Invoice | None"] = relationship("Invoice", back_populates="order", uselist=False)
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="order")
    delivery: Mapped["Delivery | None"] = relationship("Delivery", back_populates="order", uselist=False)
    tracking: Mapped[list["OrderTracking"]] = relationship("OrderTracking", back_populates="order", cascade="all, delete-orphan",)
    
    
class OrderTracking(Base, TimestampMixin):
    __tablename__ = "order_tracking"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(50), nullable=False)

    remarks: Mapped[str | None] = mapped_column(Text)

    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="tracking",
    )