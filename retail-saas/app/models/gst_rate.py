from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class GstRate(Base, TimestampMixin):
    __tablename__ = "gst_rates"
    __table_args__ = (UniqueConstraint("tenant_id", "hsn_code", name="uq_gst_rates_tenant_hsn"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    hsn_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cgst: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    sgst: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    igst: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    status: Mapped[bool] = mapped_column(Boolean, default=True)
