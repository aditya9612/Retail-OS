from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppException,
    ForbiddenException,
    NotFoundException,
    QuotaExceededException,
)
from app.models.customer import Customer
from app.models.order import Order
from app.models.product import Product
from app.models.saas_billing import SaaSSubscription
from app.models.saas_plan_entitlement import EntitlementDimension, SaaSPlanEntitlement
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User


class SaaSEntitlementService:
    """
    Centralized SaaS Entitlement Service.
    Single application-level authority for:
    - Authoritative current subscription resolution (via Tenant.current_subscription_id)
    - Plan entitlement resolution (via saas_plan_entitlements)
    - Resource usage counting using composite usage indexes
    - Limit determination & hard quota enforcement
    - Unlimited semantics & fail-closed validation
    - Tenant-row locking foundation for atomic resource creation/reactivation

    TRANSACTION BOUNDARY RULE:
    This service MUST NOT commit or roll back transactions. The caller/service
    layer owns the database transaction boundary.
    """

    ALLOWED_OPERATIONAL_WRITE_STATUSES = {"trialing", "active", "past_due"}
    DENIED_OPERATIONAL_WRITE_STATUSES = {"expired", "cancelled"}

    def __init__(self, db: Session):
        self.db = db

    def acquire_tenant_lock(self, tenant_id: int) -> Tenant:
        """
        Acquires an exclusive row lock on the tenant row using SELECT ... FOR UPDATE.
        Must be executed within an active transaction owned by the caller.
        """
        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == tenant_id)
            .with_for_update()
            .first()
        )
        if not tenant:
            raise NotFoundException(f"Tenant {tenant_id} not found")
        return tenant

    def get_current_subscription(
        self,
        tenant_id: int,
        lock_tenant: bool = False,
    ) -> SaaSSubscription:
        """
        Resolves the tenant's authoritative current subscription using Tenant.current_subscription_id.
        Fails closed if:
        - Tenant does not exist
        - Tenant.current_subscription_id is NULL
        - Pointed subscription does not exist
        - Subscription belongs to another tenant (cross-tenant mismatch)
        """
        if lock_tenant:
            tenant = self.acquire_tenant_lock(tenant_id)
        else:
            tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                raise NotFoundException(f"Tenant {tenant_id} not found")

        if tenant.current_subscription_id is None:
            raise ForbiddenException(
                f"Tenant {tenant_id} has no authoritative current subscription configured"
            )

        subscription = (
            self.db.query(SaaSSubscription)
            .filter(SaaSSubscription.id == tenant.current_subscription_id)
            .first()
        )
        if not subscription:
            raise ForbiddenException(
                f"Subscription {tenant.current_subscription_id} pointed by tenant {tenant_id} not found"
            )

        if subscription.tenant_id != tenant.id:
            raise ForbiddenException(
                f"Security violation: Subscription {subscription.id} belongs to tenant "
                f"{subscription.tenant_id}, but tenant pointer is {tenant.id}"
            )

        return subscription

    def get_entitlement(
        self,
        tenant_id: int,
        dimension: str,
        lock_tenant: bool = False,
    ) -> SaaSPlanEntitlement:
        """
        Resolves the entitlement row from saas_plan_entitlements for the tenant's
        current subscription and the specified dimension.
        Fails closed if:
        - Subscription or plan is missing
        - Entitlement dimension is not configured for the plan
        - Entitlement has is_unlimited=False but value is NULL or negative
        """
        subscription = self.get_current_subscription(tenant_id, lock_tenant=lock_tenant)

        if not subscription.plan_id:
            raise ForbiddenException(
                f"Subscription {subscription.id} has no SaaS plan assigned"
            )

        entitlement = (
            self.db.query(SaaSPlanEntitlement)
            .filter(
                SaaSPlanEntitlement.plan_id == subscription.plan_id,
                SaaSPlanEntitlement.dimension == dimension,
            )
            .first()
        )
        if not entitlement:
            raise ForbiddenException(
                f"Entitlement dimension '{dimension}' is not configured for plan {subscription.plan_id}"
            )

        if not entitlement.is_unlimited:
            if entitlement.value is None or entitlement.value < 0:
                raise ForbiddenException(
                    f"Entitlement dimension '{dimension}' has invalid limit value: {entitlement.value}"
                )

        return entitlement

    def get_limit(
        self,
        tenant_id: int,
        dimension: str,
        lock_tenant: bool = False,
    ) -> Tuple[Optional[int], bool]:
        """
        Returns (limit, is_unlimited) tuple.
        - If is_unlimited is True, limit is None.
        - If is_unlimited is False, limit is a non-negative integer.
        """
        entitlement = self.get_entitlement(
            tenant_id,
            dimension,
            lock_tenant=lock_tenant,
        )
        if entitlement.is_unlimited:
            return None, True
        return entitlement.value, False

    def get_usage(
        self,
        tenant_id: int,
        dimension: str,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> int:
        """
        Counts current resource usage for a tenant using authoritative queries.
        - users: active and non-deleted users
        - stores: active stores
        - products: active products
        - monthly_orders: non-cancelled orders within current subscription billing period
        - customers: tenant customers
        """
        if dimension == EntitlementDimension.USERS:
            return (
                self.db.query(func.count(User.id))
                .filter(
                    User.tenant_id == tenant_id,
                    User.is_deleted.is_(False),
                    User.is_active.is_(True),
                )
                .scalar()
                or 0
            )

        if dimension == EntitlementDimension.STORES:
            return (
                self.db.query(func.count(Store.id))
                .filter(
                    Store.tenant_id == tenant_id,
                    Store.is_active.is_(True),
                )
                .scalar()
                or 0
            )

        if dimension == EntitlementDimension.PRODUCTS:
            return (
                self.db.query(func.count(Product.id))
                .filter(
                    Product.tenant_id == tenant_id,
                    Product.is_active.is_(True),
                )
                .scalar()
                or 0
            )

        if dimension == EntitlementDimension.MONTHLY_ORDERS:
            if period_start is None or period_end is None:
                sub = self.get_current_subscription(tenant_id)
                period_start = period_start or sub.current_period_start
                period_end = period_end or sub.current_period_end

            if not period_start or not period_end:
                now = datetime.utcnow()
                period_start = datetime(now.year, now.month, 1)
                if now.month == 12:
                    period_end = datetime(now.year + 1, 1, 1)
                else:
                    period_end = datetime(now.year, now.month + 1, 1)

            return (
                self.db.query(func.count(Order.id))
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.created_at >= period_start,
                    Order.created_at < period_end,
                    Order.status != "cancelled",
                )
                .scalar()
                or 0
            )

        if dimension == EntitlementDimension.CUSTOMERS:
            return (
                self.db.query(func.count(Customer.id))
                .filter(Customer.tenant_id == tenant_id)
                .scalar()
                or 0
            )

        raise ForbiddenException(f"Unsupported usage dimension '{dimension}'")

    def check_limit(
        self,
        tenant_id: int,
        dimension: str,
        requested_amount: int = 1,
        lock_tenant: bool = False,
    ) -> dict:
        """
        Evaluates whether requested_amount can be accommodated without raising QuotaExceededException.
        Returns evaluation dict:
        {
            "allowed": bool,
            "dimension": str,
            "current_usage": int,
            "limit": Optional[int],
            "is_unlimited": bool,
            "requested": int,
            "subscription_status": str,
        }
        Fails closed if subscription status is not in allowed operational write statuses.
        """
        if requested_amount <= 0:
            raise AppException("Requested amount must be greater than 0")

        subscription = self.get_current_subscription(tenant_id, lock_tenant=lock_tenant)

        if subscription.status not in self.ALLOWED_OPERATIONAL_WRITE_STATUSES:
            raise ForbiddenException(
                f"Subscription status '{subscription.status}' does not permit operational resource creation."
            )

        entitlement = self.get_entitlement(tenant_id, dimension, lock_tenant=False)
        current_usage = self.get_usage(tenant_id, dimension)

        if entitlement.is_unlimited:
            return {
                "allowed": True,
                "dimension": dimension,
                "current_usage": current_usage,
                "limit": None,
                "is_unlimited": True,
                "requested": requested_amount,
                "subscription_status": subscription.status,
            }

        limit = entitlement.value
        allowed = (current_usage + requested_amount) <= limit

        return {
            "allowed": allowed,
            "dimension": dimension,
            "current_usage": current_usage,
            "limit": limit,
            "is_unlimited": False,
            "requested": requested_amount,
            "subscription_status": subscription.status,
        }

    def require_limit(
        self,
        tenant_id: int,
        dimension: str,
        requested_amount: int = 1,
        lock_tenant: bool = False,
    ) -> None:
        """
        Enforces plan quota constraint for hard-quota dimensions (users, stores, products).
        Raises:
        - ForbiddenException if subscription status is non-operational or configuration is missing
        - QuotaExceededException if current_usage + requested_amount > limit
        Does not commit transactions.
        """
        check = self.check_limit(
            tenant_id=tenant_id,
            dimension=dimension,
            requested_amount=requested_amount,
            lock_tenant=lock_tenant,
        )

        if not check["allowed"]:
            raise QuotaExceededException(
                dimension=dimension,
                current_usage=check["current_usage"],
                limit=check["limit"],
                requested=requested_amount,
            )
