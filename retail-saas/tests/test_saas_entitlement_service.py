from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import pytest
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import (
    AppException,
    ForbiddenException,
    NotFoundException,
    QuotaExceededException,
)
from app.models.customer import Customer
from app.models.order import Order
from app.models.product import Product
from app.models.role import Role
from app.models.saas_billing import SaaSPlan, SaaSSubscription
from app.models.saas_plan_entitlement import EntitlementDimension, SaaSPlanEntitlement
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.services.saas_entitlement_service import SaaSEntitlementService
from app.services.sale_service import SaleService


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def unique_suffix():
    return uuid.uuid4().hex[:8]


@pytest.fixture
def setup_test_tenant(db: Session, unique_suffix: str):
    """
    Creates a tenant with a dedicated plan and authoritative subscription.
    """
    plan = SaaSPlan(
        name=f"Entitlement Test Plan {unique_suffix}",
        code=f"test_plan_{unique_suffix}",
        price=Decimal("499.00"),
        billing_interval="monthly",
        is_active=True,
    )
    db.add(plan)
    db.flush()

    tenant = Tenant(
        name=f"Entitlement Corp {unique_suffix}",
        domain=f"entitlement-{unique_suffix}.test",
        is_active=True,
    )
    db.add(tenant)
    db.flush()

    now = datetime.utcnow()
    sub = SaaSSubscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status="active",
        unit_price=Decimal("499.00"),
        start_date=now - timedelta(days=5),
        current_period_start=now - timedelta(days=5),
        current_period_end=now + timedelta(days=25),
    )
    db.add(sub)
    db.flush()

    tenant.current_subscription_id = sub.id
    db.flush()

    role = Role(
        tenant_id=tenant.id,
        name="Admin",
    )
    db.add(role)
    db.flush()

    return {
        "tenant": tenant,
        "subscription": sub,
        "plan": plan,
        "role": role,
    }


class TestSubscriptionResolution:
    def test_valid_pointer_resolves_subscription(self, db: Session, setup_test_tenant):
        tenant = setup_test_tenant["tenant"]
        expected_sub = setup_test_tenant["subscription"]

        svc = SaaSEntitlementService(db)
        sub = svc.get_current_subscription(tenant.id)

        assert sub is not None
        assert sub.id == expected_sub.id
        assert sub.tenant_id == tenant.id

    def test_null_pointer_fails_closed(self, db: Session, setup_test_tenant):
        tenant = setup_test_tenant["tenant"]
        tenant.current_subscription_id = None
        db.flush()

        svc = SaaSEntitlementService(db)
        with pytest.raises(ForbiddenException) as exc:
            svc.get_current_subscription(tenant.id)
        assert "no authoritative current subscription" in str(exc.value.detail)

    def test_nonexistent_tenant_fails(self, db: Session):
        svc = SaaSEntitlementService(db)
        with pytest.raises(NotFoundException) as exc:
            svc.get_current_subscription(99999999)
        assert "not found" in str(exc.value.detail)

    def test_missing_referenced_subscription_fails_closed(self, db: Session, setup_test_tenant):
        tenant = setup_test_tenant["tenant"]
        tenant.current_subscription_id = 99999999
        db.flush()

        svc = SaaSEntitlementService(db)
        with pytest.raises(ForbiddenException) as exc:
            svc.get_current_subscription(tenant.id)
        assert "pointed by tenant" in str(exc.value.detail)

    def test_cross_tenant_mismatch_fails_closed(self, db: Session, setup_test_tenant, unique_suffix):
        # Create a second tenant
        other_tenant = Tenant(
            name=f"Other Corp {unique_suffix}",
            domain=f"other-{unique_suffix}.test",
            is_active=True,
        )
        db.add(other_tenant)
        db.flush()

        # Point first tenant to other tenant's subscription
        tenant = setup_test_tenant["tenant"]
        sub = setup_test_tenant["subscription"]
        other_tenant.current_subscription_id = sub.id
        db.flush()

        svc = SaaSEntitlementService(db)
        with pytest.raises(ForbiddenException) as exc:
            svc.get_current_subscription(other_tenant.id)
        assert "Security violation" in str(exc.value.detail)


class TestEntitlementResolution:
    def test_resolves_entitlement_by_dimension(self, db: Session, setup_test_tenant):
        tenant = setup_test_tenant["tenant"]
        plan = setup_test_tenant["plan"]

        ent = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.USERS,
            value=10,
            is_unlimited=False,
        )
        db.add(ent)
        db.flush()

        svc = SaaSEntitlementService(db)
        res = svc.get_entitlement(tenant.id, EntitlementDimension.USERS)

        assert res.id == ent.id
        assert res.dimension == EntitlementDimension.USERS
        assert res.value == 10
        assert res.is_unlimited is False

    def test_missing_dimension_fails_closed(self, db: Session, setup_test_tenant):
        tenant = setup_test_tenant["tenant"]
        svc = SaaSEntitlementService(db)

        with pytest.raises(ForbiddenException) as exc:
            svc.get_entitlement(tenant.id, "unconfigured_dimension")
        assert "not configured for plan" in str(exc.value.detail)

    def test_unlimited_entitlement_works(self, db: Session, setup_test_tenant):
        tenant = setup_test_tenant["tenant"]
        plan = setup_test_tenant["plan"]

        ent = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.STORES,
            value=None,
            is_unlimited=True,
        )
        db.add(ent)
        db.flush()

        svc = SaaSEntitlementService(db)
        limit, is_unlimited = svc.get_limit(tenant.id, EntitlementDimension.STORES)

        assert limit is None
        assert is_unlimited is True

    def test_finite_entitlement_with_null_value_fails_closed(self, db: Session, setup_test_tenant):
        tenant = setup_test_tenant["tenant"]
        plan = setup_test_tenant["plan"]

        ent = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.PRODUCTS,
            value=None,
            is_unlimited=False,
        )
        db.add(ent)
        db.flush()

        svc = SaaSEntitlementService(db)
        with pytest.raises(ForbiddenException) as exc:
            svc.get_entitlement(tenant.id, EntitlementDimension.PRODUCTS)
        assert "invalid limit value" in str(exc.value.detail)


class TestResourceUsageQueries:
    def test_users_usage_counts_correctly(self, db: Session, setup_test_tenant, unique_suffix):
        tenant = setup_test_tenant["tenant"]
        role = setup_test_tenant["role"]

        # 2 active, non-deleted users
        u1 = User(
            tenant_id=tenant.id,
            role_id=role.id,
            email=f"u1_{unique_suffix}@test.com",
            password_hash="pw",
            full_name="Active One",
            is_active=True,
            is_deleted=False,
        )
        u2 = User(
            tenant_id=tenant.id,
            role_id=role.id,
            email=f"u2_{unique_suffix}@test.com",
            password_hash="pw",
            full_name="Active Two",
            is_active=True,
            is_deleted=False,
        )
        # Inactive user
        u3 = User(
            tenant_id=tenant.id,
            role_id=role.id,
            email=f"u3_{unique_suffix}@test.com",
            password_hash="pw",
            full_name="Inactive User",
            is_active=False,
            is_deleted=False,
        )
        # Soft-deleted user
        u4 = User(
            tenant_id=tenant.id,
            role_id=role.id,
            email=f"u4_{unique_suffix}@test.com",
            password_hash="pw",
            full_name="Deleted User",
            is_active=True,
            is_deleted=True,
        )
        db.add_all([u1, u2, u3, u4])
        db.flush()

        svc = SaaSEntitlementService(db)
        count = svc.get_usage(tenant.id, EntitlementDimension.USERS)
        assert count == 2

    def test_stores_usage_counts_correctly(self, db: Session, setup_test_tenant, unique_suffix):
        tenant = setup_test_tenant["tenant"]

        s1 = Store(
            tenant_id=tenant.id,
            name=f"Store 1 {unique_suffix}",
            code=f"S1-{unique_suffix[:4]}",
            is_active=True,
        )
        s2 = Store(
            tenant_id=tenant.id,
            name=f"Store 2 {unique_suffix}",
            code=f"S2-{unique_suffix[:4]}",
            is_active=False,  # Inactive
        )
        db.add_all([s1, s2])
        db.flush()

        svc = SaaSEntitlementService(db)
        count = svc.get_usage(tenant.id, EntitlementDimension.STORES)
        assert count == 1

    def test_products_usage_counts_correctly(self, db: Session, setup_test_tenant, unique_suffix):
        tenant = setup_test_tenant["tenant"]

        p1 = Product(
            tenant_id=tenant.id,
            name="Prod 1",
            sku=f"SKU1-{unique_suffix}",
            selling_price=Decimal("10.00"),
            is_active=True,
        )
        p2 = Product(
            tenant_id=tenant.id,
            name="Prod 2",
            sku=f"SKU2-{unique_suffix}",
            selling_price=Decimal("20.00"),
            is_active=False,  # Inactive
        )
        db.add_all([p1, p2])
        db.flush()

        svc = SaaSEntitlementService(db)
        count = svc.get_usage(tenant.id, EntitlementDimension.PRODUCTS)
        assert count == 1

    def test_monthly_orders_usage_boundaries_and_status(self, db: Session, setup_test_tenant, unique_suffix):
        tenant = setup_test_tenant["tenant"]
        sub = setup_test_tenant["subscription"]

        s = Store(
            tenant_id=tenant.id,
            name=f"Store O {unique_suffix}",
            code=f"SO-{unique_suffix[:4]}",
            is_active=True,
        )
        db.add(s)
        db.flush()

        # Valid order inside billing period
        o1 = Order(
            tenant_id=tenant.id,
            store_id=s.id,
            order_number=f"ORD-1-{unique_suffix}",
            status="completed",
            created_at=sub.current_period_start + timedelta(days=1),
        )
        # Cancelled order inside billing period (should be excluded)
        o2 = Order(
            tenant_id=tenant.id,
            store_id=s.id,
            order_number=f"ORD-2-{unique_suffix}",
            status="cancelled",
            created_at=sub.current_period_start + timedelta(days=2),
        )
        # Order before period start (excluded)
        o3 = Order(
            tenant_id=tenant.id,
            store_id=s.id,
            order_number=f"ORD-3-{unique_suffix}",
            status="completed",
            created_at=sub.current_period_start - timedelta(days=2),
        )
        # Order after period end (excluded)
        o4 = Order(
            tenant_id=tenant.id,
            store_id=s.id,
            order_number=f"ORD-4-{unique_suffix}",
            status="completed",
            created_at=sub.current_period_end + timedelta(days=2),
        )
        db.add_all([o1, o2, o3, o4])
        db.flush()

        svc = SaaSEntitlementService(db)
        count = svc.get_usage(tenant.id, EntitlementDimension.MONTHLY_ORDERS)
        assert count == 1


class TestQuotaEnforcement:
    def test_within_limit_allowed(self, db: Session, setup_test_tenant, unique_suffix):
        tenant = setup_test_tenant["tenant"]
        plan = setup_test_tenant["plan"]

        ent = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.USERS,
            value=3,
            is_unlimited=False,
        )
        db.add(ent)
        db.flush()

        svc = SaaSEntitlementService(db)
        # Current usage: 0, requested: 1, limit: 3 -> allowed
        check = svc.check_limit(tenant.id, EntitlementDimension.USERS, requested_amount=1)
        assert check["allowed"] is True
        assert check["current_usage"] == 0
        assert check["limit"] == 3

        # require_limit does not raise
        svc.require_limit(tenant.id, EntitlementDimension.USERS, requested_amount=1)

    def test_at_limit_rejects_additional_request(self, db: Session, setup_test_tenant, unique_suffix):
        tenant = setup_test_tenant["tenant"]
        plan = setup_test_tenant["plan"]
        role = setup_test_tenant["role"]

        ent = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.USERS,
            value=1,
            is_unlimited=False,
        )
        db.add(ent)

        u = User(
            tenant_id=tenant.id,
            role_id=role.id,
            email=f"limit_user_{unique_suffix}@test.com",
            password_hash="pw",
            full_name="Limit User",
            is_active=True,
            is_deleted=False,
        )
        db.add(u)
        db.flush()

        svc = SaaSEntitlementService(db)
        check = svc.check_limit(tenant.id, EntitlementDimension.USERS, requested_amount=1)
        assert check["allowed"] is False
        assert check["current_usage"] == 1
        assert check["limit"] == 1

        with pytest.raises(QuotaExceededException) as exc:
            svc.require_limit(tenant.id, EntitlementDimension.USERS, requested_amount=1)

        err = exc.value
        assert err.status_code == 403
        assert err.dimension == EntitlementDimension.USERS
        assert err.current_usage == 1
        assert err.limit == 1
        assert err.requested == 1
        assert err.detail["error_code"] == "QUOTA_EXCEEDED"

    def test_unlimited_always_allowed(self, db: Session, setup_test_tenant):
        tenant = setup_test_tenant["tenant"]
        plan = setup_test_tenant["plan"]

        ent = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.STORES,
            value=None,
            is_unlimited=True,
        )
        db.add(ent)
        db.flush()

        svc = SaaSEntitlementService(db)
        check = svc.check_limit(tenant.id, EntitlementDimension.STORES, requested_amount=500)
        assert check["allowed"] is True
        assert check["is_unlimited"] is True

        # require_limit succeeds
        svc.require_limit(tenant.id, EntitlementDimension.STORES, requested_amount=500)

    def test_bulk_request_enforcement(self, db: Session, setup_test_tenant):
        tenant = setup_test_tenant["tenant"]
        plan = setup_test_tenant["plan"]

        ent = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.PRODUCTS,
            value=10,
            is_unlimited=False,
        )
        db.add(ent)
        db.flush()

        svc = SaaSEntitlementService(db)
        # Usage 0, requested 10 -> allowed
        check_ok = svc.check_limit(tenant.id, EntitlementDimension.PRODUCTS, requested_amount=10)
        assert check_ok["allowed"] is True

        # Usage 0, requested 11 -> rejected
        check_fail = svc.check_limit(tenant.id, EntitlementDimension.PRODUCTS, requested_amount=11)
        assert check_fail["allowed"] is False

    def test_invalid_requested_amount_fails(self, db: Session, setup_test_tenant):
        tenant = setup_test_tenant["tenant"]
        svc = SaaSEntitlementService(db)

        with pytest.raises(AppException) as exc:
            svc.check_limit(tenant.id, EntitlementDimension.USERS, requested_amount=0)
        assert "greater than 0" in str(exc.value.detail)


class TestSubscriptionStatusGating:
    @pytest.mark.parametrize("status", ["trialing", "active", "past_due"])
    def test_operational_statuses_permit_quota_check(self, db: Session, setup_test_tenant, status):
        tenant = setup_test_tenant["tenant"]
        sub = setup_test_tenant["subscription"]
        plan = setup_test_tenant["plan"]

        sub.status = status
        ent = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.USERS,
            value=5,
            is_unlimited=False,
        )
        db.add(ent)
        db.flush()

        svc = SaaSEntitlementService(db)
        check = svc.check_limit(tenant.id, EntitlementDimension.USERS)
        assert check["allowed"] is True

    @pytest.mark.parametrize("status", ["expired", "cancelled"])
    def test_restricted_statuses_deny_resource_creation(self, db: Session, setup_test_tenant, status):
        tenant = setup_test_tenant["tenant"]
        sub = setup_test_tenant["subscription"]
        plan = setup_test_tenant["plan"]

        sub.status = status
        ent = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.USERS,
            value=5,
            is_unlimited=False,
        )
        db.add(ent)
        db.flush()

        svc = SaaSEntitlementService(db)
        with pytest.raises(ForbiddenException) as exc:
            svc.check_limit(tenant.id, EntitlementDimension.USERS)
        assert f"Subscription status '{status}' does not permit operational resource creation" in str(exc.value.detail)

        with pytest.raises(ForbiddenException):
            svc.require_limit(tenant.id, EntitlementDimension.USERS)


class TestConcurrencyAndTransactionIntegrity:
    def test_tenant_row_lock_foundation(self, db: Session, setup_test_tenant):
        tenant = setup_test_tenant["tenant"]
        plan = setup_test_tenant["plan"]

        ent = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.USERS,
            value=5,
            is_unlimited=False,
        )
        db.add(ent)
        db.flush()

        svc = SaaSEntitlementService(db)
        # Lock tenant inside active transaction
        locked_tenant = svc.acquire_tenant_lock(tenant.id)
        assert locked_tenant.id == tenant.id

        # Verify require_limit works with lock_tenant=True
        svc.require_limit(tenant.id, EntitlementDimension.USERS, lock_tenant=True)

    def test_entitlement_service_never_commits(self, db: Session, setup_test_tenant, unique_suffix):
        tenant = setup_test_tenant["tenant"]
        plan = setup_test_tenant["plan"]

        ent = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.USERS,
            value=5,
            is_unlimited=False,
        )
        db.add(ent)
        db.flush()

        svc = SaaSEntitlementService(db)
        # Add an uncommitted object to db session
        test_store = Store(
            tenant_id=tenant.id,
            name=f"Uncommitted Store {unique_suffix}",
            code=f"UC-{unique_suffix[:4]}",
            is_active=True,
        )
        db.add(test_store)

        # Run require_limit
        svc.require_limit(tenant.id, EntitlementDimension.USERS, lock_tenant=True)

        # Confirm test_store remains in session dirty/new state and transaction was NOT committed
        assert test_store in db.new or test_store in db.dirty or test_store.id is None


class TestSaleServiceTenantIsolation:
    def test_create_sale_cross_tenant_store_rejected(self, db: Session, setup_test_tenant, unique_suffix):
        tenant1 = setup_test_tenant["tenant"]

        # Create store belonging to tenant 1
        s1 = Store(
            tenant_id=tenant1.id,
            name=f"T1 Store {unique_suffix}",
            code=f"T1-{unique_suffix[:4]}",
            is_active=True,
        )
        db.add(s1)
        db.flush()

        # Create user belonging to another tenant (tenant 9999)
        u_other = User(
            tenant_id=9999,
            role_id=setup_test_tenant["role"].id,
            email=f"other_user_{unique_suffix}@test.com",
            password_hash="pw",
            full_name="Other Tenant",
            is_active=True,
        )

        sale_data = SaleCreate(
            store_id=s1.id,
            items=[SaleItemCreate(product_id=1, stock=1, discount=0)],
            payment_method="cash",
        )

        with pytest.raises(ValueError) as exc:
            SaleService.create_sale(db, sale_data, current_user=u_other)
        assert "Store does not belong to the user's tenant" in str(exc.value)

    def test_create_sale_nonexistent_store_rejected(self, db: Session):
        sale_data = SaleCreate(
            store_id=999999,
            items=[SaleItemCreate(product_id=1, stock=1, discount=0)],
            payment_method="cash",
        )
        with pytest.raises(ValueError) as exc:
            SaleService.create_sale(db, sale_data)
        assert "Store with id 999999 not found" in str(exc.value)
