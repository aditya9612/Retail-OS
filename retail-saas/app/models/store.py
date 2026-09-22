from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class Store(Base, TimestampMixin):
    __tablename__ = "stores"
    expenses: Mapped[list["StoreExpense"]] = relationship(
        "StoreExpense",
        back_populates="store",
        cascade="all, delete-orphan",
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    pincode: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def is_warehouse(self) -> bool:
        return not self.is_main

    @is_warehouse.setter
    def is_warehouse(self, val: bool) -> None:
        self.is_main = not val

    @property
    def gstin(self) -> str | None:
        return getattr(self, "_gstin", None)

    @gstin.setter
    def gstin(self, val: str | None) -> None:
        self._gstin = val

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="stores"
    )

    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="store"
    )

    inventory_items: Mapped[list["Inventory"]] = relationship(
        "Inventory",
        back_populates="store"
    )

    stock_movements: Mapped[list["StockMovement"]] = relationship(
        "StockMovement",
        foreign_keys="StockMovement.store_id",
        back_populates="store"
    )
