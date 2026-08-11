from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class PurchaseOrder(Base, TimestampMixin):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"),
        nullable=False,
        index=True,
    )

    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id"),
        nullable=False,
        index=True,
    )

    po_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="draft",
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12,2),
        default=Decimal("0.00"),
    )

    remarks: Mapped[str | None] = mapped_column(Text)

    supplier = relationship(
    "Supplier"
    )

    store = relationship(
    "Store"
    )

    items = relationship(
    "PurchaseOrderItem",
    back_populates="purchase_order",
    cascade="all, delete-orphan",
    )
    
    
class PurchaseOrderItem(Base, TimestampMixin):
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id"),
        nullable=False,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"),
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(Integer)

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12,2)
    )

    total: Mapped[Decimal] = mapped_column(
        Numeric(12,2)
    )

    purchase_order = relationship(
        "PurchaseOrder",
        back_populates="items",
    )

    product = relationship("Product")