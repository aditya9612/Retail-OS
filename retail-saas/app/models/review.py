from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class Review(Base, TimestampMixin):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("products.id"),
        nullable=True,
        index=True,
    )

    store_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("stores.id"),
        nullable=True,
        index=True,
    )

    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id"),
        nullable=True,
        index=True,
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        nullable=False,
        index=True,
    )

    rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    comment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    is_verified_purchase: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="approved",
        nullable=False,
        index=True,
    )

    is_edited: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    merchant_reply: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    replied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    replied_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    product = relationship(
        "Product",
        lazy="joined",
    )

    customer = relationship(
        "Customer",
        lazy="joined",
    )

    store = relationship(
        "Store",
        lazy="joined",
    )

    order = relationship(
        "Order",
        lazy="joined",
    )

    replier = relationship(
        "User",
        foreign_keys=[replied_by],
        lazy="joined",
    )

    @property
    def customer_name(self) -> Optional[str]:
        return self.customer.name if self.customer else None

    @property
    def product_name(self) -> Optional[str]:
        return self.product.name if self.product else None

    @property
    def store_name(self) -> Optional[str]:
        return self.store.name if self.store else None
