from typing import Optional
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenException
from app.models.saas_billing import SaaSSubscription
from app.models.tenant import Tenant
from app.models.user import User


class SaaSSubscriptionAccessService:
    """
    Authoritative subscription access gating service for tenant operations.
    Enforces access rules based on authoritative SaaSSubscription DB state:
    - trialing: full read and operational write access
    - active: full read and operational write access
    - past_due: full read, billing, and operational write access (7-day grace period)
    - expired: read-only access + billing recovery allowed; operational writes blocked (403)
    - cancelled: read-only access + billing recovery allowed; operational writes blocked (403)
    """

    ALLOWED_OPERATIONAL_WRITE_STATUSES = {"trialing", "active", "past_due"}
    RESTRICTED_STATUSES = {"expired", "cancelled"}

    def __init__(self, db: Session):
        self.db = db

    def get_authoritative_subscription(
        self,
        tenant_id: int,
    ) -> Optional[SaaSSubscription]:
        """
        Deterministically queries the authoritative subscription for a tenant:
        1. Checks authoritative Tenant.current_subscription_id first if configured.
        2. Validates tenant ownership of the pointed subscription (fails closed with 403 on mismatch).
        3. If current_subscription_id is NULL, falls back deterministically to latest subscription (created_at DESC, id DESC).
        """
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant and tenant.current_subscription_id is not None:
            sub = (
                self.db.query(SaaSSubscription)
                .filter(SaaSSubscription.id == tenant.current_subscription_id)
                .first()
            )
            if sub:
                if sub.tenant_id != tenant_id:
                    raise ForbiddenException(
                        f"Security violation: Subscription {sub.id} belongs to tenant {sub.tenant_id}, but tenant pointer is {tenant_id}"
                    )
                return sub
            return None

        return (
            self.db.query(SaaSSubscription)
            .filter(SaaSSubscription.tenant_id == tenant_id)
            .order_by(
                SaaSSubscription.created_at.desc(),
                SaaSSubscription.id.desc(),
            )
            .first()
        )

    def require_operational_write_access(
        self,
        user: User,
    ) -> SaaSSubscription:
        """
        Enforces operational write authorization for tenant users.
        - Fails closed with 403 Forbidden if user has no tenant or no subscription.
        - Allows 'trialing', 'active', and 'past_due' (grace period).
        - Blocks 'expired' and 'cancelled' with 403 Forbidden.
        """
        if not user.tenant_id:
            raise ForbiddenException("User is not associated with any tenant")

        sub = self.get_authoritative_subscription(user.tenant_id)
        if not sub:
            raise ForbiddenException("No active subscription found for tenant")

        if sub.status in self.ALLOWED_OPERATIONAL_WRITE_STATUSES:
            return sub

        if sub.status == "expired":
            raise ForbiddenException(
                "Subscription is expired. Operational write operations are restricted."
            )

        if sub.status == "cancelled":
            raise ForbiddenException(
                "Subscription is cancelled. Operational write operations are restricted."
            )

        raise ForbiddenException(
            f"Subscription status '{sub.status}' does not permit operational write operations."
        )

    def require_read_access(
        self,
        user: User,
    ) -> Optional[SaaSSubscription]:
        """
        Allows historical/read-only access for tenant users across all valid statuses.
        Expired and cancelled subscriptions retain read access.
        """
        if not user.tenant_id:
            raise ForbiddenException("User is not associated with any tenant")
        return self.get_authoritative_subscription(user.tenant_id)

    def require_billing_access(
        self,
        user: User,
    ) -> Optional[SaaSSubscription]:
        """
        Allows billing/recovery access for tenant users across all subscription statuses,
        enabling subscription recovery and renewal.
        """
        if not user.tenant_id:
            raise ForbiddenException("User is not associated with any tenant")
        return self.get_authoritative_subscription(user.tenant_id)
