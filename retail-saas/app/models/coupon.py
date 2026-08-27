from datetime import date

from decimal import Decimal
from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class Coupon(Base, TimestampMixin):

    __tablename__ = "coupons"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "code",
            name="uq_coupon_tenant_code",
        ),
    )

    # ========================================================
    # ID
    # ========================================================

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    # ========================================================
    # TENANT
    # ========================================================

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )

    # ========================================================
    # COUPON CODE
    # ========================================================

    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # ========================================================
    # DESCRIPTION
    # ========================================================

    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # ========================================================
    # DISCOUNT TYPE
    # ========================================================

    discount_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # ========================================================
    # DISCOUNT VALUE
    # ========================================================

    discount_value: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    # ========================================================
    # MINIMUM ORDER AMOUNT
    # ========================================================

    minimum_order_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    # ========================================================
    # MAXIMUM DISCOUNT
    # ========================================================

    maximum_discount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    # ========================================================
    # USAGE LIMIT
    # ========================================================

    usage_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    # ========================================================
    # USED COUNT
    # ========================================================

    used_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # ========================================================
    # START DATE
    # ========================================================

    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    # ========================================================
    # END DATE
    # ========================================================

    end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    # ========================================================
    # ACTIVE STATUS
    # ========================================================

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )