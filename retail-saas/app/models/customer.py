from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__= "customers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    address: Mapped[str | None] = mapped_column(String(500))
    birthday: Mapped[date | None] = mapped_column(Date)
    loyalty_points: Mapped[int] = mapped_column(Integer, default=0)
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=True)
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, default=True)

    status: Mapped[str] = mapped_column(String(20), default="active")
    segment: Mapped[str] = mapped_column(String(20), default="new")
    total_spend: Mapped[int] = mapped_column(Integer, default=0)

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="customer")
