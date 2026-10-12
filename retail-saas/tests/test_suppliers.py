import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.store import Store
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem

client = TestClient(app)


@pytest.fixture
def tenant_fixture():
    slug = f"sup-{uuid.uuid4().hex[:8]}"
    email = f"owner-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Store {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Admin",
            "password": "Password123!",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    db = SessionLocal()
    from app.models.user import User
    user = db.query(User).filter(User.email == email).first()
    tenant_id = user.tenant_id
    db.close()

    return {"headers": headers, "tenant_id": tenant_id}


def test_supplier_purchase_history_validation(tenant_fixture):
    headers = tenant_fixture["headers"]

    # supplier_id = 0 -> 422 (Path gt=0)
    resp_zero = client.get("/api/v1/suppliers/0/purchase-history", headers=headers)
    assert resp_zero.status_code == 422

    # negative supplier_id -> 422 (Path gt=0)
    resp_neg = client.get("/api/v1/suppliers/-5/purchase-history", headers=headers)
    assert resp_neg.status_code == 422

    # non-integer supplier_id -> 422
    resp_str = client.get("/api/v1/suppliers/abc/purchase-history", headers=headers)
    assert resp_str.status_code == 422

    # valid but non-existing supplier_id -> 404
    resp_not_found = client.get("/api/v1/suppliers/999999/purchase-history", headers=headers)
    assert resp_not_found.status_code == 404


def test_supplier_zero_purchase_orders(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Create a new supplier with 0 purchase orders
    create_resp = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Zero PO Supplier Alpha",
            "contact_person": "Contact Person",
            "email": f"zeropo-{uuid.uuid4().hex[:6]}@example.com",
            "phone": "9876543210",
            "address": "123 Street",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    supplier = create_resp.json()
    supplier_id = supplier["id"]

    # Request purchase history
    resp = client.get(f"/api/v1/suppliers/{supplier_id}/purchase-history", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["supplier_id"] == supplier_id
    assert data["supplier_name"] == supplier["name"]
    assert data["total_purchases"] == 0
    assert data["purchase_history"] == []
    assert data["message"] == "No purchase history found for this supplier"


def test_supplier_multiple_purchase_orders_and_items(tenant_fixture):
    headers = tenant_fixture["headers"]
    tenant_id = tenant_fixture["tenant_id"]

    # Create supplier
    create_sup = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Multi PO Supplier Beta",
            "contact_person": "Multi Person",
            "email": f"multipo-{uuid.uuid4().hex[:6]}@example.com",
            "phone": "9876543211",
            "address": "456 Avenue",
        },
        headers=headers,
    )
    assert create_sup.status_code == 201, create_sup.text
    supplier_id = create_sup.json()["id"]
    supplier_name = create_sup.json()["name"]

    # Create store and products via db for purchase order insertion
    db = SessionLocal()
    store = Store(tenant_id=tenant_id, name="Test Store", code=f"STR-{uuid.uuid4().hex[:6]}")
    db.add(store)
    prod1 = Product(tenant_id=tenant_id, name="Product 1", sku=f"SKU-{uuid.uuid4().hex[:6]}", price=Decimal("10.00"), cost_price=Decimal("8.00"))
    prod2 = Product(tenant_id=tenant_id, name="Product 2", sku=f"SKU-{uuid.uuid4().hex[:6]}", price=Decimal("20.00"), cost_price=Decimal("15.00"))
    db.add_all([prod1, prod2])
    db.commit()
    db.refresh(store)
    db.refresh(prod1)
    db.refresh(prod2)

    # Create 2 purchase orders, each with 2 items
    po1 = PurchaseOrder(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        store_id=store.id,
        po_number=f"PO-{uuid.uuid4().hex[:8]}",
        status="received",
        total_amount=Decimal("100.00"),
        remarks="First PO with multiple items",
    )
    po2 = PurchaseOrder(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        store_id=store.id,
        po_number=f"PO-{uuid.uuid4().hex[:8]}",
        status="draft",
        total_amount=Decimal("200.00"),
        remarks="Second PO with multiple items",
    )
    db.add_all([po1, po2])
    db.commit()
    db.refresh(po1)
    db.refresh(po2)

    item1_1 = PurchaseOrderItem(purchase_order_id=po1.id, product_id=prod1.id, quantity=5, unit_price=Decimal("10.00"), total=Decimal("50.00"))
    item1_2 = PurchaseOrderItem(purchase_order_id=po1.id, product_id=prod2.id, quantity=5, unit_price=Decimal("10.00"), total=Decimal("50.00"))
    item2_1 = PurchaseOrderItem(purchase_order_id=po2.id, product_id=prod1.id, quantity=10, unit_price=Decimal("10.00"), total=Decimal("100.00"))
    item2_2 = PurchaseOrderItem(purchase_order_id=po2.id, product_id=prod2.id, quantity=5, unit_price=Decimal("20.00"), total=Decimal("100.00"))
    db.add_all([item1_1, item1_2, item2_1, item2_2])
    db.commit()
    store_id = store.id
    prod1_id = prod1.id
    prod2_id = prod2.id
    db.close()

    # Call endpoint
    resp = client.get(f"/api/v1/suppliers/{supplier_id}/purchase-history", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["supplier_id"] == supplier_id
    assert data["supplier_name"] == supplier_name
    assert data["total_purchases"] == 2
    assert data["message"] == "Purchase history retrieved successfully"
    assert len(data["purchase_history"]) == 2

    # Verify nested schema structure
    for po in data["purchase_history"]:
        assert "id" in po
        assert po["tenant_id"] == tenant_id
        assert po["supplier_id"] == supplier_id
        assert po["store_id"] == store_id
        assert "po_number" in po
        assert po["status"] in ("draft", "received")
        assert Decimal(str(po["total_amount"])) > 0
        assert "created_at" in po
        assert "items" in po
        assert len(po["items"]) == 2
        for item in po["items"]:
            assert "id" in item
            assert item["product_id"] in (prod1_id, prod2_id)
            assert item["quantity"] > 0
            assert Decimal(str(item["unit_price"])) > 0
            assert Decimal(str(item["total"])) > 0


def test_supplier_cross_tenant_isolation(tenant_fixture):
    headers_a = tenant_fixture["headers"]

    # Register tenant B
    slug_b = f"supb-{uuid.uuid4().hex[:8]}"
    email_b = f"owner-{slug_b}@example.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Store {slug_b}",
            "slug": slug_b,
            "email": email_b,
            "admin_name": "Admin B",
            "password": "Password123!",
        },
    )
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": email_b, "password": "Password123!"},
    )
    token_b = login_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Tenant B creates a supplier
    create_sup_b = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Tenant B Supplier Gamma",
            "contact_person": "Person B",
            "email": f"supb-{uuid.uuid4().hex[:6]}@example.com",
            "phone": "9876543212",
            "address": "Tenant B Street",
        },
        headers=headers_b,
    )
    assert create_sup_b.status_code == 201
    supplier_b_id = create_sup_b.json()["id"]

    # Tenant A tries to access Tenant B's supplier purchase history -> 404
    resp_cross = client.get(f"/api/v1/suppliers/{supplier_b_id}/purchase-history", headers=headers_a)
    assert resp_cross.status_code == 404


def test_supplier_create_valid_gstin_and_fields(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Valid Indian GSTIN: 27AAPFU0939F1ZV
    resp = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Stainless Steels",
            "contact_person": "Rahul Patil",
            "email": "rahul.patil@gmail.com",
            "phone": "9876543210",
            "address": "Bhosari MIDC, Pune, Maharashtra",
            "gstin": "27AAPFU0939F1ZV",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Stainless Steels"
    assert data["contact_person"] == "Rahul Patil"
    assert data["email"] == "rahul.patil@gmail.com"
    assert data["phone"] == "9876543210"
    assert data["address"] == "Bhosari MIDC, Pune, Maharashtra"
    assert data["gstin"] == "27AAPFU0939F1ZV"
    assert data["is_active"] is True
    assert "id" in data
    assert "tenant_id" in data
    assert "created_at" in data


def test_supplier_create_invalid_gstin(tenant_fixture):
    headers = tenant_fixture["headers"]

    invalid_gstins = [
        "27ABCDE1234FZ5A",       # Wrong Z position (13th char instead of 14th)
        "27ABCDE1234F1AZ",       # Wrong Z position (15th char instead of 14th)
        "27ABCDE1234F1Z",        # 14 chars (too short)
        "27aapfu0939f1zv",       # Lowercase
        "27AAPFU0939F1ZVV",      # 16 chars (too long)
        "string",                # Placeholder
        "test",                  # Placeholder
        "000000000000000",       # All zeros
        "###$%^&",               # Special characters
        "00AAPFU0939F1ZV",       # Invalid state code 00
        "99AAPFU0939F1Z!",       # Invalid checksum character
        "",                      # Empty string
        "   ",                   # Whitespace
    ]

    for gstin in invalid_gstins:
        resp = client.post(
            "/api/v1/suppliers",
            json={
                "name": "Test Supplier GSTIN",
                "email": f"gstin-{uuid.uuid4().hex[:6]}@example.com",
                "phone": "9876543210",
                "gstin": gstin,
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for GSTIN '{gstin}', got {resp.status_code}: {resp.text}"


def test_supplier_create_invalid_name(tenant_fixture):
    headers = tenant_fixture["headers"]

    invalid_names = [
        "",
        "   ",
        "..",
        "...",
        "----",
        "###",
        "!!!",
        "@@@",
        "###$%^&",
        "12345",
        "string",
        "test",
        "null",
        "none",
        "undefined",
    ]

    for name in invalid_names:
        resp = client.post(
            "/api/v1/suppliers",
            json={
                "name": name,
                "phone": "9876543210",
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for name '{name}', got {resp.status_code}: {resp.text}"


def test_supplier_create_invalid_contact_person(tenant_fixture):
    headers = tenant_fixture["headers"]

    invalid_contacts = [
        "",
        "   ",
        "..",
        "...",
        "----",
        "###",
        "12345",
        "Rahul1",
        "string",
        "test",
        "null",
        "none",
        "undefined",
    ]

    for contact in invalid_contacts:
        resp = client.post(
            "/api/v1/suppliers",
            json={
                "name": "Valid Supplier Name",
                "contact_person": contact,
                "phone": "9876543210",
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for contact_person '{contact}', got {resp.status_code}: {resp.text}"


def test_supplier_create_invalid_address(tenant_fixture):
    headers = tenant_fixture["headers"]

    invalid_addresses = [
        "",
        "   ",
        "###",
        "$%^&",
        "----",
        "....",
        ".....",
        "12345",
        "string",
        "test",
        "null",
        "none",
        "undefined",
    ]

    for addr in invalid_addresses:
        resp = client.post(
            "/api/v1/suppliers",
            json={
                "name": "Valid Supplier Name",
                "address": addr,
                "phone": "9876543210",
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for address '{addr}', got {resp.status_code}: {resp.text}"


def test_supplier_create_invalid_email(tenant_fixture):
    headers = tenant_fixture["headers"]

    invalid_emails = [
        "",
        "   ",
        "string",
        "test",
        "missing-at.com",
        "user@",
        "user@.com",
        "sandeep.joshi@gmli.com",
        "test@yaho.com",
    ]

    for em in invalid_emails:
        resp = client.post(
            "/api/v1/suppliers",
            json={
                "name": "Valid Supplier Name",
                "email": em,
                "phone": "9876543210",
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for email '{em}', got {resp.status_code}: {resp.text}"


def test_supplier_create_invalid_phone(tenant_fixture):
    headers = tenant_fixture["headers"]

    invalid_phones = [
        "",
        "   ",
        "12345",
        "1234567890",
        "abcdefghij",
        "string",
        "+911234567890",
    ]

    for ph in invalid_phones:
        resp = client.post(
            "/api/v1/suppliers",
            json={
                "name": "Valid Supplier Name",
                "phone": ph,
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for phone '{ph}', got {resp.status_code}: {resp.text}"


def test_supplier_update_valid_and_invalid(tenant_fixture):
    headers = tenant_fixture["headers"]

    # First create a valid supplier
    create_resp = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Initial Supplier",
            "contact_person": "Initial Person",
            "email": f"initial-{uuid.uuid4().hex[:6]}@example.com",
            "phone": "9876543210",
            "address": "Initial Address Line",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    supplier_id = create_resp.json()["id"]

    # Valid updates
    # 1. Valid name with apostrophe
    up1 = client.patch(f"/api/v1/suppliers/{supplier_id}", json={"name": "O'Reilly Traders"}, headers=headers)
    assert up1.status_code == 200, up1.text
    assert up1.json()["name"] == "O'Reilly Traders"

    # 2. Valid GSTIN
    up2 = client.patch(f"/api/v1/suppliers/{supplier_id}", json={"gstin": "27AAPFU0939F1ZV"}, headers=headers)
    assert up2.status_code == 200, up2.text
    assert up2.json()["gstin"] == "27AAPFU0939F1ZV"

    # 3. Valid contact_person
    up3 = client.patch(f"/api/v1/suppliers/{supplier_id}", json={"contact_person": "Samar Chavan"}, headers=headers)
    assert up3.status_code == 200, up3.text
    assert up3.json()["contact_person"] == "Samar Chavan"

    # 4. Valid address
    up4 = client.patch(f"/api/v1/suppliers/{supplier_id}", json={"address": "Bhosari MIDC, Pune, Maharashtra"}, headers=headers)
    assert up4.status_code == 200, up4.text
    assert up4.json()["address"] == "Bhosari MIDC, Pune, Maharashtra"

    # 5. Valid email
    up5 = client.patch(f"/api/v1/suppliers/{supplier_id}", json={"email": "user@example.com"}, headers=headers)
    assert up5.status_code == 200, up5.text
    assert up5.json()["email"] == "user@example.com"

    # Invalid updates: must return 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"name": ".."}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"name": "string"}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"contact_person": ".."}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"contact_person": "Rahul1"}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"address": "###"}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"address": "string"}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"email": "sandeep.joshi@gmli.com"}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"email": "string"}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"gstin": "invalid"}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"gstin": "000000000000000"}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"gstin": "27aapfu0939f1zv"}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"gstin": "27ABCDE1234FZ5A"}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"gstin": "27ABCDE1234F1AZ"}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", json={"gstin": "27ABCDE1234F1Z"}, headers=headers).status_code == 422


def test_supplier_status_update_contract_and_error(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Create supplier
    create_resp = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Status Test Supplier",
            "phone": "9876543210",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    supplier_id = create_resp.json()["id"]

    # 1. Existing contract: {"is_active": false} -> 200
    st_false = client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"is_active": False}, headers=headers)
    assert st_false.status_code == 200, st_false.text
    assert st_false.json()["is_active"] is False

    # 2. Existing contract: {"is_active": true} -> 200
    st_true = client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"is_active": True}, headers=headers)
    assert st_true.status_code == 200, st_true.text
    assert st_true.json()["is_active"] is True

    # 3. String representation: {"status": "inactive"} -> 200
    st_str_in = client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"status": "inactive"}, headers=headers)
    assert st_str_in.status_code == 200, st_str_in.text
    assert st_str_in.json()["is_active"] is False

    # 4. String representation: {"status": "active"} -> 200
    st_str_ac = client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"status": "active"}, headers=headers)
    assert st_str_ac.status_code == 200, st_str_ac.text
    assert st_str_ac.json()["is_active"] is True

    # 5. Invalid representation: {"status": "random"} -> 422 with clear expected message
    bad1 = client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"status": "random"}, headers=headers)
    assert bad1.status_code == 422, bad1.text
    assert "Invalid status. Expected one of: active, inactive." in bad1.text

    # 6. Invalid representation: {"is_active": "random"} -> 422 with clear expected message
    bad2 = client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"is_active": "random"}, headers=headers)
    assert bad2.status_code == 422, bad2.text
    assert "Invalid status. Expected one of: active, inactive." in bad2.text

    # 7. Invalid representation: empty body / invalid keys -> 422
    bad3 = client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={}, headers=headers)
    assert bad3.status_code == 422, bad3.text
    assert "Invalid status. Expected one of: active, inactive." in bad3.text


def test_supplier_list_and_search_empty_responses():
    # Register a new isolated tenant with NO suppliers
    slug = f"supempty-{uuid.uuid4().hex[:8]}"
    email = f"owner-{slug}@example.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Empty Store {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Admin",
            "password": "Password123!",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET /api/v1/suppliers when empty: must NOT return bare []
    list_resp = client.get("/api/v1/suppliers", headers=headers)
    assert list_resp.status_code == 200, list_resp.text
    list_data = list_resp.json()
    assert isinstance(list_data, dict)
    assert list_data.get("success") is True
    assert list_data.get("message") == "No suppliers found"
    assert list_data.get("data") == []

    # 2. GET /api/v1/suppliers/search when no match: must NOT return bare [] or 404
    search_resp = client.get("/api/v1/suppliers/search?search=NonExistentSupplier", headers=headers)
    assert search_resp.status_code == 200, search_resp.text
    search_data = search_resp.json()
    assert isinstance(search_data, dict)
    assert search_data.get("success") is True
    assert search_data.get("message") == "No suppliers found matching the search"
    assert search_data.get("data") == []

    # 3. Create a supplier and verify non-empty responses preserve existing structure
    create_resp = client.post(
        "/api/v1/suppliers",
        json={
            "name": "Found Supplier",
            "phone": "9876543210",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201

    list_resp2 = client.get("/api/v1/suppliers", headers=headers)
    assert list_resp2.status_code == 200
    list_data2 = list_resp2.json()
    assert isinstance(list_data2, list)
    assert len(list_data2) == 1
    assert list_data2[0]["name"] == "Found Supplier"

    search_resp2 = client.get("/api/v1/suppliers/search?search=Found Supplier", headers=headers)
    assert search_resp2.status_code == 200
    search_data2 = search_resp2.json()
    assert isinstance(search_data2, list)
    assert len(search_data2) == 1
    assert search_data2[0]["name"] == "Found Supplier"

