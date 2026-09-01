from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.order import Order
    from app.models.customer import Customer


class OrderReturn(Base, TimestampMixin):
    __tablename__ = "order_returns"

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

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        nullable=False,
        index=True,
    )

    reason: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    remarks: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="requested",
        index=True,
    )

    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
    )

    order: Mapped["Order"] = relationship(
        "Order",
    )

    customer: Mapped["Customer"] = relationship(
        "Customer",
    )