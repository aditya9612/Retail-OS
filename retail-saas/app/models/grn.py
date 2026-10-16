from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
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

    remarks: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    received_at: Mapped[datetime | None] = mapped_column(
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

    @property
    def warehouse_name(self) -> str | None:
        return self.warehouse.name if getattr(self, "warehouse", None) else None

    @property
    def purchase_order_number(self) -> str | None:
        return self.purchase_order.order_number if getattr(self, "purchase_order", None) else None

    @property
    def supplier_name(self) -> str | None:
        if getattr(self, "purchase_order", None) and getattr(self.purchase_order, "supplier", None):
            return self.purchase_order.supplier.name
        return None


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
        if hasattr(self, "_unit_cost") and self._unit_cost is not None:
            return self._unit_cost
        if getattr(self, "product", None) and getattr(self.product, "cost_price", None):
            return self.product.cost_price
        return None

    @unit_cost.setter
    def unit_cost(self, val):
        self._unit_cost = val