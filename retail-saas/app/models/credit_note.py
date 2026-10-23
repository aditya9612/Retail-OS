from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.credit_note_redemption import CreditNoteRedemption
    from app.models.customer import Customer
    from app.models.invoice import Invoice
    from app.models.refund import Refund


class CreditNote(Base, TimestampMixin):
    __tablename__ = "credit_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    credit_note_no: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    refund_id: Mapped[int] = mapped_column(ForeignKey("refunds.id"), nullable=False, unique=True)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="issued", nullable=False, index=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    return_id: Mapped[Optional[int]] = mapped_column(ForeignKey("invoice_item_returns.id", ondelete="SET NULL", use_alter=True), nullable=True)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="credit_notes")
    refund: Mapped["Refund"] = relationship("Refund", back_populates="credit_note")
    customer: Mapped[Optional["Customer"]] = relationship("Customer")
    redemptions: Mapped[list["CreditNoteRedemption"]] = relationship("CreditNoteRedemption", back_populates="credit_note", cascade="all, delete-orphan")

    @property
    def invoice_number(self) -> Optional[str]:
        return self.invoice.invoice_number if self.invoice else None

    @property
    def store_id(self) -> Optional[int]:
        return self.invoice.store_id if self.invoice else None

    @property
    def customer_name(self) -> Optional[str]:
        if self.customer:
            return self.customer.name
        if self.invoice and self.invoice.order and self.invoice.order.customer:
            return self.invoice.order.customer.name
        return None

    @property
    def customer_phone(self) -> Optional[str]:
        if self.customer:
            return self.customer.phone
        if self.invoice and self.invoice.order and self.invoice.order.customer:
            return self.invoice.order.customer.phone
        return None

    @property
    def is_expired(self) -> bool:
        if self.valid_until and self.valid_until < datetime.utcnow():
            return True
        return False
