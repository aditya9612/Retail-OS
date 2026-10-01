from datetime import date, timedelta
from decimal import Decimal
import uuid
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.store import Store
from app.models.store_expense import StoreExpense
from app.schemas.store_expense import (
    PaymentMethod,
    StoreExpenseCreate,
    StoreExpenseUpdate,
    VALID_EXPENSE_CATEGORIES,
)

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
def tenant():
    return create_tenant_client("exp-tenant")


@pytest.fixture
def stores(tenant):
    db = SessionLocal()
    try:
        s1 = Store(name="Store 1", code=f"S1-{tenant['slug'][:6]}", tenant_id=tenant["tenant_id"], is_active=True)
        s2 = Store(name="Store 2", code=f"S2-{tenant['slug'][:6]}", tenant_id=tenant["tenant_id"], is_active=True)
        db.add_all([s1, s2])
        db.commit()
        db.refresh(s1)
        db.refresh(s2)
        return s1, s2
    finally:
        db.close()


# ==============================================================================
# SCHEMA-LEVEL UNIT TESTS
# ==============================================================================

def test_schema_valid_categories():
    today = date.today()
    for cat in ["Rent", "Utilities", "Salary", "Maintenance", "Travel", "Office Supplies", "Office", "Marketing", "Other"]:
        exp = StoreExpenseCreate(
            store_id=1,
            amount=Decimal("100.00"),
            category=cat,
            expense_date=today,
            payment_method=PaymentMethod.CASH,
        )
        assert exp.category == cat

    # Test lowercase normalization
    exp_lower = StoreExpenseCreate(
        store_id=1,
        amount=Decimal("100.00"),
        category="rent",
        expense_date=today,
        payment_method=PaymentMethod.CASH,
    )
    assert exp_lower.category == "Rent"


def test_schema_invalid_categories():
    today = date.today()
    for bad_cat in ["ArbitraryCategory", "Food123", "RandomExpense", "Entertainment"]:
        with pytest.raises(ValidationError):
            StoreExpenseCreate(
                store_id=1,
                amount=Decimal("100.00"),
                category=bad_cat,
                expense_date=today,
                payment_method=PaymentMethod.CASH,
            )


def test_schema_reference_number_date_correlation():
    exp_date = date(2026, 9, 24)

    # 1. Matching 8-digit date -> succeeds
    e1 = StoreExpenseCreate(
        store_id=1,
        amount=Decimal("100.00"),
        category="Rent",
        expense_date=exp_date,
        payment_method=PaymentMethod.CASH,
        reference_number="EXP-20260924-001",
    )
    assert e1.reference_number == "EXP-20260924-001"

    # 2. Mismatching 8-digit date -> rejected
    with pytest.raises(ValidationError) as exc_info:
        StoreExpenseCreate(
            store_id=1,
            amount=Decimal("100.00"),
            category="Rent",
            expense_date=exp_date,
            payment_method=PaymentMethod.CASH,
            reference_number="EXP-20260920-001",
        )
    assert "does not match expense date" in str(exc_info.value)

    # 3. Matching year -> succeeds
    e2 = StoreExpenseCreate(
        store_id=1,
        amount=Decimal("100.00"),
        category="Rent",
        expense_date=exp_date,
        payment_method=PaymentMethod.CASH,
        reference_number="INV-2026-001",
    )
    assert e2.reference_number == "INV-2026-001"

    # 4. Mismatching year -> rejected
    with pytest.raises(ValidationError) as exc_info:
        StoreExpenseCreate(
            store_id=1,
            amount=Decimal("100.00"),
            category="Rent",
            expense_date=exp_date,
            payment_method=PaymentMethod.CASH,
            reference_number="INV-2025-001",
        )
    assert "does not match expense date year" in str(exc_info.value)

    # 5. Non-date reference number -> succeeds
    e3 = StoreExpenseCreate(
        store_id=1,
        amount=Decimal("100.00"),
        category="Rent",
        expense_date=exp_date,
        payment_method=PaymentMethod.CASH,
        reference_number="RECEIPT-101",
    )
    assert e3.reference_number == "RECEIPT-101"

    # 6. Omitted reference number -> succeeds
    e4 = StoreExpenseCreate(
        store_id=1,
        amount=Decimal("100.00"),
        category="Rent",
        expense_date=exp_date,
        payment_method=PaymentMethod.CASH,
    )
    assert e4.reference_number is None


def test_schema_preserves_existing_validations():
    today = date.today()
    # Amount <= 0 rejected
    with pytest.raises(ValidationError):
        StoreExpenseCreate(store_id=1, amount=Decimal("0.00"), category="Rent", expense_date=today, payment_method=PaymentMethod.CASH)

    with pytest.raises(ValidationError):
        StoreExpenseCreate(store_id=1, amount=Decimal("-50.00"), category="Rent", expense_date=today, payment_method=PaymentMethod.CASH)

    # Future date rejected
    with pytest.raises(ValidationError):
        StoreExpenseCreate(store_id=1, amount=Decimal("100.00"), category="Rent", expense_date=today + timedelta(days=1), payment_method=PaymentMethod.CASH)

    # Invalid payment method rejected
    with pytest.raises(ValidationError):
        StoreExpenseCreate(store_id=1, amount=Decimal("100.00"), category="Rent", expense_date=today, payment_method="bitcoin")


# ==============================================================================
# API-LEVEL END-TO-END TESTS
# ==============================================================================

def test_create_store_expense_success(tenant, stores):
    s1, _ = stores
    today = date.today().isoformat()
    ref_num = f"REF-{date.today().strftime('%Y%m%d')}-01"

    resp = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": s1.id,
            "amount": 1250.50,
            "category": "Rent",
            "description": "Monthly shop rent",
            "expense_date": today,
            "payment_method": "bank_transfer",
            "reference_number": ref_num,
        },
        headers=tenant["headers"],
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["amount"] == "1250.50"
    assert data["category"] == "Rent"
    assert data["reference_number"] == ref_num
    assert data["store_id"] == s1.id


def test_create_store_expense_duplicate_reference_rejected(tenant, stores):
    s1, s2 = stores
    today = date.today().isoformat()
    ref_num = f"DUP-{date.today().strftime('%Y%m%d')}-01"

    # Create first expense
    resp1 = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": s1.id,
            "amount": 500.00,
            "category": "Utilities",
            "description": "Electric bill",
            "expense_date": today,
            "payment_method": "cash",
            "reference_number": ref_num,
        },
        headers=tenant["headers"],
    )
    assert resp1.status_code == 201, resp1.text

    # Attempt to create duplicate reference number in same store -> rejected
    resp2 = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": s1.id,
            "amount": 600.00,
            "category": "Utilities",
            "description": "Another electric bill",
            "expense_date": today,
            "payment_method": "cash",
            "reference_number": ref_num,
        },
        headers=tenant["headers"],
    )
    assert resp2.status_code == 409, f"Expected 409 Conflict, got {resp2.status_code}: {resp2.text}"

    # Attempt to create duplicate reference number in another store of same tenant -> rejected
    resp3 = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": s2.id,
            "amount": 700.00,
            "category": "Utilities",
            "description": "Second store bill",
            "expense_date": today,
            "payment_method": "cash",
            "reference_number": ref_num,
        },
        headers=tenant["headers"],
    )
    assert resp3.status_code == 409, f"Expected 409 Conflict, got {resp3.status_code}: {resp3.text}"


def test_create_store_expense_invalid_category_rejected(tenant, stores):
    s1, _ = stores
    today = date.today().isoformat()

    resp = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": s1.id,
            "amount": 100.00,
            "category": "ArbitraryNonExistentCategory",
            "expense_date": today,
            "payment_method": "cash",
        },
        headers=tenant["headers"],
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_create_store_expense_invalid_reference_date_rejected(tenant, stores):
    s1, _ = stores
    # expense_date is 2026-09-24 but reference number says 20260920
    resp = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": s1.id,
            "amount": 100.00,
            "category": "Office",
            "expense_date": "2026-09-24",
            "payment_method": "cash",
            "reference_number": "EXP-20260920-001",
        },
        headers=tenant["headers"],
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_update_store_expense_reassign_store_rejected(tenant, stores):
    s1, s2 = stores
    today = date.today().isoformat()

    # Create expense in Store 1
    create_resp = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": s1.id,
            "amount": 800.00,
            "category": "Maintenance",
            "description": "AC repair",
            "expense_date": today,
            "payment_method": "upi",
        },
        headers=tenant["headers"],
    )
    assert create_resp.status_code == 201
    expense_id = create_resp.json()["id"]

    # Attempt to reassign store_id to Store 2 -> must be rejected
    put_resp = client.put(
        f"/api/v1/store-expenses/{expense_id}",
        json={"store_id": s2.id},
        headers=tenant["headers"],
    )
    assert put_resp.status_code == 400, f"Expected 400, got {put_resp.status_code}: {put_resp.text}"
    assert "Store ID cannot be changed" in put_resp.text

    # Updating with unchanged store_id succeeds
    put_ok = client.put(
        f"/api/v1/store-expenses/{expense_id}",
        json={"store_id": s1.id, "amount": 850.00},
        headers=tenant["headers"],
    )
    assert put_ok.status_code == 200, put_ok.text
    assert put_ok.json()["amount"] == "850.00"
    assert put_ok.json()["store_id"] == s1.id


def test_update_store_expense_duplicate_reference_rejected(tenant, stores):
    s1, _ = stores
    today = date.today().isoformat()
    ref1 = f"REF1-{date.today().strftime('%Y%m%d')}-01"
    ref2 = f"REF2-{date.today().strftime('%Y%m%d')}-02"

    exp1 = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": s1.id,
            "amount": 100.00,
            "category": "Travel",
            "expense_date": today,
            "payment_method": "cash",
            "reference_number": ref1,
        },
        headers=tenant["headers"],
    ).json()

    exp2 = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": s1.id,
            "amount": 200.00,
            "category": "Travel",
            "expense_date": today,
            "payment_method": "cash",
            "reference_number": ref2,
        },
        headers=tenant["headers"],
    ).json()

    # Expense 1 updating while retaining own reference number -> succeeds
    put_self = client.put(
        f"/api/v1/store-expenses/{exp1['id']}",
        json={"reference_number": ref1, "amount": 150.00},
        headers=tenant["headers"],
    )
    assert put_self.status_code == 200, put_self.text

    # Expense 2 updating to Expense 1's reference number -> rejected
    put_dup = client.put(
        f"/api/v1/store-expenses/{exp2['id']}",
        json={"reference_number": ref1},
        headers=tenant["headers"],
    )
    assert put_dup.status_code == 409, f"Expected 409, got {put_dup.status_code}: {put_dup.text}"


def test_update_store_expense_invalid_category_rejected(tenant, stores):
    s1, _ = stores
    today = date.today().isoformat()

    exp = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": s1.id,
            "amount": 300.00,
            "category": "Office",
            "expense_date": today,
            "payment_method": "cash",
        },
        headers=tenant["headers"],
    ).json()

    # Update with invalid category -> rejected
    resp = client.put(
        f"/api/v1/store-expenses/{exp['id']}",
        json={"category": "InvalidCategoryName"},
        headers=tenant["headers"],
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_update_store_expense_invalid_reference_date_rejected(tenant, stores):
    s1, _ = stores

    exp = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": s1.id,
            "amount": 300.00,
            "category": "Office",
            "expense_date": "2026-09-24",
            "payment_method": "cash",
            "reference_number": "EXP-20260924-001",
        },
        headers=tenant["headers"],
    ).json()

    # Attempt to change reference number to a mismatching date -> rejected
    resp = client.put(
        f"/api/v1/store-expenses/{exp['id']}",
        json={"reference_number": "EXP-20260920-001"},
        headers=tenant["headers"],
    )
    assert resp.status_code in [400, 422], f"Expected 400/422, got {resp.status_code}: {resp.text}"


# ==============================================================================
# EXPENSE ID VALIDATION (GET, PUT, DELETE)
# ==============================================================================

def test_expense_id_validation_non_existing_404(tenant):
    non_existent_id = 999999

    # GET non-existent -> 404
    resp_get = client.get(f"/api/v1/store-expenses/{non_existent_id}", headers=tenant["headers"])
    assert resp_get.status_code == 404, resp_get.text

    # PUT non-existent -> 404
    resp_put = client.put(
        f"/api/v1/store-expenses/{non_existent_id}",
        json={"amount": 100.00},
        headers=tenant["headers"],
    )
    assert resp_put.status_code == 404, resp_put.text

    # DELETE non-existent -> 404
    resp_del = client.delete(f"/api/v1/store-expenses/{non_existent_id}", headers=tenant["headers"])
    assert resp_del.status_code == 404, resp_del.text


def test_expense_id_validation_invalid_id_400(tenant):
    invalid_id = 0

    # GET <= 0 -> 400
    resp_get = client.get(f"/api/v1/store-expenses/{invalid_id}", headers=tenant["headers"])
    assert resp_get.status_code == 400, resp_get.text

    # PUT <= 0 -> 400
    resp_put = client.put(
        f"/api/v1/store-expenses/{invalid_id}",
        json={"amount": 100.00},
        headers=tenant["headers"],
    )
    assert resp_put.status_code == 400, resp_put.text

    # DELETE <= 0 -> 400
    resp_del = client.delete(f"/api/v1/store-expenses/{invalid_id}", headers=tenant["headers"])
    assert resp_del.status_code == 400, resp_del.text


def test_expense_crud_flow_existing_id(tenant, stores):
    s1, _ = stores
    today = date.today().isoformat()

    # 1. CREATE
    create_resp = client.post(
        "/api/v1/store-expenses",
        json={
            "store_id": s1.id,
            "amount": 250.00,
            "category": "Salary",
            "description": "Assistant salary",
            "expense_date": today,
            "payment_method": "bank_transfer",
        },
        headers=tenant["headers"],
    )
    assert create_resp.status_code == 201
    expense_id = create_resp.json()["id"]

    # 2. GET by ID
    get_resp = client.get(f"/api/v1/store-expenses/{expense_id}", headers=tenant["headers"])
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == expense_id
    assert get_resp.json()["category"] == "Salary"

    # 3. UPDATE
    put_resp = client.put(
        f"/api/v1/store-expenses/{expense_id}",
        json={"amount": 300.00, "description": "Updated assistant salary"},
        headers=tenant["headers"],
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["amount"] == "300.00"
    assert put_resp.json()["description"] == "Updated assistant salary"

    # 4. DELETE
    del_resp = client.delete(f"/api/v1/store-expenses/{expense_id}", headers=tenant["headers"])
    assert del_resp.status_code == 204

    # 5. Subsequent GET returns 404 (soft-deleted)
    get_after = client.get(f"/api/v1/store-expenses/{expense_id}", headers=tenant["headers"])
    assert get_after.status_code == 404
