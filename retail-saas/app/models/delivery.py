from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
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
        String(100)
    )

    tracking_number: Mapped[str | None] = mapped_column(
        String(100)
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime
    )

    order = relationship(
        "Order",
        back_populates="delivery"
    )