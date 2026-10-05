from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.pos_shift import POSShift
    from app.models.tenant import Tenant
    from app.models.user import User


class POSCashMovement(Base, TimestampMixin):
    __tablename__ = "pos_cash_movements"
    __table_args__ = (
        Index("ix_pos_cash_movements_shift", "tenant_id", "shift_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("pos_shifts.id"), nullable=False, index=True)
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Relationships
    shift: Mapped["POSShift"] = relationship("POSShift", back_populates="movements")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    tenant: Mapped["Tenant"] = relationship("Tenant")
