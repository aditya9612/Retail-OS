import random
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.inventory import Inventory
from app.core.database import SessionLocal

client = TestClient(app)


def _gen_phone():
    return f"9{random.randint(100000000, 999999999)}"


@pytest.fixture
def store_security_fixture(unique_slug):
    suffix = uuid.uuid4().hex[:6]
    owner_email = f"owner_{unique_slug}_{suffix}@secstore.com"
    owner_pass = "OwnerPass@123!"

    # 1. Register Tenant A
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Security Mart {suffix}",
            "domain": f"{unique_slug}-{suffix}",
            "owner_email": owner_email,
            "owner_name": "Security Owner",
            "password": owner_pass,
            "owner_phone": _gen_phone(),
            "plan_code": "enterprise",
        },
    )
    assert reg_res.status_code == 200, reg_res.text
    tenant_a_id = reg_res.json()["tenant_id"]

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": owner_email, "password": owner_pass},
    )
    assert login_res.status_code == 200
    owner_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # 2. Create Store 1 & Store 2
    s1_res = client.post(
        "/api/v1/stores/",
        headers=owner_headers,
        json={"name": f"Store Alpha {suffix}", "code": f"SA{suffix[:3].upper()}"},
    )
    assert s1_res.status_code == 201, s1_res.text
    store1_id = s1_res.json()["id"]

    s2_res = client.post(
        "/api/v1/stores/",
        headers=owner_headers,
        json={"name": f"Store Beta {suffix}", "code": f"SB{suffix[:3].upper()}"},
    )
    assert s2_res.status_code == 201, s2_res.text
    store2_id = s2_res.json()["id"]

    # 3. Create Products for Store 1 and Store 2
    p1_res = client.post(
        "/api/v1/products/",
        headers=owner_headers,
        json={
            "name": f"Alpha Product {suffix}",
            "sku": f"SKU-A-{suffix}",
            "price": "100.00",
            "gst_rate": "18.00",
            "hsn_code": "8471",
        },
    )
    assert p1_res.status_code == 201, p1_res.text
    product1_id = p1_res.json()["id"]

    p2_res = client.post(
        "/api/v1/products/",
        headers=owner_headers,
        json={
            "name": f"Beta Product {suffix}",
            "sku": f"SKU-B-{suffix}",
            "price": "150.00",
            "gst_rate": "18.00",
            "hsn_code": "8471",
        },
    )
    assert p2_res.status_code == 201, p2_res.text
    product2_id = p2_res.json()["id"]

    # Stock-in inventory
    client.post(
        "/api/v1/inventory/stock-in",
        headers=owner_headers,
        json={"store_id": store1_id, "product_id": product1_id, "quantity": 100},
    )
    client.post(
        "/api/v1/inventory/stock-in",
        headers=owner_headers,
        json={"store_id": store2_id, "product_id": product2_id, "quantity": 100},
    )

    # 4. Create Cashier 1 (assigned to Store 1) and Cashier 2 (assigned to Store 2)
    c1_email = f"cashier1_{suffix}@secstore.com"
    c1_pass = "CashierPass1@123!"
    u1_res = client.post(
        "/api/v1/users",
        headers=owner_headers,
        data={
            "email": c1_email,
            "full_name": "Cashier Alpha",
            "password": c1_pass,
            "role": "cashier",
            "phone": _gen_phone(),
        },
    )
    assert u1_res.status_code == 201, u1_res.text
    cashier1_user_id = u1_res.json()["id"]

    assign1 = client.patch(
        f"/api/v1/users/{cashier1_user_id}/assign-store",
        headers=owner_headers,
        json={"store_id": store1_id},
    )
    assert assign1.status_code == 200, assign1.text

    c1_login = client.post(
        "/api/v1/auth/login",
        json={"email": c1_email, "password": c1_pass},
    )
    assert c1_login.status_code == 200
    cashier1_headers = {"Authorization": f"Bearer {c1_login.json()['access_token']}"}

    c2_email = f"cashier2_{suffix}@secstore.com"
    c2_pass = "CashierPass2@123!"
    u2_res = client.post(
        "/api/v1/users",
        headers=owner_headers,
        data={
            "email": c2_email,
            "full_name": "Cashier Beta",
            "password": c2_pass,
            "role": "cashier",
            "phone": _gen_phone(),
        },
    )
    assert u2_res.status_code == 201, u2_res.text
    cashier2_user_id = u2_res.json()["id"]

    assign2 = client.patch(
        f"/api/v1/users/{cashier2_user_id}/assign-store",
        headers=owner_headers,
        json={"store_id": store2_id},
    )
    assert assign2.status_code == 200, assign2.text

    c2_login = client.post(
        "/api/v1/auth/login",
        json={"email": c2_email, "password": c2_pass},
    )
    assert c2_login.status_code == 200
    cashier2_headers = {"Authorization": f"Bearer {c2_login.json()['access_token']}"}

    # 5. Generate Invoice 1 for Store 1 (by Cashier 1)
    inv1_res = client.post(
        "/api/v1/invoices",
        headers=cashier1_headers,
        json={
            "store_id": store1_id,
            "items": [{"product_id": product1_id, "quantity": 1}],
            "payments": [{"payment_mode": "cash", "amount": "118.00"}],
        },
    )
    assert inv1_res.status_code == 201, inv1_res.text
    invoice1_id = inv1_res.json()["id"]
    invoice1_number = inv1_res.json()["invoice_number"]

    # 6. Generate Invoice 2 for Store 2 (by Cashier 2)
    inv2_res = client.post(
        "/api/v1/invoices",
        headers=cashier2_headers,
        json={
            "store_id": store2_id,
            "items": [{"product_id": product2_id, "quantity": 1}],
            "payments": [{"payment_mode": "cash", "amount": "177.00"}],
        },
    )
    assert inv2_res.status_code == 201, inv2_res.text
    invoice2_id = inv2_res.json()["id"]
    invoice2_number = inv2_res.json()["invoice_number"]

    # 7. Register a completely distinct Tenant B
    b_suffix = uuid.uuid4().hex[:6]
    b_email = f"owner_b_{unique_slug}_{b_suffix}@tenb.com"
    b_pass = "TenantBPass@123!"
    b_reg = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Tenant B Mart {b_suffix}",
            "domain": f"tenb-{unique_slug}-{b_suffix}",
            "owner_email": b_email,
            "owner_name": "Tenant B Owner",
            "password": b_pass,
            "owner_phone": _gen_phone(),
            "plan_code": "enterprise",
        },
    )
    assert b_reg.status_code == 200, b_reg.text
    b_login = client.post(
        "/api/v1/auth/login",
        json={"email": b_email, "password": b_pass},
    )
    assert b_login.status_code == 200
    tenant_b_headers = {"Authorization": f"Bearer {b_login.json()['access_token']}"}

    return {
        "tenant_a_id": tenant_a_id,
        "owner_headers": owner_headers,
        "store1_id": store1_id,
        "store2_id": store2_id,
        "product1_id": product1_id,
        "product2_id": product2_id,
        "cashier1_headers": cashier1_headers,
        "cashier2_headers": cashier2_headers,
        "invoice1_id": invoice1_id,
        "invoice1_number": invoice1_number,
        "invoice2_id": invoice2_id,
        "invoice2_number": invoice2_number,
        "tenant_b_headers": tenant_b_headers,
    }


def test_authorized_same_store_invoice_detail(store_security_fixture):
    """Cashier 1 assigned to Store 1 can view Store 1 invoice detail."""
    ctx = store_security_fixture
    res = client.get(
        f"/api/v1/invoices/{ctx['invoice1_id']}",
        headers=ctx["cashier1_headers"],
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == ctx["invoice1_id"]
    assert data["store_id"] == ctx["store1_id"]
    assert data["invoice_number"] == ctx["invoice1_number"]


def test_unauthorized_cross_store_invoice_detail_forbidden(store_security_fixture):
    """Cashier 1 assigned to Store 1 cannot view Store 2 invoice detail (403 Forbidden)."""
    ctx = store_security_fixture
    res = client.get(
        f"/api/v1/invoices/{ctx['invoice2_id']}",
        headers=ctx["cashier1_headers"],
    )
    assert res.status_code == 403
    data = res.json()
    # Ensure error response does not leak sensitive Store 2 invoice data
    err_text = str(data)
    assert ctx["invoice2_number"] not in err_text
    assert "Beta" not in err_text


def test_unauthorized_cross_store_invoice_pdf_forbidden(store_security_fixture):
    """Cashier 1 assigned to Store 1 cannot download or preview Store 2 invoice PDF (403 Forbidden)."""
    ctx = store_security_fixture
    res = client.get(
        f"/api/v1/invoices/{ctx['invoice2_id']}/pdf",
        headers=ctx["cashier1_headers"],
    )
    assert res.status_code == 403
    assert b"%PDF" not in res.content


def test_unauthorized_cross_store_invoice_reprint_forbidden(store_security_fixture):
    """Cashier 1 assigned to Store 1 cannot reprint Store 2 invoice (403 Forbidden)."""
    ctx = store_security_fixture
    res = client.post(
        f"/api/v1/invoices/{ctx['invoice2_id']}/reprint",
        headers=ctx["cashier1_headers"],
    )
    assert res.status_code == 403


def test_unauthorized_cross_store_invoice_async_generate_forbidden(store_security_fixture):
    """Cashier 1 assigned to Store 1 cannot queue async PDF generation for Store 2 invoice (403 Forbidden)."""
    ctx = store_security_fixture
    res = client.post(
        f"/api/v1/invoices/{ctx['invoice2_id']}/generate-async",
        headers=ctx["cashier1_headers"],
    )
    assert res.status_code == 403


def test_unauthorized_store_filtering_in_search_forbidden(store_security_fixture):
    """Cashier 1 assigned to Store 1 cannot explicitly query Store 2 invoices via store_id query param."""
    ctx = store_security_fixture
    res = client.get(
        f"/api/v1/invoices?store_id={ctx['store2_id']}",
        headers=ctx["cashier1_headers"],
    )
    assert res.status_code == 403


def test_store_scoped_search_auto_filters_to_assigned_store(store_security_fixture):
    """Cashier 1 searching invoices without specifying store_id only receives Store 1 invoices."""
    ctx = store_security_fixture
    # Query with date_from to satisfy the at-least-one-search-parameter validation
    res = client.get(
        "/api/v1/invoices?payment_status=completed",
        headers=ctx["cashier1_headers"],
    )
    assert res.status_code == 200
    invoices = res.json()
    # Must only contain Store 1 invoices
    for inv in invoices:
        assert inv["store_id"] == ctx["store1_id"]
        assert inv["id"] != ctx["invoice2_id"]


def test_tampered_store_id_checkout_forbidden_with_no_side_effects(store_security_fixture):
    """Cashier 1 attempting checkout for Store 2 is rejected (403) with zero database side effects."""
    ctx = store_security_fixture

    db = SessionLocal()
    try:
        # Check initial inventory for Store 2
        inv_before = db.query(Inventory).filter(
            Inventory.store_id == ctx["store2_id"],
            Inventory.product_id == ctx["product2_id"],
        ).first()
        qty_before = inv_before.quantity if inv_before else 0
        order_count_before = db.query(Order).filter(Order.store_id == ctx["store2_id"]).count()
        invoice_count_before = db.query(Invoice).filter(Invoice.store_id == ctx["store2_id"]).count()
    finally:
        db.close()

    # Attempt tampered checkout by Cashier 1 specifying Store 2
    tampered_checkout = client.post(
        "/api/v1/invoices",
        headers=ctx["cashier1_headers"],
        json={
            "store_id": ctx["store2_id"],
            "items": [{"product_id": ctx["product2_id"], "quantity": 5}],
            "payments": [{"payment_mode": "cash", "amount": "885.00"}],
        },
    )
    assert tampered_checkout.status_code == 403

    # Verify zero persistent side effects
    db = SessionLocal()
    try:
        inv_after = db.query(Inventory).filter(
            Inventory.store_id == ctx["store2_id"],
            Inventory.product_id == ctx["product2_id"],
        ).first()
        qty_after = inv_after.quantity if inv_after else 0
        order_count_after = db.query(Order).filter(Order.store_id == ctx["store2_id"]).count()
        invoice_count_after = db.query(Invoice).filter(Invoice.store_id == ctx["store2_id"]).count()

        assert qty_after == qty_before, "Inventory was altered during unauthorized checkout!"
        assert order_count_after == order_count_before, "Draft order was persisted during unauthorized checkout!"
        assert invoice_count_after == invoice_count_before, "Invoice was generated during unauthorized checkout!"
    finally:
        db.close()


def test_tampered_store_id_cart_add_item_forbidden(store_security_fixture):
    """Cashier 1 attempting to add items to cart for Store 2 is rejected with 403 Forbidden."""
    ctx = store_security_fixture
    res = client.post(
        "/api/v1/billing/cart/add-item",
        headers=ctx["cashier1_headers"],
        params={"store_id": ctx["store2_id"]},
        json={"product_id": ctx["product2_id"], "quantity": 1},
    )
    assert res.status_code == 403


def test_cross_tenant_invoice_access_returns_404(store_security_fixture):
    """User from Tenant B attempting to access Tenant A's invoice receives 404 Not Found without leaking existence."""
    ctx = store_security_fixture
    res = client.get(
        f"/api/v1/invoices/{ctx['invoice1_id']}",
        headers=ctx["tenant_b_headers"],
    )
    assert res.status_code == 404
    data = res.json()
    assert "not found" in str(data).lower()


def test_tenant_wide_owner_can_access_both_stores(store_security_fixture):
    """Tenant Owner (store_id=None) can access invoices from both Store 1 and Store 2."""
    ctx = store_security_fixture

    # Owner can access Store 1 invoice detail & PDF
    res1 = client.get(
        f"/api/v1/invoices/{ctx['invoice1_id']}",
        headers=ctx["owner_headers"],
    )
    assert res1.status_code == 200
    assert res1.json()["id"] == ctx["invoice1_id"]

    pdf1 = client.get(
        f"/api/v1/invoices/{ctx['invoice1_id']}/pdf",
        headers=ctx["owner_headers"],
    )
    assert pdf1.status_code == 200
    assert b"%PDF" in pdf1.content

    # Owner can access Store 2 invoice detail & PDF
    res2 = client.get(
        f"/api/v1/invoices/{ctx['invoice2_id']}",
        headers=ctx["owner_headers"],
    )
    assert res2.status_code == 200
    assert res2.json()["id"] == ctx["invoice2_id"]

    pdf2 = client.get(
        f"/api/v1/invoices/{ctx['invoice2_id']}/pdf",
        headers=ctx["owner_headers"],
    )
    assert pdf2.status_code == 200
    assert b"%PDF" in pdf2.content

    # Owner can search Store 1 specifically
    s1_search = client.get(
        f"/api/v1/invoices?store_id={ctx['store1_id']}",
        headers=ctx["owner_headers"],
    )
    assert s1_search.status_code == 200
    for inv in s1_search.json():
        assert inv["store_id"] == ctx["store1_id"]

    # Owner can search Store 2 specifically
    s2_search = client.get(
        f"/api/v1/invoices?store_id={ctx['store2_id']}",
        headers=ctx["owner_headers"],
    )
    assert s2_search.status_code == 200
    for inv in s2_search.json():
        assert inv["store_id"] == ctx["store2_id"]


def test_tenant_wide_owner_querying_invalid_store_returns_404(store_security_fixture):
    """Tenant Owner searching for a foreign or non-existent store ID receives 404 Not Found."""
    ctx = store_security_fixture
    res = client.get(
        "/api/v1/invoices?store_id=999999",
        headers=ctx["owner_headers"],
    )
    assert res.status_code == 404


def test_unauthorized_cross_store_return_forbidden(store_security_fixture):
    """Cashier 1 attempting to process return on Store 2 invoice is rejected with 403 Forbidden."""
    ctx = store_security_fixture
    res = client.post(
        "/api/v1/billing/returns",
        headers=ctx["cashier1_headers"],
        json={
            "invoice_id": ctx["invoice2_id"],
            "product_id": ctx["product2_id"],
            "return_quantity": 1,
            "reason": "Customer changed mind",
        },
    )
    assert res.status_code == 403


def test_unauthorized_cross_store_credit_note_forbidden(store_security_fixture):
    """Cashier 1 attempting to issue credit note for Store 2 invoice is rejected with 403 Forbidden."""
    ctx = store_security_fixture
    res = client.post(
        "/api/v1/credit-notes",
        headers=ctx["cashier1_headers"],
        json={
            "invoice_id": ctx["invoice2_id"],
            "refund_amount": "50.00",
            "reason": "Defective item",
        },
    )
    # Cashier role has billing:write, but might lack billing:refund (which gives 403) or store check (gives 403)
    assert res.status_code == 403


def test_unauthorized_cross_store_refund_create_forbidden(store_security_fixture):
    """Cashier 1 attempting to initiate refund on Store 2 invoice is rejected with 403 Forbidden."""
    ctx = store_security_fixture
    res = client.post(
        "/api/v1/refunds",
        headers=ctx["cashier1_headers"],
        json={
            "invoice_id": ctx["invoice2_id"],
            "refund_amount": "50.00",
            "refund_method": "cash",
            "reason": "Overcharged customer",
        },
    )
    assert res.status_code == 403


def test_unauthorized_cross_store_list_refunds_forbidden(store_security_fixture):
    """Cashier 1 querying refunds for Store 2 invoice is rejected with 403 Forbidden."""
    ctx = store_security_fixture
    res = client.get(
        f"/api/v1/refunds?invoice_id={ctx['invoice2_id']}",
        headers=ctx["cashier1_headers"],
    )
    assert res.status_code == 403


def test_unauthorized_cross_store_list_credit_notes_forbidden(store_security_fixture):
    """Cashier 1 querying credit notes for Store 2 invoice is rejected with 403 Forbidden."""
    ctx = store_security_fixture
    res = client.get(
        f"/api/v1/credit-notes?invoice_id={ctx['invoice2_id']}",
        headers=ctx["cashier1_headers"],
    )
    assert res.status_code == 403


