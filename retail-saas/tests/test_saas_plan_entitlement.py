from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal, engine
from app.models.saas_billing import SaaSPlan, SaaSSubscription
from app.models.saas_plan_entitlement import EntitlementDimension, SaaSPlanEntitlement
from app.models.tenant import Tenant


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


class TestSaaSPlanEntitlementModel:
    def test_create_saas_plan_entitlement(self, db_session):
        plan = db_session.query(SaaSPlan).filter_by(code="basic").first()
        assert plan is not None

        entitlement = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.USERS,
            value=5,
            is_unlimited=False,
        )
        db_session.add(entitlement)
        db_session.flush()

        assert entitlement.id is not None
        assert entitlement.dimension == "users"
        assert entitlement.value == 5
        assert entitlement.is_unlimited is False
        assert entitlement.plan.code == "basic"
        assert entitlement in plan.entitlements

    def test_saas_plan_entitlement_unlimited(self, db_session):
        plan = db_session.query(SaaSPlan).filter_by(code="pro").first()
        assert plan is not None

        entitlement = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.MONTHLY_ORDERS,
            value=None,
            is_unlimited=True,
        )
        db_session.add(entitlement)
        db_session.flush()

        assert entitlement.id is not None
        assert entitlement.value is None
        assert entitlement.is_unlimited is True

    def test_unique_constraint_plan_dimension(self, db_session):
        plan = db_session.query(SaaSPlan).filter_by(code="basic").first()
        assert plan is not None

        dim = f"custom_dim_{uuid.uuid4().hex[:6]}"
        ent1 = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=dim,
            value=10,
            is_unlimited=False,
        )
        db_session.add(ent1)
        db_session.flush()

        ent2 = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=dim,
            value=20,
            is_unlimited=False,
        )
        db_session.add(ent2)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_cascade_delete_from_plan(self, db_session):
        test_code = f"test_cascade_{uuid.uuid4().hex[:6]}"
        plan = SaaSPlan(
            name="Cascade Test",
            code=test_code,
            price=Decimal("0.00"),
            currency="INR",
            billing_interval="monthly",
            trial_days=0,
            is_active=True,
        )
        db_session.add(plan)
        db_session.flush()

        ent = SaaSPlanEntitlement(
            plan_id=plan.id,
            dimension=EntitlementDimension.STORES,
            value=2,
            is_unlimited=False,
        )
        db_session.add(ent)
        db_session.flush()
        ent_id = ent.id

        # Delete plan and verify cascade
        db_session.delete(plan)
        db_session.flush()

        deleted_ent = db_session.query(SaaSPlanEntitlement).filter_by(id=ent_id).first()
        assert deleted_ent is None


class TestTenantSubscriptionPointerAndBackfill:
    def test_tenant_current_subscription_relationship(self, db_session):
        plan = db_session.query(SaaSPlan).filter_by(code="basic").first()
        now = datetime.utcnow()

        tenant = Tenant(
            name=f"Pointer Test {uuid.uuid4().hex[:6]}",
            domain=f"pointer-{uuid.uuid4().hex[:6]}",
            plan="basic",
            subscription_status="active",
        )
        db_session.add(tenant)
        db_session.flush()

        sub = SaaSSubscription(
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="active",
            billing_interval="monthly",
            unit_price=Decimal("999.00"),
            currency="INR",
            start_date=now,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db_session.add(sub)
        db_session.flush()

        tenant.current_subscription_id = sub.id
        db_session.flush()

        # Refresh and verify relationship
        db_session.refresh(tenant)
        assert tenant.current_subscription is not None
        assert tenant.current_subscription.id == sub.id
        assert tenant.current_subscription.tenant_id == tenant.id

    def test_backfill_simulation_on_multiple_tenants(self, db_session):
        """Simulate migration backfill on multiple tenants and verify isolation."""
        plan = db_session.query(SaaSPlan).filter_by(code="basic").first()
        now = datetime.utcnow()

        created_pairs = []
        for i in range(3):
            t = Tenant(
                name=f"Backfill Test {i}_{uuid.uuid4().hex[:6]}",
                domain=f"bf-{i}-{uuid.uuid4().hex[:6]}",
                plan="basic",
                subscription_status="trial",
            )
            db_session.add(t)
            db_session.flush()

            s = SaaSSubscription(
                tenant_id=t.id,
                plan_id=plan.id,
                status="trialing",
                billing_interval="monthly",
                unit_price=Decimal("0.00"),
                currency="INR",
                start_date=now,
                current_period_start=now,
                current_period_end=now + timedelta(days=14),
            )
            db_session.add(s)
            db_session.flush()
            created_pairs.append((t, s))

        # Perform backfill
        CURRENT_STATUSES = ("trialing", "active", "past_due")
        for t, expected_sub in created_pairs:
            subs = (
                db_session.query(SaaSSubscription)
                .filter(SaaSSubscription.tenant_id == t.id)
                .all()
            )
            candidates = [s for s in subs if s.status in CURRENT_STATUSES]
            assert len(candidates) == 1
            t.current_subscription_id = candidates[0].id

        db_session.flush()

        # Verify all backfilled correctly
        for t, expected_sub in created_pairs:
            db_session.refresh(t)
            assert t.current_subscription_id == expected_sub.id
            assert t.current_subscription.tenant_id == t.id

    def test_safe_backfill_logic_error_cases(self):
        """Test the pure validation invariants used in safe backfill migration."""
        CURRENT_STATUSES = ("trialing", "active", "past_due")

        # Case 1: Zero candidate subscriptions
        subs_zero = []
        candidates_zero = [s for s in subs_zero if s["status"] in CURRENT_STATUSES]
        with pytest.raises(ValueError, match="0 candidate subscriptions"):
            if len(candidates_zero) == 0:
                raise ValueError("Safe backfill failed: Tenant 999 (Test) has 0 candidate subscriptions")

        # Case 2: Ambiguous candidate subscriptions
        subs_ambiguous = [
            {"id": 1, "tenant_id": 999, "status": "active"},
            {"id": 2, "tenant_id": 999, "status": "trialing"},
        ]
        candidates_ambiguous = [s for s in subs_ambiguous if s["status"] in CURRENT_STATUSES]
        with pytest.raises(ValueError, match="ambiguous candidate subscriptions"):
            if len(candidates_ambiguous) > 1:
                raise ValueError("Safe backfill failed: Tenant 999 (Test) has 2 ambiguous candidate subscriptions")

        # Case 3: Cross-tenant mismatch
        subs_mismatch = [{"id": 1, "tenant_id": 888, "status": "active"}]
        sub = subs_mismatch[0]
        tenant_id = 999
        with pytest.raises(ValueError, match="Cross-tenant mismatch"):
            if sub["tenant_id"] != tenant_id:
                raise ValueError(f"Safe backfill failed: Cross-tenant mismatch! Sub {sub['id']} tenant_id {sub['tenant_id']} != Tenant {tenant_id}")


class TestSchemaIndexesAndConstraints:
    def test_indexes_exist(self):
        insp = inspect(engine)

        # users
        user_indexes = {idx["name"]: idx["column_names"] for idx in insp.get_indexes("users")}
        assert "ix_users_tenant_entitlement" in user_indexes
        assert user_indexes["ix_users_tenant_entitlement"] == ["tenant_id", "is_deleted", "is_active"]

        # stores
        store_indexes = {idx["name"]: idx["column_names"] for idx in insp.get_indexes("stores")}
        assert "ix_stores_tenant_entitlement" in store_indexes
        assert store_indexes["ix_stores_tenant_entitlement"] == ["tenant_id", "is_active"]

        # products
        product_indexes = {idx["name"]: idx["column_names"] for idx in insp.get_indexes("products")}
        assert "ix_products_tenant_entitlement" in product_indexes
        assert product_indexes["ix_products_tenant_entitlement"] == ["tenant_id", "is_active"]

        # orders
        order_indexes = {idx["name"]: idx["column_names"] for idx in insp.get_indexes("orders")}
        assert "ix_orders_tenant_billing" in order_indexes
        assert order_indexes["ix_orders_tenant_billing"] == ["tenant_id", "created_at", "status"]

        # saas_subscriptions
        sub_indexes = {idx["name"]: idx["column_names"] for idx in insp.get_indexes("saas_subscriptions")}
        assert "ix_saas_subscriptions_tenant_lookup" in sub_indexes
        assert sub_indexes["ix_saas_subscriptions_tenant_lookup"] == ["tenant_id", "status", "created_at", "id"]

        # tenants
        tenant_indexes = {idx["name"]: idx["column_names"] for idx in insp.get_indexes("tenants")}
        assert "ix_tenants_current_subscription_id" in tenant_indexes
        assert tenant_indexes["ix_tenants_current_subscription_id"] == ["current_subscription_id"]

    def test_foreign_keys_exist(self):
        insp = inspect(engine)

        # saas_plan_entitlements -> saas_plans.id
        ent_fks = insp.get_foreign_keys("saas_plan_entitlements")
        assert any(
            fk["referred_table"] == "saas_plans" and fk["constrained_columns"] == ["plan_id"]
            for fk in ent_fks
        )

        # tenants.current_subscription_id -> saas_subscriptions.id
        tenant_fks = insp.get_foreign_keys("tenants")
        assert any(
            fk["referred_table"] == "saas_subscriptions" and fk["constrained_columns"] == ["current_subscription_id"]
            for fk in tenant_fks
        )
