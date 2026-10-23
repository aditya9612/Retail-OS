from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
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

    store_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("stores.id"),
        nullable=True,
        index=True,
    )

    warehouse_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("warehouses.id"),
        nullable=True,
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

    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    shipping_charges: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
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

    invoice_number: Mapped[Optional[str]] = mapped_column(
        String(100),
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

    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    cancellation_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    supplier = relationship("Supplier", foreign_keys=[supplier_id], lazy="joined")
    store = relationship("Store", foreign_keys=[store_id], lazy="joined")
    warehouse = relationship("Warehouse", foreign_keys=[warehouse_id], lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
    approved_by = relationship("User", foreign_keys=[approved_by_id], lazy="joined")

    items = relationship(
        "PurchaseOrderItem",
        back_populates="purchase_order",
        foreign_keys="PurchaseOrderItem.po_id",
        cascade="all, delete-orphan",
        lazy="joined",
    )

    def __init__(self, **kwargs):
        if "po_number" in kwargs and "order_number" not in kwargs:
            kwargs["order_number"] = kwargs.pop("po_number")
        if "remarks" in kwargs and "notes" not in kwargs:
            kwargs["notes"] = kwargs.pop("remarks")
        if "invoice_id" in kwargs and "invoice_number" not in kwargs:
            kwargs["invoice_number"] = kwargs.pop("invoice_id")
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
    def invoice_id(self) -> Optional[str]:
        return self.invoice_number

    @invoice_id.setter
    def invoice_id(self, value: Optional[str]) -> None:
        self.invoice_number = value

    @property
    def supplier_name(self) -> Optional[str]:
        return self.supplier.name if getattr(self, "supplier", None) else None

    @property
    def supplier_email(self) -> Optional[str]:
        return self.supplier.email if getattr(self, "supplier", None) else None

    @property
    def supplier_phone(self) -> Optional[str]:
        return self.supplier.phone if getattr(self, "supplier", None) else None

    @property
    def supplier_gstin(self) -> Optional[str]:
        return getattr(self.supplier, "gstin", None) if getattr(self, "supplier", None) else None

    @property
    def store_name(self) -> Optional[str]:
        return self.store.name if getattr(self, "store", None) else None

    @property
    def warehouse_name(self) -> Optional[str]:
        return self.warehouse.name if getattr(self, "warehouse", None) else None

    @property
    def created_by_name(self) -> Optional[str]:
        if getattr(self, "created_by", None):
            return getattr(self.created_by, "full_name", None) or getattr(self.created_by, "name", None)
        return None

    @property
    def approved_by_name(self) -> Optional[str]:
        if getattr(self, "approved_by", None):
            return getattr(self.approved_by, "full_name", None) or getattr(self.approved_by, "name", None)
        return None

    @property
    def total_quantity(self) -> int:
        return sum(item.quantity for item in self.items) if self.items else 0

    @property
    def total_received_quantity(self) -> int:
        return sum(item.received_quantity or 0 for item in self.items) if self.items else 0

    @property
    def remaining_quantity(self) -> int:
        return max(0, self.total_quantity - self.total_received_quantity)


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

    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    hsn_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    unit_of_measure: Mapped[Optional[str]] = mapped_column(
        String(30),
        default="pcs",
        nullable=True,
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

    product = relationship("Product", foreign_keys=[product_id], lazy="joined")

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

    @property
    def product_name(self) -> Optional[str]:
        return self.product.name if getattr(self, "product", None) else None

    @property
    def product_sku(self) -> Optional[str]:
        return self.product.sku if getattr(self, "product", None) else None

    @property
    def remaining_quantity(self) -> int:
        return max(0, self.quantity - (self.received_quantity or 0))