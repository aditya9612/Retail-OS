from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class Coupon(Base, TimestampMixin):
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(String(255))

    discount_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    discount_value: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    minimum_order_amount: Mapped[float] = mapped_column(
        Numeric(10, 2),
        default=0,
    )

    maximum_discount: Mapped[float | None] = mapped_column(
        Numeric(10, 2)
    )

    usage_limit: Mapped[int] = mapped_column(
        Integer,
        default=1,
    )

    used_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    start_date: Mapped[date] = mapped_column(Date)

    end_date: Mapped[date] = mapped_column(Date)

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )