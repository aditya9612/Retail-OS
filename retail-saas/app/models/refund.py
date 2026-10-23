from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class Refund(Base, TimestampMixin):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id"),
        nullable=False,
        index=True,
    )

    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id"),
        nullable=True,
        index=True,
    )

    shift_id: Mapped[int | None] = mapped_column(
        ForeignKey("pos_shifts.id"),
        nullable=True,
        index=True,
    )

    refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    refund_method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        index=True,
        nullable=False,
    )

    refund_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    refund_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
    )

    initiated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    invoice: Mapped["Invoice"] = relationship(
        "Invoice",
        back_populates="refunds",
    )

    credit_note: Mapped["CreditNote | None"] = relationship(
        "CreditNote",
        back_populates="refund",
        uselist=False,
    )

    @property
    def invoice_number(self) -> str | None:
        return self.invoice.invoice_number if self.invoice else None

    @property
    def credit_note_no(self) -> str | None:
        return self.credit_note.credit_note_no if self.credit_note else None

    @property
    def credit_note_id(self) -> int | None:
        return self.credit_note.id if self.credit_note else None

    @property
    def store_id(self) -> int | None:
        return self.invoice.store_id if self.invoice else None

    @property
    def customer_id(self) -> int | None:
        if self.invoice and self.invoice.order:
            return self.invoice.order.customer_id
        return None

    @property
    def customer_name(self) -> str | None:
        if self.invoice and self.invoice.order and self.invoice.order.customer:
            return self.invoice.order.customer.name
        return None
