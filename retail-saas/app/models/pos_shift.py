from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.pos_cash_movement import POSCashMovement
    from app.models.store import Store
    from app.models.tenant import Tenant
    from app.models.user import User


class POSShift(Base, TimestampMixin):
    __tablename__ = "pos_shifts"
    __table_args__ = (
        Index("ix_pos_shifts_tenant_store_status", "tenant_id", "store_id", "status"),
        Index("ix_pos_shifts_cashier_status", "tenant_id", "cashier_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)
    cashier_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)

    opening_cash_float: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    closing_cash_counted: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    expected_cash: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cash_variance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    store: Mapped["Store"] = relationship("Store")
    cashier: Mapped["User"] = relationship("User", foreign_keys=[cashier_id])
    movements: Mapped[list["POSCashMovement"]] = relationship(
        "POSCashMovement",
        back_populates="shift",
        cascade="all, delete-orphan",
    )

