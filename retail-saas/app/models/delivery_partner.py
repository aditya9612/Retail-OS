from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class DeliveryPartner(Base, TimestampMixin):
    __tablename__ = "delivery_partners"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "code",
            name="uq_delivery_partner_tenant_code",
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

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    contact_email: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    contact_phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    api_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    api_secret: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    tracking_url_template: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
