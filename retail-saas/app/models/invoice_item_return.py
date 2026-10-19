from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.credit_note import CreditNote
    from app.models.invoice import Invoice
    from app.models.invoice_item import InvoiceItem
    from app.models.order_item import OrderItem
    from app.models.product import Product
    from app.models.product_batch import ProductBatch
    from app.models.refund import Refund


class InvoiceItemReturn(Base, TimestampMixin):
    __tablename__ = "invoice_item_returns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    invoice_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("invoice_items.id"), nullable=False, index=True)
    order_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("order_items.id"), nullable=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    batch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("product_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    condition: Mapped[str] = mapped_column(String(30), default="sellable", nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    refund_id: Mapped[Optional[int]] = mapped_column(ForeignKey("refunds.id", ondelete="SET NULL"), nullable=True)
    credit_note_id: Mapped[Optional[int]] = mapped_column(ForeignKey("credit_notes.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    invoice: Mapped["Invoice"] = relationship("Invoice")
    invoice_item: Mapped["InvoiceItem"] = relationship("InvoiceItem")
    order_item: Mapped[Optional["OrderItem"]] = relationship("OrderItem")
    product: Mapped["Product"] = relationship("Product")
    batch: Mapped[Optional["ProductBatch"]] = relationship("ProductBatch")

    __table_args__ = (
        Index("ix_invoice_item_returns_tenant_idemp", "tenant_id", "idempotency_key", unique=True),
    )
