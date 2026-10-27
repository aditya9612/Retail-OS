import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.review import Review
from app.models.role import Role
from app.models.store import Store
from app.models.storefront_setting import StorefrontSetting
from app.models.tenant import Tenant
from app.models.user import User

client = TestClient(app)


def create_tenant_setup(prefix: str):
    """Create tenant, admin user, store, active products, and active customers directly in DB."""
    db = SessionLocal()
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"

    tenant = Tenant(
        name=f"Tenant {slug}",
        domain=slug,
        is_active=True,
    )
    db.add(tenant)
    db.flush()

    role = Role(
        tenant_id=tenant.id,
        name="admin",
        permissions=["*"],
        is_system=True,
    )
    db.add(role)
    db.flush()

    user = User(
        tenant_id=tenant.id,
        role_id=role.id,
        email=f"owner-{slug}@example.com",
        password_hash="test-password-hash",
        full_name="Review Owner",
        is_active=True,
    )
    db.add(user)
    db.flush()

    store = Store(
        tenant_id=tenant.id,
        name=f"Store-{uuid.uuid4().hex[:4]}",
        address="123 Retail St",
        is_active=True,
        is_main=True,
    )
    db.add(store)
    db.flush()

    product = Product(
        tenant_id=tenant.id,
        name="Organic Almonds 500g",
        sku=f"ALM-{uuid.uuid4().hex[:6]}",
        selling_price=Decimal("450.00"),
        cost_price=Decimal("350.00"),
        is_active=True,
    )
    product2 = Product(
        tenant_id=tenant.id,
        name="Premium Cashews 500g",
        sku=f"CSH-{uuid.uuid4().hex[:6]}",
        selling_price=Decimal("550.00"),
        cost_price=Decimal("420.00"),
        is_active=True,
    )
    db.add_all([product, product2])

    customer = Customer(
        tenant_id=tenant.id,
        name="Aarav Sharma",
        phone=f"98{uuid.uuid4().int % 100000000:08d}",
        email=f"aarav-{uuid.uuid4().hex[:6]}@example.com",
        status="active",
    )
    customer2 = Customer(
        tenant_id=tenant.id,
        name="Priya Patil",
        phone=f"99{uuid.uuid4().int % 100000000:08d}",
        email=f"priya-{uuid.uuid4().hex[:6]}@example.com",
        status="active",
    )
    db.add_all([customer, customer2])
    db.commit()

    token = create_access_token({
        "sub": str(user.id),
        "tenant_id": tenant.id,
        "role": "admin",
        "store_id": store.id,
    })
    headers = {"Authorization": f"Bearer {token}"}

    res = {
        "tenant_id": tenant.id,
        "user_id": user.id,
        "headers": headers,
        "store_id": store.id,
        "product_id": product.id,
        "product2_id": product2.id,
        "customer_id": customer.id,
        "customer2_id": customer2.id,
    }
    db.close()
    return res


@pytest.fixture
def tenant_data():
    return create_tenant_setup("rev")


# ==============================================================================
# 1. CREATE REVIEW (PRODUCT & STORE)
# ==============================================================================

def test_create_product_review_success(tenant_data):
    """Customer leaves a 5-star review on a product."""
    payload = {
        "product_id": tenant_data["product_id"],
        "customer_id": tenant_data["customer_id"],
        "rating": 5,
        "comment": "Exceptional quality and crisp almonds!",
    }
    resp = client.post("/api/v1/reviews", json=payload, headers=tenant_data["headers"])
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["product_id"] == tenant_data["product_id"]
    assert data["customer_id"] == tenant_data["customer_id"]
    assert data["customer_name"] == "Aarav Sharma"
    assert data["product_name"] == "Organic Almonds 500g"
    assert data["rating"] == 5
    assert data["comment"] == "Exceptional quality and crisp almonds!"
    assert data["status"] == "approved"
    assert data["is_edited"] is False
    assert data["is_verified_purchase"] is False


def test_create_store_review_success(tenant_data):
    """Customer leaves feedback for a store outlet without a product."""
    payload = {
        "store_id": tenant_data["store_id"],
        "customer_id": tenant_data["customer_id"],
        "rating": 4,
        "comment": "Very friendly staff and quick billing experience.",
    }
    resp = client.post("/api/v1/reviews", json=payload, headers=tenant_data["headers"])
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["store_id"] == tenant_data["store_id"]
    assert data["product_id"] is None
    assert data["customer_name"] == "Aarav Sharma"
    assert data["rating"] == 4
    assert data["comment"] == "Very friendly staff and quick billing experience."


# ==============================================================================
# 2. VALIDATION FAILURES
# ==============================================================================

def test_create_review_validation_failures(tenant_data):
    """Missing target, invalid rating, invalid comments, and non-existent IDs."""
    headers = tenant_data["headers"]

    # Missing both product_id and store_id
    resp = client.post(
        "/api/v1/reviews",
        json={"customer_id": tenant_data["customer_id"], "rating": 5},
        headers=headers,
    )
    assert resp.status_code == 422

    # Rating < 1
    resp = client.post(
        "/api/v1/reviews",
        json={
            "product_id": tenant_data["product_id"],
            "customer_id": tenant_data["customer_id"],
            "rating": 0,
        },
        headers=headers,
    )
    assert resp.status_code == 422

    # Rating > 5
    resp = client.post(
        "/api/v1/reviews",
        json={
            "product_id": tenant_data["product_id"],
            "customer_id": tenant_data["customer_id"],
            "rating": 6,
        },
        headers=headers,
    )
    assert resp.status_code == 422

    # Comment only digits
    resp = client.post(
        "/api/v1/reviews",
        json={
            "product_id": tenant_data["product_id"],
            "customer_id": tenant_data["customer_id"],
            "rating": 5,
            "comment": "12345",
        },
        headers=headers,
    )
    assert resp.status_code == 422

    # Comment too short
    resp = client.post(
        "/api/v1/reviews",
        json={
            "product_id": tenant_data["product_id"],
            "customer_id": tenant_data["customer_id"],
            "rating": 5,
            "comment": "x",
        },
        headers=headers,
    )
    assert resp.status_code == 422

    # Non-existent customer
    resp = client.post(
        "/api/v1/reviews",
        json={
            "product_id": tenant_data["product_id"],
            "customer_id": 999999,
            "rating": 5,
        },
        headers=headers,
    )
    assert resp.status_code == 404

    # Non-existent product
    resp = client.post(
        "/api/v1/reviews",
        json={
            "product_id": 999999,
            "customer_id": tenant_data["customer_id"],
            "rating": 5,
        },
        headers=headers,
    )
    assert resp.status_code == 404


# ==============================================================================
# 3. DUPLICATE REVIEW PREVENTION
# ==============================================================================

def test_duplicate_review_prevention(tenant_data):
    """Customer cannot submit multiple active reviews for the same product or store."""
    headers = tenant_data["headers"]
    payload = {
        "product_id": tenant_data["product_id"],
        "customer_id": tenant_data["customer_id"],
        "rating": 4,
        "comment": "First review for product.",
    }
    resp1 = client.post("/api/v1/reviews", json=payload, headers=headers)
    assert resp1.status_code == 201

    # Second attempt by same customer for same product must return 409 Conflict
    resp2 = client.post("/api/v1/reviews", json=payload, headers=headers)
    assert resp2.status_code == 409
    assert "already submitted a review" in resp2.json()["detail"]


# ==============================================================================
# 4. STOREFRONT TOGGLE (ENABLE_PRODUCT_REVIEWS)
# ==============================================================================

def test_storefront_reviews_disabled_toggle(tenant_data):
    """When storefront setting disables reviews, product review creation must fail."""
    db = SessionLocal()
    try:
        setting = StorefrontSetting(
            tenant_id=tenant_data["tenant_id"],
            store_id=tenant_data["store_id"],
            enable_product_reviews=False,
        )
        db.add(setting)
        db.commit()
    finally:
        db.close()

    payload = {
        "product_id": tenant_data["product2_id"],
        "customer_id": tenant_data["customer2_id"],
        "store_id": tenant_data["store_id"],
        "rating": 5,
        "comment": "Trying to review when disabled.",
    }
    resp = client.post("/api/v1/reviews", json=payload, headers=tenant_data["headers"])
    assert resp.status_code == 400
    assert "disabled" in resp.json()["detail"].lower()


# ==============================================================================
# 5. VERIFIED PURCHASE DETECTION
# ==============================================================================

def test_verified_purchase_with_valid_and_invalid_order(tenant_data):
    """Customer with completed order gets verified badge; mismatch is rejected."""
    db = SessionLocal()
    try:
        # Create completed order with product_id
        order = Order(
            tenant_id=tenant_data["tenant_id"],
            store_id=tenant_data["store_id"],
            customer_id=tenant_data["customer_id"],
            order_number=f"ORD-{uuid.uuid4().hex[:6]}",
            status="completed",
            payment_status="paid",
            total_amount=Decimal("450.00"),
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        order_item = OrderItem(
            order_id=order.id,
            product_id=tenant_data["product2_id"],
            quantity=1,
            unit_price=Decimal("450.00"),
            total_amount=Decimal("450.00"),
        )
        db.add(order_item)
        db.commit()
        order_id = order.id
    finally:
        db.close()

    # 1. Invalid order check: Order does not contain product_id
    resp_invalid = client.post(
        "/api/v1/reviews",
        json={
            "product_id": tenant_data["product_id"],  # product_id is not in order (order has product2_id)
            "customer_id": tenant_data["customer_id"],
            "order_id": order_id,
            "rating": 5,
            "comment": "Testing invalid order product matching.",
        },
        headers=tenant_data["headers"],
    )
    assert resp_invalid.status_code == 400
    assert "does not contain product" in resp_invalid.json()["detail"]

    # 2. Valid verified purchase: Order contains product2_id
    resp_valid = client.post(
        "/api/v1/reviews",
        json={
            "product_id": tenant_data["product2_id"],
            "customer_id": tenant_data["customer_id"],
            "order_id": order_id,
            "rating": 5,
            "comment": "Verified purchase of almonds!",
        },
        headers=tenant_data["headers"],
    )
    assert resp_valid.status_code == 201
    assert resp_valid.json()["is_verified_purchase"] is True
    assert resp_valid.json()["order_id"] == order_id


# ==============================================================================
# 6. PAGINATION, FILTERS & RATINGS SUMMARY
# ==============================================================================

def test_reviews_pagination_and_star_filter(tenant_data):
    """List reviews with rating filter and pagination parameters."""
    headers = tenant_data["headers"]
    product_id = tenant_data["product_id"]

    # Add reviews from multiple customers
    db = SessionLocal()
    try:
        c3 = Customer(
            tenant_id=tenant_data["tenant_id"],
            name="Vikram Rao",
            phone=f"97{uuid.uuid4().int % 100000000:08d}",
            status="active",
        )
        c4 = Customer(
            tenant_id=tenant_data["tenant_id"],
            name="Sneha Kulkarni",
            phone=f"96{uuid.uuid4().int % 100000000:08d}",
            status="active",
        )
        db.add_all([c3, c4])
        db.commit()
        c3_id, c4_id = c3.id, c4.id
    finally:
        db.close()

    # Create 3 reviews on product_id with ratings 5, 5, 2
    client.post(
        "/api/v1/reviews",
        json={"product_id": product_id, "customer_id": tenant_data["customer_id"], "rating": 5, "comment": "Great!"},
        headers=headers,
    )
    client.post(
        "/api/v1/reviews",
        json={"product_id": product_id, "customer_id": c3_id, "rating": 5, "comment": "Awesome!"},
        headers=headers,
    )
    client.post(
        "/api/v1/reviews",
        json={"product_id": product_id, "customer_id": c4_id, "rating": 2, "comment": "Average packaging."},
        headers=headers,
    )

    # 1. Product reviews with star rating filter = 5
    resp_5 = client.get(
        f"/api/v1/reviews/product/{product_id}?rating=5",
        headers=headers,
    )
    assert resp_5.status_code == 200
    data_5 = resp_5.json()
    assert data_5["total"] == 2
    assert all(r["rating"] == 5 for r in data_5["items"])

    # 2. Product reviews pagination page_size=2
    resp_page = client.get(
        f"/api/v1/reviews/product/{product_id}?page=1&page_size=2",
        headers=headers,
    )
    assert resp_page.status_code == 200
    data_page = resp_page.json()
    assert data_page["total"] == 3
    assert len(data_page["items"]) == 2

    # 3. Product review summary & breakdown
    resp_summary = client.get(
        f"/api/v1/reviews/product/{product_id}/summary",
        headers=headers,
    )
    assert resp_summary.status_code == 200
    s_data = resp_summary.json()
    assert s_data["target_type"] == "product"
    assert s_data["target_id"] == product_id
    assert s_data["total_reviews"] == 3
    assert s_data["average_rating"] == 4.0  # (5+5+2)/3 = 4.0
    assert s_data["rating_breakdown"]["star_5"] == 2
    assert s_data["rating_breakdown"]["star_2"] == 1
    assert s_data["rating_breakdown"]["star_1"] == 0


def test_store_review_summary(tenant_data):
    """Store summary calculates total reviews and average rating."""
    headers = tenant_data["headers"]
    store_id = tenant_data["store_id"]

    client.post(
        "/api/v1/reviews",
        json={"store_id": store_id, "customer_id": tenant_data["customer2_id"], "rating": 4, "comment": "Nice store!"},
        headers=headers,
    )

    resp = client.get(f"/api/v1/reviews/store/{store_id}/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_type"] == "store"
    assert data["total_reviews"] == 1
    assert data["average_rating"] == 4.0
    assert data["rating_breakdown"]["star_4"] == 1


# ==============================================================================
# 7. UPDATE & SOFT DELETE REVIEW
# ==============================================================================

def test_update_review_and_soft_delete(tenant_data):
    """Update review text/rating, then soft delete and ensure it is omitted from queries."""
    headers = tenant_data["headers"]

    create_resp = client.post(
        "/api/v1/reviews",
        json={
            "product_id": tenant_data["product_id"],
            "customer_id": tenant_data["customer_id"],
            "rating": 3,
            "comment": "Initial rating was okay.",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    rev_id = create_resp.json()["id"]

    # 1. Update review
    update_resp = client.patch(
        f"/api/v1/reviews/{rev_id}",
        json={"rating": 4, "comment": "Updated after second use, much better!"},
        headers=headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["rating"] == 4
    assert update_resp.json()["is_edited"] is True

    # 2. Soft delete review
    del_resp = client.delete(f"/api/v1/reviews/{rev_id}", headers=headers)
    assert del_resp.status_code == 204

    # 3. GET after deletion must return 404
    get_resp = client.get(f"/api/v1/reviews/{rev_id}", headers=headers)
    assert get_resp.status_code == 404


# ==============================================================================
# 8. MERCHANT REPLY & STATUS MODERATION
# ==============================================================================

def test_merchant_reply_to_review(tenant_data):
    """Store merchant replies to a customer review."""
    headers = tenant_data["headers"]

    create_resp = client.post(
        "/api/v1/reviews",
        json={
            "product_id": tenant_data["product_id"],
            "customer_id": tenant_data["customer_id"],
            "rating": 4,
            "comment": "Good taste, prompt delivery.",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    rev_id = create_resp.json()["id"]

    reply_resp = client.post(
        f"/api/v1/reviews/{rev_id}/reply",
        json={"merchant_reply": "Thank you for shopping with us! We appreciate your feedback."},
        headers=headers,
    )
    assert reply_resp.status_code == 200
    r_data = reply_resp.json()
    assert r_data["merchant_reply"] == "Thank you for shopping with us! We appreciate your feedback."
    assert r_data["replied_at"] is not None
    assert r_data["replied_by"] == tenant_data["user_id"]


def test_update_review_status_moderation(tenant_data):
    """Admin can change review status to hidden or approved."""
    headers = tenant_data["headers"]

    create_resp = client.post(
        "/api/v1/reviews",
        json={
            "product_id": tenant_data["product_id"],
            "customer_id": tenant_data["customer_id"],
            "rating": 1,
            "comment": "Abusive or inappropriate text sample.",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    rev_id = create_resp.json()["id"]

    status_resp = client.patch(
        f"/api/v1/reviews/{rev_id}/status",
        json={"status": "hidden"},
        headers=headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "hidden"

