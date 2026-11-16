from datetime import date, timedelta
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.store import Store
from app.models.product import Product
from app.models.category import Category
from app.models.store_transfer import StoreTransfer
from app.models.store_transfer_item import StoreTransferItem
from app.schemas.store_expense import PaymentMethod

client = TestClient(app)


def create_tenant_client(prefix: str):
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
def test_env():
    tenant = create_tenant_client("bugfix")
    db = SessionLocal()
    try:
        s1 = Store(
            name="Main Store",
            code=f"STR-{tenant['slug'][:6]}A",
            address="123 Main Street Market",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            phone="9876543210",
            email=f"s1_{tenant['slug'][:6]}@test.com",
            tenant_id=tenant["tenant_id"],
            is_active=True,
            is_main=True,
            is_warehouse=False,
        )
        s2 = Store(
            name="Secondary Branch",
            code=f"STR-{tenant['slug'][:6]}B",
            address="456 Secondary Road",
            city="Pune",
            state="Maharashtra",
            pincode="411001",
            phone="9876543211",
            email=f"s2_{tenant['slug'][:6]}@test.com",
            tenant_id=tenant["tenant_id"],
            is_active=True,
            is_main=False,
            is_warehouse=False,
        )
        db.add_all([s1, s2])
        db.commit()
        db.refresh(s1)
        db.refresh(s2)
        s1_id = s1.id
        s2_id = s2.id

        cat = Category(
            tenant_id=tenant["tenant_id"],
            name=f"Cat-{tenant['slug'][:6]}",
        )
        db.add(cat)
        db.commit()
        db.refresh(cat)

        p = Product(
            tenant_id=tenant["tenant_id"],
            name="Test Soap",
            sku=f"SKU-{tenant['slug'][:6]}",
            price=Decimal("50.00"),
            cost_price=Decimal("30.00"),
            category_id=cat.id,
            is_active=True,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        p_id = p.id

        return {
            "tenant": tenant,
            "store1_id": s1_id,
            "store2_id": s2_id,
            "product_id": p_id,
        }
    finally:
        db.close()


# ==============================================================================
# 1. CREATE STORE EXPENSE API TESTS
# ==============================================================================

def test_create_store_expense_required_field_with_null(test_env):
    headers = test_env["tenant"]["headers"]
    store_id = test_env["store1_id"]
    today = str(date.today())

    # store_id = null
    r = client.post("/api/v1/store-expenses", headers=headers, json={
        "store_id": None,
        "amount": 100.50,
        "category": "Rent",
        "expense_date": today,
        "payment_method": "cash",
    })
    assert r.status_code == 422
    assert "store_id" in str(r.json())

    # amount = null
    r = client.post("/api/v1/store-expenses", headers=headers, json={
        "store_id": store_id,
        "amount": None,
        "category": "Rent",
        "expense_date": today,
        "payment_method": "cash",
    })
    assert r.status_code == 422
    assert "amount" in str(r.json())

    # category = null
    r = client.post("/api/v1/store-expenses", headers=headers, json={
        "store_id": store_id,
        "amount": 100.50,
        "category": None,
        "expense_date": today,
        "payment_method": "cash",
    })
    assert r.status_code == 422
    assert "category" in str(r.json())

    # expense_date = null
    r = client.post("/api/v1/store-expenses", headers=headers, json={
        "store_id": store_id,
        "amount": 100.50,
        "category": "Rent",
        "expense_date": None,
        "payment_method": "cash",
    })
    assert r.status_code == 422
    assert "expense_date" in str(r.json())

    # payment_method = null
    r = client.post("/api/v1/store-expenses", headers=headers, json={
        "store_id": store_id,
        "amount": 100.50,
        "category": "Rent",
        "expense_date": today,
        "payment_method": None,
    })
    assert r.status_code == 422
    assert "payment_method" in str(r.json())


def test_create_store_expense_required_field_with_empty_string(test_env):
    headers = test_env["tenant"]["headers"]
    store_id = test_env["store1_id"]
    today = str(date.today())

    # category = ""
    r = client.post("/api/v1/store-expenses", headers=headers, json={
        "store_id": store_id,
        "amount": 100.50,
        "category": "",
        "expense_date": today,
        "payment_method": "cash",
    })
    assert r.status_code == 422

    # payment_method = ""
    r = client.post("/api/v1/store-expenses", headers=headers, json={
        "store_id": store_id,
        "amount": 100.50,
        "category": "Rent",
        "expense_date": today,
        "payment_method": "",
    })
    assert r.status_code == 422

    # expense_date = ""
    r = client.post("/api/v1/store-expenses", headers=headers, json={
        "store_id": store_id,
        "amount": 100.50,
        "category": "Rent",
        "expense_date": "",
        "payment_method": "cash",
    })
    assert r.status_code == 422


def test_create_store_expense_optional_field_with_null(test_env):
    headers = test_env["tenant"]["headers"]
    store_id = test_env["store1_id"]
    today = str(date.today())

    # Optional fields (description, reference_number) = null must succeed (HTTP 201)
    r = client.post("/api/v1/store-expenses", headers=headers, json={
        "store_id": store_id,
        "amount": 250.75,
        "category": "Utilities",
        "expense_date": today,
        "payment_method": "upi",
        "description": None,
        "reference_number": None,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["description"] is None
    assert data["reference_number"] is None
    assert float(data["amount"]) == 250.75


def test_create_store_expense_invalid_data_type(test_env):
    headers = test_env["tenant"]["headers"]
    store_id = test_env["store1_id"]
    today = str(date.today())

    # Invalid amount: string not a number
    r = client.post("/api/v1/store-expenses", headers=headers, json={
        "store_id": store_id,
        "amount": "abc",
        "category": "Rent",
        "expense_date": today,
        "payment_method": "cash",
    })
    assert r.status_code == 422

    # Invalid store_id: boolean
    r = client.post("/api/v1/store-expenses", headers=headers, json={
        "store_id": True,
        "amount": 100,
        "category": "Rent",
        "expense_date": today,
        "payment_method": "cash",
    })
    assert r.status_code == 422


def test_create_store_expense_valid_request(test_env):
    headers = test_env["tenant"]["headers"]
    store_id = test_env["store1_id"]
    today = str(date.today())

    r = client.post("/api/v1/store-expenses", headers=headers, json={
        "store_id": store_id,
        "amount": 500.00,
        "category": "Office Supplies",
        "description": "Purchased notebooks and printer paper",
        "expense_date": today,
        "payment_method": "card",
        "reference_number": "INV-2026-9901",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["category"] == "Office Supplies"
    assert data["reference_number"] == "INV-2026-9901"
    assert data["payment_method"] == "card"


# ==============================================================================
# 2. UPDATE STORE API TESTS (REFERENCE NUMBER & GENERAL UPDATE)
# ==============================================================================

def test_update_store_invalid_reference_number(test_env):
    headers = test_env["tenant"]["headers"]
    store_id = test_env["store1_id"]

    # Contains invalid special character '@'
    r = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={
        "reference_number": "STORE@123",
    })
    assert r.status_code == 422
    assert "reference_number" in str(r.json())

    # Less than 3 characters
    r = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={
        "reference_number": "AB",
    })
    assert r.status_code == 422

    # No letters (numbers only)
    r = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={
        "reference_number": "123456",
    })
    assert r.status_code == 422


def test_update_store_empty_reference_number(test_env):
    headers = test_env["tenant"]["headers"]
    store_id = test_env["store1_id"]

    # Empty string should be handled and cleared to None
    r = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={
        "reference_number": "",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reference_number"] is None

    # Spaces only string should also be treated as empty / cleared to None
    r = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={
        "reference_number": "   ",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reference_number"] is None


def test_update_store_null_reference_number(test_env):
    headers = test_env["tenant"]["headers"]
    store_id = test_env["store1_id"]

    # Null reference number should be accepted and set to None
    r = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={
        "reference_number": None,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reference_number"] is None


def test_update_store_incorrect_data_type(test_env):
    headers = test_env["tenant"]["headers"]
    store_id = test_env["store1_id"]

    # Integer
    r = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={
        "reference_number": 12345,
    })
    assert r.status_code == 422

    # Boolean
    r = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={
        "reference_number": True,
    })
    assert r.status_code == 422


def test_update_store_valid_reference_number(test_env):
    headers = test_env["tenant"]["headers"]
    store_id = test_env["store1_id"]

    valid_ref = "REF-MUM-2026_01"
    r = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={
        "reference_number": valid_ref,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reference_number"] == valid_ref

    # Verify persistence by fetching store details
    get_r = client.get(f"/api/v1/stores/{store_id}", headers=headers)
    assert get_r.status_code == 200
    assert get_r.json()["reference_number"] == valid_ref


def test_update_store_existing_functionality_preserved(test_env):
    headers = test_env["tenant"]["headers"]
    store_id = test_env["store1_id"]

    # First set reference_number
    valid_ref = "REF-MUM-2026_01"
    r1 = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={
        "reference_number": valid_ref,
    })
    assert r1.status_code == 200
    assert r1.json()["reference_number"] == valid_ref

    # Update address and city without reference_number
    r2 = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={
        "address": "999 Newly Updated Road",
        "city": "Thane",
    })
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["address"] == "999 Newly Updated Road"
    assert data["city"] == "Thane"
    # Previously saved reference_number should remain unchanged
    assert data["reference_number"] == valid_ref


# ==============================================================================
# 3. REJECT STORE TRANSFER API TESTS
# ==============================================================================

def test_reject_store_transfer_workflow(test_env):
    headers = test_env["tenant"]["headers"]
    s1_id = test_env["store1_id"]
    s2_id = test_env["store2_id"]
    p_id = test_env["product_id"]

    # 1. Create a transfer request
    create_resp = client.post("/api/v1/store-transfers", headers=headers, json={
        "source_store_id": s1_id,
        "destination_store_id": s2_id,
        "items": [
            {
                "product_id": p_id,
                "quantity": 10,
            }
        ]
    })
    assert create_resp.status_code == 201, create_resp.text
    transfer_data = create_resp.json()
    transfer_id = transfer_data["id"]
    assert transfer_data["status"] == "Pending"
    assert transfer_data.get("rejection_reason") is None

    # 2. Reject transfer with a valid rejection reason
    reason = "Source branch inventory audit in progress - insufficient stock"
    reject_resp = client.put(
        f"/api/v1/store-transfers/{transfer_id}/reject",
        headers=headers,
        json={"rejection_reason": reason},
    )
    assert reject_resp.status_code == 200, reject_resp.text
    rejected_data = reject_resp.json()
    assert rejected_data["status"] == "Rejected"
    assert rejected_data["rejection_reason"] == reason

    # 3. Fetch transfer details and verify rejection reason is returned
    get_resp = client.get(f"/api/v1/store-transfers/{transfer_id}", headers=headers)
    assert get_resp.status_code == 200, get_resp.text
    fetched_data = get_resp.json()
    assert fetched_data["id"] == transfer_id
    assert fetched_data["status"] == "Rejected"
    assert fetched_data["rejection_reason"] == reason

    # 4. Fetch transfer list and verify rejection reason is returned
    list_resp = client.get("/api/v1/store-transfers", headers=headers)
    assert list_resp.status_code == 200, list_resp.text
    transfers = list_resp.json()
    matching = [t for t in transfers if t["id"] == transfer_id]
    assert len(matching) == 1
    assert matching[0]["rejection_reason"] == reason

    # 5. Verify cannot reject an already rejected transfer
    again_resp = client.put(
        f"/api/v1/store-transfers/{transfer_id}/reject",
        headers=headers,
        json={"rejection_reason": "Trying again"},
    )
    assert again_resp.status_code == 400
