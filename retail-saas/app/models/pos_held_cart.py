from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.store import Store
    from app.models.tenant import Tenant
    from app.models.user import User


class POSHeldCart(Base, TimestampMixin):
    __tablename__ = "pos_held_carts"
    __table_args__ = (
        Index("ix_pos_held_carts_tenant_store_status", "tenant_id", "store_id", "status"),
        Index("ix_pos_held_carts_tenant_ref", "tenant_id", "hold_reference"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)

    hold_reference: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="held", index=True)
    items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    gst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    same_state: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    cart_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)

    held_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    recalled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    store: Mapped["Store"] = relationship("Store")
    cashier: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    customer: Mapped[Optional["Customer"]] = relationship("Customer", foreign_keys=[customer_id])

