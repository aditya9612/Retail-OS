from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class Store(Base, TimestampMixin):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    pincode: Mapped[str | None] = mapped_column(String(10))
    phone: Mapped[str | None] = mapped_column(String(20))
    gstin: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_warehouse: Mapped[bool] = mapped_column(Boolean, default=False)

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