from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.store import Store

class DocumentSetting(Base, TimestampMixin):
    """Document branding overrides scoped to a tenant (global) or a specific store.

    The table holds only values that need to be configurable per document.  All other
    branding values fall back to the Tenant or Store models (e.g. name, address, phone).
    """

    __tablename__ = "document_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "store_id", name="uq_document_setting_tenant_store"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    store_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)

    # Optional overrides – if NULL the renderer will fall back to Tenant/Store fields
    business_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gstin: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    footer_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    invoice_prefix: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    bill_prefix: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Display flags – default to True where sensible, but can be overridden
    show_gstin: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    show_qr: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    show_signature: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    show_payment_details: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Logo is stored as a path relative to the static directory
    logo_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships – only for convenience
    tenant: Mapped["Tenant"] = relationship("Tenant", backref="document_settings")
    store: Mapped[Optional["Store"]] = relationship("Store", backref="document_settings")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
