from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.credit_note import CreditNote
    from app.models.invoice_item import InvoiceItem
    from app.models.order import Order
    from app.models.refund import Refund


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, unique=True)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    is_b2b: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="invoice")
    items: Mapped[list["InvoiceItem"]] = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    refunds: Mapped[list["Refund"]] = relationship("Refund", back_populates="invoice")
    credit_notes: Mapped[list["CreditNote"]] = relationship("CreditNote", back_populates="invoice")

    def __init__(self, **kwargs):
        self._status = kwargs.pop("status", "issued")
        self._tax_breakdown = kwargs.pop("tax_breakdown", None)
        if "tax_amount" not in kwargs:
            cgst = kwargs.get("cgst_amount", Decimal("0.00")) or Decimal("0.00")
            sgst = kwargs.get("sgst_amount", Decimal("0.00")) or Decimal("0.00")
            igst = kwargs.get("igst_amount", Decimal("0.00")) or Decimal("0.00")
            kwargs["tax_amount"] = cgst + sgst + igst
        super().__init__(**kwargs)

    @property
    def status(self) -> str:
        return getattr(self, "_status", "issued")

    @status.setter
    def status(self, val: str) -> None:
        self._status = val

    @property
    def tax_breakdown(self) -> dict:
        return getattr(self, "_tax_breakdown", {
            "cgst": float(self.cgst_amount),
            "sgst": float(self.sgst_amount),
            "igst": float(self.igst_amount),
        })

    @tax_breakdown.setter
    def tax_breakdown(self, val: dict) -> None:
        self._tax_breakdown = val