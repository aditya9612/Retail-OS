from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.saas_billing import SaaSPlan


class EntitlementDimension:
    """
    Architecture dimension constants under consideration.
    These are technical dimensions, NOT approved commercial limits.
    """
    USERS = "users"
    STORES = "stores"
    PRODUCTS = "products"
    MONTHLY_ORDERS = "monthly_orders"
    CUSTOMERS = "customers"
    STORAGE = "storage"

    # Enforced hard quotas
    HARD_QUOTA_DIMENSIONS = {USERS, STORES, PRODUCTS}
    # Monitored soft metrics
    SOFT_METRIC_DIMENSIONS = {MONTHLY_ORDERS}
    # Active operational dimensions reported in tenant usage
    OPERATIONAL_DIMENSIONS = {USERS, STORES, PRODUCTS, MONTHLY_ORDERS}
    # Future/configurable dimensions (not metered or blocking in Task 9.3A)
    FUTURE_DIMENSIONS = {CUSTOMERS, STORAGE}

    ALL = {USERS, STORES, PRODUCTS, MONTHLY_ORDERS, CUSTOMERS, STORAGE}


class SaaSPlanEntitlement(Base, TimestampMixin):
    """
    Normalized entitlement storage for SaaS plans.
    Frozen unlimited contract:
    - is_unlimited = True  => value is ignored / null permitted
    - is_unlimited = False => value specifies numeric ceiling
    """
    __tablename__ = "saas_plan_entitlements"
    __table_args__ = (
        UniqueConstraint("plan_id", "dimension", name="uq_plan_dimension"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("saas_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dimension: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    value: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    is_unlimited: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    plan: Mapped["SaaSPlan"] = relationship(
        "SaaSPlan",
        back_populates="entitlements",
    )
