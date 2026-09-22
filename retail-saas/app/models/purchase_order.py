from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
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

    order_number: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="draft",
        nullable=False,
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    expected_delivery_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    supplier = relationship("Supplier")

    items = relationship(
        "PurchaseOrderItem",
        back_populates="purchase_order",
        foreign_keys="PurchaseOrderItem.po_id",
        cascade="all, delete-orphan",
    )

    def __init__(self, **kwargs):
        if "po_number" in kwargs and "order_number" not in kwargs:
            kwargs["order_number"] = kwargs.pop("po_number")
        if "remarks" in kwargs and "notes" not in kwargs:
            kwargs["notes"] = kwargs.pop("remarks")
        # store_id is not in purchase_orders table
        self._store_id = kwargs.pop("store_id", None)
        super().__init__(**kwargs)

    @property
    def po_number(self) -> str:
        return self.order_number

    @po_number.setter
    def po_number(self, value: str) -> None:
        self.order_number = value

    @property
    def remarks(self) -> Optional[str]:
        return self.notes

    @remarks.setter
    def remarks(self, value: Optional[str]) -> None:
        self.notes = value

    @property
    def store_id(self) -> Optional[int]:
        return getattr(self, "_store_id", None)

    @store_id.setter
    def store_id(self, value: Optional[int]) -> None:
        self._store_id = value


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    po_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id"),
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

    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    received_quantity: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    purchase_order = relationship(
        "PurchaseOrder",
        back_populates="items",
        foreign_keys=[po_id],
    )

    product = relationship("Product")

    def __init__(self, **kwargs):
        if "purchase_order_id" in kwargs and "po_id" not in kwargs:
            kwargs["po_id"] = kwargs.pop("purchase_order_id")
        if "unit_price" in kwargs and "unit_cost" not in kwargs:
            kwargs["unit_cost"] = kwargs.pop("unit_price")
        if "total" in kwargs and "total_cost" not in kwargs:
            kwargs["total_cost"] = kwargs.pop("total")
        super().__init__(**kwargs)

    @property
    def purchase_order_id(self) -> int:
        return self.po_id

    @purchase_order_id.setter
    def purchase_order_id(self, val: int) -> None:
        self.po_id = val

    @property
    def unit_price(self) -> Decimal:
        return self.unit_cost

    @unit_price.setter
    def unit_price(self, val: Decimal) -> None:
        self.unit_cost = val

    @property
    def total(self) -> Decimal:
        return self.total_cost

    @total.setter
    def total(self, val: Decimal) -> None:
        self.total_cost = val