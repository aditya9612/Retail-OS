from datetime import date
from decimal import Decimal
from typing import Any, TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.store import Store
    from app.models.supplier import Supplier


class Inventory(Base, TimestampMixin):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_stock_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_stock_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reorder_point: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    @property
    def low_stock_threshold(self) -> int:
        return self.min_stock_level or self.reorder_point

    @low_stock_threshold.setter
    def low_stock_threshold(self, val: int) -> None:
        self.min_stock_level = val

    @property
    def batch_number(self) -> str | None:
        return getattr(self, "_batch_number", None)

    @batch_number.setter
    def batch_number(self, val: str | None) -> None:
        self._batch_number = val

    @property
    def expiry_date(self) -> date | None:
        return getattr(self, "_expiry_date", None)

    @expiry_date.setter
    def expiry_date(self, val: date | None) -> None:
        self._expiry_date = val

    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="inventory_items",
    )

    store: Mapped["Store"] = relationship(
        "Store",
        back_populates="inventory_items",
    )


class StockMovement(Base, TimestampMixin):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)

    movement_type: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    reference_id: Mapped[int | None] = mapped_column(Integer)
    reference_type: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    @property
    def reference(self) -> str | None:
        return str(self.reference_id) if self.reference_id else None

    @reference.setter
    def reference(self, val: Any) -> None:
        if val is not None:
            try:
                self.reference_id = int(val)
            except (ValueError, TypeError):
                self.reference_type = str(val)

    @property
    def unit_cost(self) -> Decimal | None:
        return Decimal("0.00")

    @unit_cost.setter
    def unit_cost(self, val: Any) -> None:
        pass

    @property
    def from_store_id(self) -> int | None:
        return None

    @from_store_id.setter
    def from_store_id(self, val: Any) -> None:
        pass

    @property
    def to_store_id(self) -> int | None:
        return self.store_id

    @to_store_id.setter
    def to_store_id(self, val: Any) -> None:
        if val:
            self.store_id = val

    @property
    def supplier_id(self) -> int | None:
        return None

    @supplier_id.setter
    def supplier_id(self, val: Any) -> None:
        pass

    store: Mapped["Store"] = relationship(
        "Store",
        foreign_keys=[store_id],
        back_populates="stock_movements",
    )

    product: Mapped["Product"] = relationship("Product")