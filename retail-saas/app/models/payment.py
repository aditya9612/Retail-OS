from decimal import Decimal
from datetime import datetime, date

from sqlalchemy import ForeignKey, Numeric, String , Text,DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transaction_id: Mapped[str | None] = mapped_column(String(100))
    gateway_response: Mapped[str | None] = mapped_column(String(1000))

    order: Mapped["Order"] = relationship("Order", back_populates="payments")


class PaymentGateway(Base, TimestampMixin):
    __tablename__ = "payment_gateways"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )

    gateway_name: Mapped[str] = mapped_column(String(100), nullable=False)
    merchant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    secret_key: Mapped[str] = mapped_column(Text, nullable=False)

    webhook_secret: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    environment: Mapped[str] = mapped_column(
        String(20),
        default="TEST"
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="active"
    )

class PaymentSplit(Base, TimestampMixin):
    __tablename__ = "payment_splits"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id"),
        nullable=False
    )

    payment_method: Mapped[str] = mapped_column(
        String(30),
        nullable=False
    )

    amount: Mapped[float] = mapped_column(
        DECIMAL(12,2),
        nullable=False
    )  

class Settlement(Base, TimestampMixin):
    __tablename__ = "settlements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    gateway_id: Mapped[int] = mapped_column(
        ForeignKey("payment_gateways.id"),
        nullable=False,
    )

    settlement_date: Mapped[date] = mapped_column(nullable=False)

    total_amount: Mapped[Decimal] = mapped_column(
        DECIMAL(12, 2),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
    )

    reference_no: Mapped[str] = mapped_column(
        String(100),
        nullable=True,
    )  

class PaymentWebhookLog(Base, TimestampMixin):
    __tablename__ = "payment_webhook_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)

    transaction_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    payload: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20),
        default="received",
    )           