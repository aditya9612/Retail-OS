from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
        index=True,
    )

    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("invoices.id"),
        nullable=True,
        index=True,
    )

    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"),
        nullable=True,
        index=True,
    )

    gateway_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_gateways.id"),
        nullable=True,
        index=True,
    )

    payment_method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    transaction_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    gateway_transaction_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    gateway_response: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="payments",
    )


class PaymentGateway(Base, TimestampMixin):
    __tablename__ = "payment_gateways"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="razorpay",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    api_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    api_secret: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    webhook_secret: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    config: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    def __init__(self, **kwargs):
        if "gateway_name" in kwargs and "name" not in kwargs:
            kwargs["name"] = kwargs.pop("gateway_name")
        elif "gateway_name" in kwargs:
            kwargs.pop("gateway_name")

        if "secret_key" in kwargs and "api_secret" not in kwargs:
            kwargs["api_secret"] = kwargs.pop("secret_key")
        elif "secret_key" in kwargs:
            kwargs.pop("secret_key")

        if "status" in kwargs:
            status_val = kwargs.pop("status")
            if "is_active" not in kwargs:
                kwargs["is_active"] = (str(status_val).upper() == "ACTIVE")

        if "merchant_id" in kwargs:
            m_id = kwargs.pop("merchant_id")
            if "api_key" not in kwargs:
                kwargs["api_key"] = m_id

        kwargs.pop("environment", None)
        super().__init__(**kwargs)

    @property
    def gateway_name(self) -> str:
        return self.name

    @gateway_name.setter
    def gateway_name(self, val: str) -> None:
        self.name = val

    @property
    def secret_key(self) -> str | None:
        return self.api_secret

    @secret_key.setter
    def secret_key(self, val: str | None) -> None:
        self.api_secret = val

    @property
    def merchant_id(self) -> str | None:
        return self.api_key

    @merchant_id.setter
    def merchant_id(self, val: str | None) -> None:
        self.api_key = val

    @property
    def status(self) -> str:
        return "ACTIVE" if self.is_active else "INACTIVE"

    @status.setter
    def status(self, val: str) -> None:
        self.is_active = (str(val).upper() == "ACTIVE")

    @property
    def environment(self) -> str:
        return "PRODUCTION"

    @environment.setter
    def environment(self, val: str) -> None:
        pass


class PaymentSplit(Base):
    __tablename__ = "payment_splits"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id"),
        nullable=False,
        index=True,
    )

    payment_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="completed",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    payment: Mapped["Payment"] = relationship(
        "Payment",
    )

    def __init__(self, **kwargs):
        if "transaction_id" in kwargs and "payment_id" not in kwargs:
            kwargs["payment_id"] = kwargs.pop("transaction_id")
        if "payment_mode" in kwargs and "payment_method" not in kwargs:
            kwargs["payment_method"] = kwargs.pop("payment_mode")
        kwargs.pop("updated_at", None)
        super().__init__(**kwargs)

    @property
    def payment_mode(self) -> str:
        return self.payment_method

    @payment_mode.setter
    def payment_mode(self, val: str) -> None:
        self.payment_method = val

    @property
    def transaction_id(self) -> int:
        return self.payment_id

    @transaction_id.setter
    def transaction_id(self, val: int) -> None:
        self.payment_id = val


class Settlement(Base, TimestampMixin):
    __tablename__ = "settlements"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    gateway_id: Mapped[int] = mapped_column(
        ForeignKey("payment_gateways.id"),
        nullable=False,
        index=True,
    )

    settlement_date: Mapped[date] = mapped_column(
        nullable=False,
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )

    reference_no: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    settlement_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    charges: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    gateway: Mapped["PaymentGateway"] = relationship(
        "PaymentGateway",
    )


class PaymentWebhookLog(Base, TimestampMixin):
    __tablename__ = "payment_webhook_logs"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    gateway_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    transaction_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    payload: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="received",
        index=True,
    )