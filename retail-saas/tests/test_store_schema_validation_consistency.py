import uuid
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.core.database import SessionLocal
from app.models.store import Store
from app.schemas.store import StoreCreate, StoreUpdate

client = TestClient(app)


def _create_tenant_and_auth(prefix: str):
    suffix = uuid.uuid4().hex[:6]
    slug = f"{prefix}-{suffix}"
    email = f"owner_{suffix}@{prefix}.com"

    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Tenant {suffix}",
            "domain": slug,
            "owner_email": email,
            "owner_name": "Test Owner",
            "password": "Password123!",
            "plan_code": "enterprise",
        },
    )
    assert reg_res.status_code == 200, f"Register failed: {reg_res.text}"

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "tenant_id": reg_res.json()["tenant_id"],
        "slug": slug,
    }


# ==============================================================================
# 1. Schema-Level Consistency Tests (StoreCreate vs StoreUpdate)
# ==============================================================================

def test_store_update_name_validation_consistency():
    # Valid names in StoreUpdate
    for valid_name in ["BHAGYALAXMI MART", "Om", "Sai", "Sai Krupa Traders"]:
        s = StoreUpdate(name=valid_name)
        assert s.name == valid_name

    # Omitted / None is allowed in StoreUpdate
    s_none = StoreUpdate(name=None)
    assert s_none.name is None

    # Invalid names rejected in StoreUpdate just like StoreCreate
    for invalid_name in ["A", "KIRANA", "BHAGYALAXMI", "Store@123", "   ", ""]:
        with pytest.raises(ValidationError):
            StoreUpdate(name=invalid_name)


def test_store_update_address_validation_consistency():
    # Valid address in StoreUpdate
    valid_addr = "Shop No. 5, College Road, Gangapur, Nashik"
    s = StoreUpdate(address=valid_addr)
    assert s.address == valid_addr

    # None allowed in StoreUpdate
    s_none = StoreUpdate(address=None)
    assert s_none.address is None

    # Invalid addresses rejected in StoreUpdate
    for invalid_addr in ["Road", "Main Road", "Nashik", "House No. 10", "Shop No. 5, Main Road", "   "]:
        with pytest.raises(ValidationError):
            StoreUpdate(address=invalid_addr)


def test_store_update_city_validation_consistency():
    # Valid city in StoreUpdate
    for valid_city in ["Nashik", "Pune", "Mumbai"]:
        s = StoreUpdate(city=valid_city)
        assert s.city == valid_city

    # None allowed in StoreUpdate
    s_none = StoreUpdate(city=None)
    assert s_none.city is None

    # Invalid cities rejected in StoreUpdate
    for invalid_city in ["12345", "@#$%", "Maharashtra", "India", "Shop 5, College Road, Nashik"]:
        with pytest.raises(ValidationError):
            StoreUpdate(city=invalid_city)


def test_store_update_location_consistency_schema_level():
    # When both address and city are passed to StoreUpdate, match is enforced
    s_valid = StoreUpdate(address="FC Road, Pune", city="Pune")
    assert s_valid.address == "FC Road, Pune"
    assert s_valid.city == "Pune"

    # Mismatch rejected
    with pytest.raises(ValidationError):
        StoreUpdate(address="FC Road, Pune", city="Nashik")

    with pytest.raises(ValidationError):
        StoreUpdate(address="College Road, Nashik", city="Mumbai")

    # When only one is supplied to StoreUpdate, schema passes
    s_addr_only = StoreUpdate(address="FC Road, Pune")
    assert s_addr_only.address == "FC Road, Pune"
    assert s_addr_only.city is None

    s_city_only = StoreUpdate(city="Nashik")
    assert s_city_only.city == "Nashik"
    assert s_addr_only.city is None


def test_phone_and_pincode_validation_retained():
    # Valid phone and pincode
    s = StoreUpdate(phone="9876543210", pincode="411004")
    assert s.phone == "9876543210"
    assert s.pincode == "411004"

    # Invalid phone (wrong length, starts with 1-5, all same)
    for bad_phone in ["12345", "98765432101", "5555555555", "1111111111"]:
        with pytest.raises(ValidationError):
            StoreUpdate(phone=bad_phone)

    # Invalid pincode (wrong length, sequential, starts with 0, all same)
    for bad_pin in ["12345", "1234567", "123456", "654321", "012345", "999999"]:
        with pytest.raises(ValidationError):
            StoreUpdate(pincode=bad_pin)


def test_reference_number_validation_retained():
    # Valid reference numbers
    for valid_ref in ["REF-001/A", "STORE_2026-X", "BRANCH/NORTH/01"]:
        c = StoreCreate(name="Sai Mart", reference_number=valid_ref)
        u = StoreUpdate(reference_number=valid_ref)
        assert c.reference_number == valid_ref
        assert u.reference_number == valid_ref

    # Invalid reference numbers (contains @, too short, placeholder 'string', etc.)
    for bad_ref in ["R@", "string", "AB", "12345", "@#$%"]:
        with pytest.raises(ValidationError):
            StoreCreate(name="Sai Mart", reference_number=bad_ref)
        with pytest.raises(ValidationError):
            StoreUpdate(reference_number=bad_ref)


# ==============================================================================
# 2. API Integration Tests (PATCH /api/v1/stores/{id})
# ==============================================================================

def test_api_store_create_and_partial_updates():
    auth = _create_tenant_and_auth("patch-test")
    headers = auth["headers"]

    # 1. Create a store with valid initial details in Nashik
    create_payload = {
        "name": "Sai Krupa Traders",
        "code": f"SKT-{uuid.uuid4().hex[:4].upper()}",
        "address": "Shop No. 5, College Road, Gangapur, Nashik",
        "city": "Nashik",
        "state": "Maharashtra",
        "pincode": "422005",
        "phone": "9876543210",
        "email": "saikrupa@example.com",
        "reference_number": "REF-001/A",
    }
    res = client.post("/api/v1/stores/", headers=headers, json=create_payload)
    assert res.status_code == 201, res.text
    store_id = res.json()["id"]

    # 2. Update ONLY the store name
    upd_name = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"name": "Sai Krupa Superstore"},
    )
    assert upd_name.status_code == 200, upd_name.text
    assert upd_name.json()["name"] == "Sai Krupa Superstore"
    # Preserved existing address and city
    assert upd_name.json()["city"] == "Nashik"
    assert upd_name.json()["address"] == "Shop No. 5, College Road, Gangapur, Nashik"

    # 3. Update ONLY address (valid Nashik address)
    upd_addr = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"address": "Gangapur Road, Nashik"},
    )
    assert upd_addr.status_code == 200, upd_addr.text
    assert upd_addr.json()["address"] == "Gangapur Road, Nashik"
    assert upd_addr.json()["city"] == "Nashik"

    # 4. Update ONLY address with conflicting location (FC Road, Pune -> conflicts with existing city Nashik)
    upd_addr_mismatch = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"address": "FC Road, Pune"},
    )
    assert upd_addr_mismatch.status_code == 422, upd_addr_mismatch.text

    # 5. Update ONLY city with conflicting city (Mumbai -> conflicts with existing address Gangapur Road, Nashik)
    upd_city_mismatch = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"city": "Mumbai"},
    )
    assert upd_city_mismatch.status_code == 422, upd_city_mismatch.text

    # 6. Update BOTH address and city consistently (Move store to Pune)
    upd_both = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={
            "address": "FC Road, Deccan Gymkhana, Shivajinagar",
            "city": "Pune",
            "pincode": "411004",
        },
    )
    assert upd_both.status_code == 200, upd_both.text
    assert upd_both.json()["city"] == "Pune"
    assert upd_both.json()["address"] == "FC Road, Deccan Gymkhana, Shivajinagar"
    assert upd_both.json()["pincode"] == "411004"

    # 7. Update with omitted optional fields (e.g. update only phone)
    upd_phone = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"phone": "9876543211"},
    )
    assert upd_phone.status_code == 200, upd_phone.text
    assert upd_phone.json()["phone"] == "9876543211"
    # Address, city, pincode, email, reference_number remain intact
    assert upd_phone.json()["city"] == "Pune"
    assert upd_phone.json()["reference_number"] == "REF-001/A"

    # 8. Explicitly pass null for optional fields (e.g. clear reference_number)
    upd_clear_ref = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"reference_number": None},
    )
    assert upd_clear_ref.status_code == 200, upd_clear_ref.text
    assert upd_clear_ref.json()["reference_number"] is None

    # Check DB persistence
    db = SessionLocal()
    st_db = db.query(Store).filter(Store.id == store_id).first()
    assert st_db.reference_number is None
    assert st_db.city == "Pune"
    assert st_db.name == "Sai Krupa Superstore"
    db.close()
