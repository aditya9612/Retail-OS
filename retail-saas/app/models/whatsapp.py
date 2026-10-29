from typing import Optional
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class WhatsAppSetting(Base, TimestampMixin):
    __tablename__ = "whatsapp_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "store_id", name="uq_whatsapp_settings_tenant_store"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    store_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)

    phone_number_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    business_account_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    webhook_verify_token: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_send_invoice: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_send_order_confirm: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    template_invoice: Mapped[str] = mapped_column(String(100), default="pos_invoice_receipt", nullable=False)
    template_order_confirm: Mapped[str] = mapped_column(String(100), default="order_confirmation", nullable=False)
    template_language: Mapped[str] = mapped_column(String(20), default="en_US", nullable=False)

    tenant = relationship("Tenant")
    store = relationship("Store")


class WhatsAppLog(Base, TimestampMixin):
    __tablename__ = "whatsapp_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    store_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)

    recipient_phone: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    message_type: Mapped[str] = mapped_column(String(50), default="invoice", nullable=False, index=True)
    template_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    meta_message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", nullable=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    payload_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)

    tenant = relationship("Tenant")
    store = relationship("Store")
    invoice = relationship("Invoice")
    order = relationship("Order")

