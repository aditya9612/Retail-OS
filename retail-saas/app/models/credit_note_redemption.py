from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.credit_note import CreditNote
    from app.models.invoice import Invoice
    from app.models.order import Order
    from app.models.tenant import Tenant
    from app.models.user import User


class CreditNoteRedemption(Base, TimestampMixin):
    __tablename__ = "credit_note_redemptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    credit_note_id: Mapped[int] = mapped_column(ForeignKey("credit_notes.id"), nullable=False, index=True)
    invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("invoices.id"), nullable=True, index=True)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    amount_redeemed: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    credit_note: Mapped["CreditNote"] = relationship("CreditNote", back_populates="redemptions")
    tenant: Mapped["Tenant"] = relationship("Tenant")
    invoice: Mapped[Optional["Invoice"]] = relationship("Invoice")
    order: Mapped[Optional["Order"]] = relationship("Order")
    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by])

