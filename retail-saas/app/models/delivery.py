from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class Delivery(Base, TimestampMixin):
    __tablename__ = "deliveries"

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

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
    )

    delivery_person: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    tracking_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # 3PL Courier Partner, Method & Zone links
    partner_id: Mapped[int | None] = mapped_column(
        ForeignKey("delivery_partners.id"),
        nullable=True,
        index=True,
    )

    delivery_method_id: Mapped[int | None] = mapped_column(
        ForeignKey("delivery_methods.id"),
        nullable=True,
        index=True,
    )

    zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("delivery_zones.id"),
        nullable=True,
        index=True,
    )

    # Cash On Delivery (COD) tracking
    is_cod: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    cod_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    cod_collected: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    cod_collected_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # Scheduling, Dispatch & SLA
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    estimated_delivery_time: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    delivery_slot: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Failed Deliveries (NDR) & Attempts
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    failure_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Proof of Delivery (POD) & OTP
    delivery_otp: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    pod_image_url: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    recipient_signature: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    order = relationship(
        "Order",
        back_populates="delivery",
        lazy="joined",
    )

    partner = relationship(
        "DeliveryPartner",
        foreign_keys=[partner_id],
        lazy="joined",
    )

    delivery_method = relationship(
        "DeliveryMethod",
        foreign_keys=[delivery_method_id],
        lazy="joined",
    )

    zone = relationship(
        "DeliveryZone",
        foreign_keys=[zone_id],
        lazy="joined",
    )

    @property
    def partner_name(self) -> str | None:
        if getattr(self, "partner", None) and self.partner:
            return self.partner.name
        return None

    @property
    def partner_code(self) -> str | None:
        if getattr(self, "partner", None) and self.partner:
            return self.partner.code
        return None

    @property
    def method_name(self) -> str | None:
        if getattr(self, "delivery_method", None) and self.delivery_method:
            return self.delivery_method.name
        return None

    @property
    def zone_name(self) -> str | None:
        if getattr(self, "zone", None) and self.zone:
            return self.zone.name
        return None

    @property
    def recipient_name(self) -> str | None:
        if getattr(self, "order", None) and self.order and getattr(self.order, "customer", None) and self.order.customer:
            return self.order.customer.name
        return "Retail Customer"

    @property
    def recipient_phone(self) -> str | None:
        if getattr(self, "order", None) and self.order and getattr(self.order, "customer", None) and self.order.customer:
            return self.order.customer.phone
        return None

    @property
    def delivery_address(self) -> str | None:
        if getattr(self, "order", None) and self.order:
            return self.order.delivery_address
        return None

    @property
    def tracking_url(self) -> str | None:
        if getattr(self, "partner", None) and self.partner and self.partner.tracking_url_template and self.tracking_number:
            tmpl = self.partner.tracking_url_template
            if "{tracking_number}" in tmpl:
                return tmpl.replace("{tracking_number}", self.tracking_number)
            elif "{}" in tmpl:
                return tmpl.format(self.tracking_number)
            elif tmpl.endswith("="):
                return f"{tmpl}{self.tracking_number}"
            return f"{tmpl}/{self.tracking_number}"
        return None
