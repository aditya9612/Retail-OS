import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.store import Store
from app.models.customer import Customer
from app.models.sale import Sale, SaleItem

client = TestClient(app)


def create_tenant_client(prefix: str):
    """Helper to register and login a distinct tenant."""
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": f"Admin {prefix}",
            "password": "Password123!",
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    data = reg_resp.json()
    tenant_id = data["tenant_id"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return {
        "tenant_id": tenant_id,
        "token": token,
        "headers": headers,
        "slug": slug,
    }


@pytest.fixture
def tenant_a():
    return create_tenant_client("tenant-a")


@pytest.fixture
def tenant_b():
    return create_tenant_client("tenant-b")


# ==============================================================================
# 1. SALES TENANT ISOLATION TESTS
# ==============================================================================

def test_sales_tenant_isolation(tenant_a, tenant_b):
    """
    Verify complete tenant isolation for Sales module:
    - Tenant A can CRUD its own sales
    - Tenant A cannot list, get, update, or delete Tenant B sales
    - Tenant A cannot create sale using Tenant B store/customer/product
    """
    db = SessionLocal()
    try:
        # Create Store A and Store B
        store_a = Store(name="Store A", code=f"STA-{tenant_a['slug'][:6]}", tenant_id=tenant_a["tenant_id"], is_active=True)
        store_b = Store(name="Store B", code=f"STB-{tenant_b['slug'][:6]}", tenant_id=tenant_b["tenant_id"], is_active=True)
        db.add_all([store_a, store_b])
        db.flush()

        # Create Products
        prod_a = Product(name="Prod A", sku=f"SKU-A-{uuid.uuid4().hex[:6]}", selling_price=Decimal("100.00"), tenant_id=tenant_a["tenant_id"], is_active=True)
        prod_b = Product(name="Prod B", sku=f"SKU-B-{uuid.uuid4().hex[:6]}", selling_price=Decimal("200.00"), tenant_id=tenant_b["tenant_id"], is_active=True)
        db.add_all([prod_a, prod_b])
        db.flush()

        # Add Inventory
        inv_a = Inventory(tenant_id=tenant_a["tenant_id"], store_id=store_a.id, product_id=prod_a.id, quantity=50)
        inv_b = Inventory(tenant_id=tenant_b["tenant_id"], store_id=store_b.id, product_id=prod_b.id, quantity=50)
        db.add_all([inv_a, inv_b])
        db.flush()

        # Create Customers
        cust_a = Customer(name="Cust A", phone=f"98{uuid.uuid4().int % 100000000:08d}", tenant_id=tenant_a["tenant_id"])
        cust_b = Customer(name="Cust B", phone=f"99{uuid.uuid4().int % 100000000:08d}", tenant_id=tenant_b["tenant_id"])
        db.add_all([cust_a, cust_b])
        db.commit()

        store_a_id = store_a.id
        store_b_id = store_b.id
        prod_a_id = prod_a.id
        prod_b_id = prod_b.id
        cust_a_id = cust_a.id
        cust_b_id = cust_b.id
    finally:
        db.close()

    # 1. Positive: Tenant A creates own sale
    resp_create_a = client.post(
        "/api/v1/sales",
        json={
            "store_id": store_a_id,
            "customer_id": cust_a_id,
            "payment_method": "cash",
            "items": [{"product_id": prod_a_id, "stock": 2, "discount": 0}],
        },
        headers=tenant_a["headers"],
    )
    assert resp_create_a.status_code == 201, resp_create_a.text
    sale_a_id = resp_create_a.json()["id"]

    # Tenant B creates own sale
    resp_create_b = client.post(
        "/api/v1/sales",
        json={
            "store_id": store_b_id,
            "customer_id": cust_b_id,
            "payment_method": "cash",
            "items": [{"product_id": prod_b_id, "stock": 3, "discount": 0}],
        },
        headers=tenant_b["headers"],
    )
    assert resp_create_b.status_code == 201, resp_create_b.text
    sale_b_id = resp_create_b.json()["id"]

    # 2. Negative: Tenant A lists sales -> must NOT include Tenant B's sale
    resp_list_a = client.get("/api/v1/sales", headers=tenant_a["headers"])
    assert resp_list_a.status_code == 200
    sales_a = resp_list_a.json()
    sale_ids_seen_by_a = [s["id"] for s in sales_a]
    assert sale_a_id in sale_ids_seen_by_a
    assert sale_b_id not in sale_ids_seen_by_a, "SECURITY VIOLATION: Tenant A saw Tenant B sale in list!"

    # 3. Negative: Tenant A attempts to get Tenant B sale by ID -> must fail (404)
    resp_get_b_by_a = client.get(f"/api/v1/sales/{sale_b_id}", headers=tenant_a["headers"])
    assert resp_get_b_by_a.status_code == 404, "SECURITY VIOLATION: Tenant A accessed Tenant B sale detail!"

    # 4. Negative: Tenant A attempts to update Tenant B sale -> must fail (404)
    resp_put_b_by_a = client.put(
        f"/api/v1/sales/{sale_b_id}",
        json={
            "store_id": store_a_id,
            "customer_id": cust_a_id,
            "payment_method": "upi",
            "items": [{"product_id": prod_a_id, "stock": 1, "discount": 0}],
        },
        headers=tenant_a["headers"],
    )
    assert resp_put_b_by_a.status_code in [400, 404], "SECURITY VIOLATION: Tenant A mutated Tenant B sale!"

    # 5. Negative: Tenant A attempts to delete Tenant B sale -> must fail (404)
    resp_del_b_by_a = client.delete(f"/api/v1/sales/{sale_b_id}", headers=tenant_a["headers"])
    assert resp_del_b_by_a.status_code == 404, "SECURITY VIOLATION: Tenant A deleted Tenant B sale!"

    # 6. Negative: Tenant A attempts to create sale using Tenant B store_id -> must fail
    resp_cross_store = client.post(
        "/api/v1/sales",
        json={
            "store_id": store_b_id,
            "customer_id": cust_a_id,
            "payment_method": "cash",
            "items": [{"product_id": prod_a_id, "stock": 1, "discount": 0}],
        },
        headers=tenant_a["headers"],
    )
    assert resp_cross_store.status_code in [400, 404], "SECURITY VIOLATION: Tenant A created sale in Tenant B store!"

    # 7. Negative: Tenant A attempts to create sale with Tenant B customer_id -> must fail
    resp_cross_cust = client.post(
        "/api/v1/sales",
        json={
            "store_id": store_a_id,
            "customer_id": cust_b_id,
            "payment_method": "cash",
            "items": [{"product_id": prod_a_id, "stock": 1, "discount": 0}],
        },
        headers=tenant_a["headers"],
    )
    assert resp_cross_cust.status_code in [400, 404], "SECURITY VIOLATION: Tenant A used Tenant B customer!"

    # 8. Negative: Tenant A attempts to create sale with Tenant B product_id -> must fail
    resp_cross_prod = client.post(
        "/api/v1/sales",
        json={
            "store_id": store_a_id,
            "customer_id": cust_a_id,
            "payment_method": "cash",
            "items": [{"product_id": prod_b_id, "stock": 1, "discount": 0}],
        },
        headers=tenant_a["headers"],
    )
    assert resp_cross_prod.status_code in [400, 404], "SECURITY VIOLATION: Tenant A used Tenant B product!"

    # 9. Positive: Tenant A can get and delete own sale
    resp_get_a = client.get(f"/api/v1/sales/{sale_a_id}", headers=tenant_a["headers"])
    assert resp_get_a.status_code == 200

    resp_del_a = client.delete(f"/api/v1/sales/{sale_a_id}", headers=tenant_a["headers"])
    assert resp_del_a.status_code == 200


# ==============================================================================
# 2. STORE EXPENSES TENANT ISOLATION TESTS
# ==============================================================================

def test_store_expenses_tenant_isolation(tenant_a, tenant_b):
    """
    Verify complete tenant isolation for Store Expenses module:
    - Tenant A can CRUD its own expenses
    - Tenant A cannot list, get, update, or delete Tenant B expenses
    - Tenant A cannot create an expense using Tenant B store_id
    - Tenant A list without store_id must NEVER return Tenant B expenses
    """
    db = SessionLocal()
    try:
        store_a = Store(name="Exp Store A", code=f"ESA-{tenant_a['slug'][:6]}", tenant_id=tenant_a["tenant_id"], is_active=True)
        store_b = Store(name="Exp Store B", code=f"ESB-{tenant_b['slug'][:6]}", tenant_id=tenant_b["tenant_id"], is_active=True)
        db.add_all([store_a, store_b])
        db.commit()
        store_a_id = store_a.id
        store_b_id = store_b.id
    finally:
        db.close()

    # 1. Positive: Tenant A creates own expense
    resp_exp_a = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": store_a_id,
            "amount": 250.00,
            "category": "Office",
            "description": "Tea and snacks for staff",
            "expense_date": "2026-09-24",
            "payment_method": "cash",
        },
        headers=tenant_a["headers"],
    )
    assert resp_exp_a.status_code == 201, resp_exp_a.text
    exp_a_id = resp_exp_a.json()["id"]

    # Tenant B creates own expense
    resp_exp_b = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": store_b_id,
            "amount": 5000.00,
            "category": "Utilities",
            "description": "Monthly electricity bill",
            "expense_date": "2026-09-24",
            "payment_method": "bank_transfer",
        },
        headers=tenant_b["headers"],
    )
    assert resp_exp_b.status_code == 201, resp_exp_b.text
    exp_b_id = resp_exp_b.json()["id"]

    # 2. Negative: Tenant A lists expenses without store_id -> must NOT include Tenant B expense
    resp_list_a = client.get("/api/v1/store-expenses", headers=tenant_a["headers"])
    assert resp_list_a.status_code == 200
    exp_ids_seen_by_a = [e["id"] for e in resp_list_a.json()]
    assert exp_a_id in exp_ids_seen_by_a
    assert exp_b_id not in exp_ids_seen_by_a, "SECURITY VIOLATION: Tenant A saw Tenant B expense in global list!"

    # 3. Negative: Tenant A requests expenses passing Tenant B's store_id -> must NOT return Tenant B data
    resp_filter_b = client.get(f"/api/v1/store-expenses?store_id={store_b_id}", headers=tenant_a["headers"])
    if resp_filter_b.status_code == 200:
        assert len(resp_filter_b.json()) == 0, "SECURITY VIOLATION: Tenant A filtered by Tenant B store and got data!"
    else:
        assert resp_filter_b.status_code in [400, 404]

    # 4. Negative: Tenant A attempts to get Tenant B's expense by ID -> must fail (404)
    resp_get_b = client.get(f"/api/v1/store-expenses/{exp_b_id}", headers=tenant_a["headers"])
    assert resp_get_b.status_code == 404, "SECURITY VIOLATION: Tenant A fetched Tenant B expense by ID!"

    # 5. Negative: Tenant A attempts to update Tenant B's expense -> must fail (404)
    resp_put_b = client.put(
        f"/api/v1/store-expenses/{exp_b_id}",
        json={
            "amount": 10.00,
            "description": "Tampered description",
        },
        headers=tenant_a["headers"],
    )
    assert resp_put_b.status_code == 404, "SECURITY VIOLATION: Tenant A updated Tenant B expense!"

    # 6. Negative: Tenant A attempts to delete Tenant B's expense -> must fail (404)
    resp_del_b = client.delete(f"/api/v1/store-expenses/{exp_b_id}", headers=tenant_a["headers"])
    assert resp_del_b.status_code == 404, "SECURITY VIOLATION: Tenant A deleted Tenant B expense!"

    # 7. Negative: Tenant A attempts to create expense using Tenant B's store_id -> must fail (404)
    resp_create_cross = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": store_b_id,
            "amount": 99.00,
            "category": "Office",
            "description": "Cross tenant expense creation attempt",
            "expense_date": "2026-09-24",
            "payment_method": "cash",
        },
        headers=tenant_a["headers"],
    )
    assert resp_create_cross.status_code in [400, 404], "SECURITY VIOLATION: Tenant A created expense for Tenant B store!"

    # 8. Positive: Tenant A can get, update, and delete own expense
    resp_own_get = client.get(f"/api/v1/store-expenses/{exp_a_id}", headers=tenant_a["headers"])
    assert resp_own_get.status_code == 200

    resp_own_del = client.delete(f"/api/v1/store-expenses/{exp_a_id}", headers=tenant_a["headers"])
    assert resp_own_del.status_code in [200, 204]


# ==============================================================================
# 3. STORE TRANSFERS TENANT ISOLATION TESTS
# ==============================================================================

def test_store_transfers_tenant_isolation(tenant_a, tenant_b):
    """
    Verify complete tenant isolation for Store Transfers module:
    - Tenant A can transfer between two own stores (Store A1 -> Store A2)
    - Tenant A cannot transfer using Tenant B store as source or destination
    - Tenant A cannot access, approve, reject, dispatch, or receive Tenant B transfer
    """
    db = SessionLocal()
    try:
        store_a1 = Store(name="Store A1", code=f"SA1-{tenant_a['slug'][:5]}", tenant_id=tenant_a["tenant_id"], is_active=True)
        store_a2 = Store(name="Store A2", code=f"SA2-{tenant_a['slug'][:5]}", tenant_id=tenant_a["tenant_id"], is_active=True)
        store_b1 = Store(name="Store B1", code=f"SB1-{tenant_b['slug'][:5]}", tenant_id=tenant_b["tenant_id"], is_active=True)
        store_b2 = Store(name="Store B2", code=f"SB2-{tenant_b['slug'][:5]}", tenant_id=tenant_b["tenant_id"], is_active=True)
        db.add_all([store_a1, store_a2, store_b1, store_b2])
        db.flush()

        prod_a = Product(name="Trf Prod A", sku=f"TRF-A-{uuid.uuid4().hex[:6]}", selling_price=Decimal("50.00"), tenant_id=tenant_a["tenant_id"], is_active=True)
        prod_b = Product(name="Trf Prod B", sku=f"TRF-B-{uuid.uuid4().hex[:6]}", selling_price=Decimal("50.00"), tenant_id=tenant_b["tenant_id"], is_active=True)
        db.add_all([prod_a, prod_b])
        db.commit()

        sa1_id = store_a1.id
        sa2_id = store_a2.id
        sb1_id = store_b1.id
        sb2_id = store_b2.id
        pa_id = prod_a.id
        pb_id = prod_b.id
    finally:
        db.close()

    # 1. Positive: Tenant A creates valid transfer between own stores
    resp_trf_a = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": sa1_id,
            "destination_store_id": sa2_id,
            "items": [{"product_id": pa_id, "quantity": 5}],
        },
        headers=tenant_a["headers"],
    )
    assert resp_trf_a.status_code == 201, resp_trf_a.text
    trf_a_id = resp_trf_a.json()["id"]

    # Tenant B creates valid transfer between own stores
    resp_trf_b = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": sb1_id,
            "destination_store_id": sb2_id,
            "items": [{"product_id": pb_id, "quantity": 10}],
        },
        headers=tenant_b["headers"],
    )
    assert resp_trf_b.status_code == 201, resp_trf_b.text
    trf_b_id = resp_trf_b.json()["id"]

    # 2. Negative: Tenant A lists transfers -> must NOT see Tenant B transfer
    resp_list_a = client.get("/api/v1/store-transfers", headers=tenant_a["headers"])
    assert resp_list_a.status_code == 200
    seen_by_a = [t["id"] for t in resp_list_a.json()]
    assert trf_a_id in seen_by_a
    assert trf_b_id not in seen_by_a, "SECURITY VIOLATION: Tenant A saw Tenant B transfer in list!"

    # 3. Negative: Tenant A cannot get Tenant B transfer by ID -> must fail (404)
    resp_get_b = client.get(f"/api/v1/store-transfers/{trf_b_id}", headers=tenant_a["headers"])
    assert resp_get_b.status_code == 404, "SECURITY VIOLATION: Tenant A retrieved Tenant B transfer!"

    # 4. Negative: Tenant A cannot approve Tenant B transfer
    resp_appr_b = client.put(f"/api/v1/store-transfers/{trf_b_id}/approve", headers=tenant_a["headers"])
    assert resp_appr_b.status_code in [400, 404], "SECURITY VIOLATION: Tenant A approved Tenant B transfer!"

    # 5. Negative: Tenant A cannot reject Tenant B transfer
    resp_rej_b = client.put(f"/api/v1/store-transfers/{trf_b_id}/reject", headers=tenant_a["headers"])
    assert resp_rej_b.status_code in [400, 404], "SECURITY VIOLATION: Tenant A rejected Tenant B transfer!"

    # 6. Negative: Tenant A cannot dispatch Tenant B transfer
    resp_disp_b = client.put(f"/api/v1/store-transfers/{trf_b_id}/dispatch", headers=tenant_a["headers"])
    assert resp_disp_b.status_code in [400, 404], "SECURITY VIOLATION: Tenant A dispatched Tenant B transfer!"

    # 7. Negative: Tenant A cannot receive Tenant B transfer
    resp_recv_b = client.put(f"/api/v1/store-transfers/{trf_b_id}/receive", headers=tenant_a["headers"])
    assert resp_recv_b.status_code in [400, 404], "SECURITY VIOLATION: Tenant A received Tenant B transfer!"

    # 8. Negative: Tenant A attempts to create transfer with Tenant B source store -> must fail
    resp_fake_src = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": sb1_id,
            "destination_store_id": sa2_id,
            "items": [{"product_id": pa_id, "quantity": 1}],
        },
        headers=tenant_a["headers"],
    )
    assert resp_fake_src.status_code in [400, 404], "SECURITY VIOLATION: Tenant A used Tenant B source store!"

    # 9. Negative: Tenant A attempts to create transfer with Tenant B destination store -> must fail
    resp_fake_dst = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": sa1_id,
            "destination_store_id": sb2_id,
            "items": [{"product_id": pa_id, "quantity": 1}],
        },
        headers=tenant_a["headers"],
    )
    assert resp_fake_dst.status_code in [400, 404], "SECURITY VIOLATION: Tenant A used Tenant B destination store!"
