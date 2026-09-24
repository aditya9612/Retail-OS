from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.saas_plan_entitlement import SaaSPlanEntitlement
    from app.models.super_admin import SuperAdmin
    from app.models.tenant import Tenant


class SaaSPlan(Base, TimestampMixin):
    __tablename__ = "saas_plans"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="INR",
        nullable=False,
    )
    billing_interval: Mapped[str] = mapped_column(
        String(20),
        default="monthly",
        nullable=False,
    )
    trial_days: Mapped[int] = mapped_column(
        Integer,
        default=14,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    subscriptions: Mapped[list["SaaSSubscription"]] = relationship(
        "SaaSSubscription",
        back_populates="plan",
    )
    entitlements: Mapped[list["SaaSPlanEntitlement"]] = relationship(
        "SaaSPlanEntitlement",
        back_populates="plan",
        cascade="all, delete-orphan",
    )


class SaaSSubscription(Base, TimestampMixin):
    __tablename__ = "saas_subscriptions"
    __table_args__ = (
        Index(
            "ix_saas_subscriptions_tenant_lookup",
            "tenant_id",
            "status",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("saas_plans.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="trialing",
        nullable=False,
        index=True,
    )
    billing_interval: Mapped[str] = mapped_column(
        String(20),
        default="monthly",
        nullable=False,
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="INR",
        nullable=False,
    )
    start_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )
    trial_end_date: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        foreign_keys=[tenant_id],
    )
    plan: Mapped["SaaSPlan"] = relationship(
        "SaaSPlan",
        back_populates="subscriptions",
    )
    invoices: Mapped[list["SaaSInvoice"]] = relationship(
        "SaaSInvoice",
        back_populates="subscription",
    )
    upi_transactions: Mapped[list["SaaSUPITransaction"]] = relationship(
        "SaaSUPITransaction",
        back_populates="subscription",
    )


class SaaSInvoice(Base, TimestampMixin):
    __tablename__ = "saas_invoices"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("saas_subscriptions.id"),
        nullable=False,
        index=True,
    )
    invoice_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )
    billing_reason: Mapped[str] = mapped_column(
        String(30),
        default="subscription_cycle",
        nullable=False,
    )
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="INR",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="unpaid",
        nullable=False,
        index=True,
    )
    due_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    pdf_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        foreign_keys=[tenant_id],
    )
    subscription: Mapped["SaaSSubscription"] = relationship(
        "SaaSSubscription",
        back_populates="invoices",
    )
    upi_transactions: Mapped[list["SaaSUPITransaction"]] = relationship(
        "SaaSUPITransaction",
        back_populates="invoice",
    )


class SaaSUPITransaction(Base, TimestampMixin):
    __tablename__ = "saas_upi_transactions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("saas_subscriptions.id"),
        nullable=False,
    )
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("saas_invoices.id"),
        nullable=False,
        index=True,
    )
    reference: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )
    utr: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="INR",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
        index=True,
    )
    upi_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    payer_vpa: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    verified_by_super_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("super_admins.id"),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    proof_image_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        foreign_keys=[tenant_id],
    )
    subscription: Mapped["SaaSSubscription"] = relationship(
        "SaaSSubscription",
        back_populates="upi_transactions",
    )
    invoice: Mapped["SaaSInvoice"] = relationship(
        "SaaSInvoice",
        back_populates="upi_transactions",
    )
    verified_by: Mapped["SuperAdmin"] = relationship(
        "SuperAdmin",
        foreign_keys=[verified_by_super_admin_id],
    )


class SaaSInvoiceSequence(Base, TimestampMixin):
    __tablename__ = "saas_invoice_sequences"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    year: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
    )
    last_sequence: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

