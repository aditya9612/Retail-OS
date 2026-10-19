from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class GRN(Base, TimestampMixin):
    __tablename__ = "grns"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    purchase_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_orders.id"),
        nullable=True,
        index=True,
    )

    warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.id"),
        nullable=True,
        index=True,
    )

    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id"),
        nullable=True,
        index=True,
    )

    grn_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
    )

    invoice_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    invoice_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    vehicle_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    transporter_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    remarks: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    received_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    received_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    items = relationship(
        "GRNItem",
        back_populates="grn",
        cascade="all, delete-orphan",
    )

    purchase_order = relationship(
        "PurchaseOrder",
        foreign_keys=[purchase_order_id],
        lazy="joined",
    )

    warehouse = relationship(
        "Warehouse",
        foreign_keys=[warehouse_id],
        lazy="joined",
    )

    store = relationship(
        "Store",
        foreign_keys=[store_id],
        lazy="joined",
    )

    created_by = relationship(
        "User",
        foreign_keys=[created_by_id],
        lazy="joined",
    )

    received_by = relationship(
        "User",
        foreign_keys=[received_by_id],
        lazy="joined",
    )

    @property
    def warehouse_name(self) -> str | None:
        return self.warehouse.name if getattr(self, "warehouse", None) else None

    @property
    def store_name(self) -> str | None:
        return self.store.name if getattr(self, "store", None) else None

    @property
    def purchase_order_number(self) -> str | None:
        return self.purchase_order.order_number if getattr(self, "purchase_order", None) else None

    @property
    def supplier_name(self) -> str | None:
        if getattr(self, "purchase_order", None) and getattr(self.purchase_order, "supplier", None):
            return self.purchase_order.supplier.name
        return None

    @property
    def supplier_id(self) -> int | None:
        if getattr(self, "purchase_order", None):
            return self.purchase_order.supplier_id
        return None

    @property
    def created_by_name(self) -> str | None:
        if getattr(self, "created_by", None):
            return getattr(self.created_by, "full_name", None) or getattr(self.created_by, "email", None)
        return None

    @property
    def received_by_name(self) -> str | None:
        if getattr(self, "received_by", None):
            return getattr(self.received_by, "full_name", None) or getattr(self.received_by, "email", None)
        return None

    @property
    def total_items_count(self) -> int:
        return len(self.items) if self.items else 0

    @property
    def total_ordered_quantity(self) -> int:
        return sum(item.ordered_quantity for item in self.items) if self.items else 0

    @property
    def total_received_quantity(self) -> int:
        return sum(item.received_quantity for item in self.items) if self.items else 0

    @property
    def total_accepted_quantity(self) -> int:
        if not self.items:
            return 0
        return sum(
            item.accepted_quantity if getattr(item, "accepted_quantity", None) is not None else item.received_quantity
            for item in self.items
        )

    @property
    def total_rejected_quantity(self) -> int:
        if not self.items:
            return 0
        return sum(item.rejected_quantity or 0 for item in self.items)

    @property
    def total_cost_value(self) -> Decimal:
        if not self.items:
            return Decimal("0.00")
        total = Decimal("0.00")
        for item in self.items:
            cost = getattr(item, "unit_cost", None) or Decimal("0.00")
            qty = getattr(item, "accepted_quantity", None)
            if qty is None:
                qty = item.received_quantity
            total += Decimal(str(cost)) * Decimal(str(qty))
        return total.quantize(Decimal("0.01"))


class GRNItem(Base):
    __tablename__ = "grn_items"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    grn_id: Mapped[int] = mapped_column(
        ForeignKey("grns.id"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"),
        nullable=False,
    )

    ordered_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    received_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    accepted_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    rejected_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=0,
    )

    damage_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    batch_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    unit_cost_col: Mapped[Decimal | None] = mapped_column(
        "unit_cost",
        Numeric(12, 2),
        nullable=True,
    )

    remarks: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    grn = relationship(
        "GRN",
        back_populates="items",
    )

    product = relationship(
        "Product",
        foreign_keys=[product_id],
        lazy="joined",
    )

    @property
    def product_name(self) -> str | None:
        return self.product.name if getattr(self, "product", None) else None

    @property
    def product_sku(self) -> str | None:
        return self.product.sku if getattr(self, "product", None) else None

    @property
    def unit_cost(self):
        if self.unit_cost_col is not None:
            return self.unit_cost_col
        if hasattr(self, "_unit_cost") and self._unit_cost is not None:
            return self._unit_cost
        if getattr(self, "product", None) and getattr(self.product, "cost_price", None):
            return self.product.cost_price
        return None

    @unit_cost.setter
    def unit_cost(self, val):
        self.unit_cost_col = val
        self._unit_cost = val