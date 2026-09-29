from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.order import Order
from app.models.product import Product
from app.models.role import Role
from app.models.saas_billing import SaaSPlan, SaaSSubscription
from app.models.saas_plan_entitlement import EntitlementDimension, SaaSPlanEntitlement
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_test_tenant(prefix: str):
    clean = "".join([c for c in prefix if c.isalnum()]).lower() or "t"
    uid = uuid.uuid4().hex[:6]
    email = f"{clean}{uid}@example.com"
    password = "Password123!"
    phone = f"91{uuid.uuid4().int % 100000000:08d}"

    reg_payload = {
        "tenant_name": f"{clean} Tenant {uid}",
        "domain": f"{clean}-{uid}",
        "email": email,
        "admin_name": f"Admin {uid}",
        "password": password,
        "phone": phone,
    }
    r = client.post("/api/v1/auth/register", json=reg_payload)
    assert r.status_code == 200, f"Registration failed: {r.text}"
    tenant_id = r.json()["tenant_id"]

    login_r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_r.status_code == 200, f"Login failed: {login_r.text}"
    token = login_r.json()["access_token"]

    return {
        "tenant_id": tenant_id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
        "email": email,
    }


def seed_plan_entitlements(db: Session, plan_id: int):
    """Seed or update all standard dimensions for a test plan."""
    dimensions = [
        (EntitlementDimension.USERS, 10, False),
        (EntitlementDimension.STORES, 3, False),
        (EntitlementDimension.PRODUCTS, None, True),
        (EntitlementDimension.MONTHLY_ORDERS, 500, False),
    ]
    for dim, val, unlimited in dimensions:
        existing = (
            db.query(SaaSPlanEntitlement)
            .filter(
                SaaSPlanEntitlement.plan_id == plan_id,
                SaaSPlanEntitlement.dimension == dim,
            )
            .first()
        )
        if existing:
            existing.value = val
            existing.is_unlimited = unlimited
        else:
            ent = SaaSPlanEntitlement(
                plan_id=plan_id,
                dimension=dim,
                value=val,
                is_unlimited=unlimited,
            )
            db.add(ent)
    db.commit()


class TestSaaSUsageApi:
    def test_anonymous_request_rejected(self):
        r = client.get("/api/v1/saas/usage")
        assert r.status_code == 401

    def test_tenant_authenticated_usage_success(self, db: Session):
        t = create_test_tenant("usg")
        tenant = db.query(Tenant).filter(Tenant.id == t["tenant_id"]).first()
        assert tenant.current_subscription_id is not None
        sub = db.query(SaaSSubscription).filter(SaaSSubscription.id == tenant.current_subscription_id).first()
        
        # Seed entitlements
        seed_plan_entitlements(db, sub.plan_id)

        # Create active store
        store = Store(
            tenant_id=tenant.id,
            name=f"Store-{uuid.uuid4().hex[:6]}",
            code=f"STR-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        db.add(store)

        # Create active product
        product = Product(
            tenant_id=tenant.id,
            name=f"Product-{uuid.uuid4().hex[:6]}",
            sku=f"SKU-{uuid.uuid4().hex[:6]}",
            selling_price=Decimal("100.00"),
            is_active=True,
        )
        db.add(product)

        # Create customer & order within current period
        customer = Customer(
            tenant_id=tenant.id,
            name="Test Customer",
            phone=f"9{uuid.uuid4().int % 1000000000:09d}",
        )
        db.add(customer)
        db.flush()

        order = Order(
            tenant_id=tenant.id,
            customer_id=customer.id,
            store_id=store.id,
            order_number=f"ORD-{uuid.uuid4().hex[:6]}",
            total_amount=Decimal("100.00"),
            status="completed",
            created_at=datetime.utcnow(),
        )
        db.add(order)
        db.commit()

        # Query GET /api/v1/saas/usage
        r = client.get("/api/v1/saas/usage", headers=t["headers"])
        assert r.status_code == 200, f"Usage API failed: {r.text}"
        data = r.json()

        assert data["tenant_id"] == tenant.id
        assert data["plan_id"] == sub.plan_id
        assert data["subscription_status"] in ("trialing", "active")
        assert len(data["items"]) == 4

        dims = data["dimensions"]
        # Users: registration created 1 admin user
        assert dims["users"]["dimension"] == "users"
        assert dims["users"]["current_usage"] >= 1
        assert dims["users"]["limit"] == 10
        assert dims["users"]["is_unlimited"] is False

        # Stores: 1 active store created
        assert dims["stores"]["dimension"] == "stores"
        assert dims["stores"]["current_usage"] == 1
        assert dims["stores"]["limit"] == 3
        assert dims["stores"]["is_unlimited"] is False

        # Products: 1 active product created, is_unlimited=True
        assert dims["products"]["dimension"] == "products"
        assert dims["products"]["current_usage"] == 1
        assert dims["products"]["limit"] is None
        assert dims["products"]["is_unlimited"] is True

        # Monthly orders: 1 order created in cycle
        assert dims["monthly_orders"]["dimension"] == "monthly_orders"
        assert dims["monthly_orders"]["current_usage"] == 1
        assert dims["monthly_orders"]["limit"] == 500
        assert dims["monthly_orders"]["is_unlimited"] is False

    def test_tenant_isolation_cannot_view_another_tenant_usage(self, db: Session):
        t1 = create_test_tenant("iso1")
        t2 = create_test_tenant("iso2")

        sub1 = db.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == t1["tenant_id"]).first()
        sub2 = db.query(SaaSSubscription).filter(SaaSSubscription.tenant_id == t2["tenant_id"]).first()
        seed_plan_entitlements(db, sub1.plan_id)
        seed_plan_entitlements(db, sub2.plan_id)

        # Tenant 1 adds a store
        st1 = Store(tenant_id=t1["tenant_id"], name="T1 Store", code=f"S1-{uuid.uuid4().hex[:4]}", is_active=True)
        db.add(st1)
        db.commit()

        # Tenant 2 calls /usage with a malicious query parameter ?tenant_id=t1["tenant_id"]
        r = client.get(f"/api/v1/saas/usage?tenant_id={t1['tenant_id']}", headers=t2["headers"])
        assert r.status_code == 200
        data = r.json()
        # MUST return Tenant 2's usage, NEVER Tenant 1's usage!
        assert data["tenant_id"] == t2["tenant_id"]
        assert data["dimensions"]["stores"]["current_usage"] == 0

    def test_usage_fails_closed_when_subscription_pointer_missing(self, db: Session):
        t = create_test_tenant("nosub")
        tenant = db.query(Tenant).filter(Tenant.id == t["tenant_id"]).first()
        tenant.current_subscription_id = None
        db.commit()

        r = client.get("/api/v1/saas/usage", headers=t["headers"])
        assert r.status_code in (402, 403)
        body = r.json()
        assert "no authoritative current subscription" in str(body).lower()

    def test_usage_fails_closed_when_entitlement_missing(self, db: Session):
        t = create_test_tenant("noent")
        tenant = db.query(Tenant).filter(Tenant.id == t["tenant_id"]).first()
        sub = db.query(SaaSSubscription).filter(SaaSSubscription.id == tenant.current_subscription_id).first()

        # Delete all entitlements for this plan
        db.query(SaaSPlanEntitlement).filter(SaaSPlanEntitlement.plan_id == sub.plan_id).delete()
        db.commit()

        r = client.get("/api/v1/saas/usage", headers=t["headers"])
        assert r.status_code in (402, 403)
        body = r.json()
        assert "not configured" in str(body).lower()

    def test_usage_fails_closed_when_entitlement_invalid(self, db: Session):
        t = create_test_tenant("inval")
        tenant = db.query(Tenant).filter(Tenant.id == t["tenant_id"]).first()
        sub = db.query(SaaSSubscription).filter(SaaSSubscription.id == tenant.current_subscription_id).first()

        seed_plan_entitlements(db, sub.plan_id)
        # Corrupt one entitlement: is_unlimited=False with value=None
        ent = (
            db.query(SaaSPlanEntitlement)
            .filter(
                SaaSPlanEntitlement.plan_id == sub.plan_id,
                SaaSPlanEntitlement.dimension == EntitlementDimension.USERS,
            )
            .first()
        )
        ent.is_unlimited = False
        ent.value = None
        db.commit()

        r = client.get("/api/v1/saas/usage", headers=t["headers"])
        assert r.status_code in (402, 403)
        body = r.json()
        assert "invalid limit value" in str(body).lower()
