import uuid
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.store import StoreCreate, StoreUpdate

client = TestClient(app)


def create_tenant_and_admin(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@test.com"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "store_name": f"Tenant {slug}",
            "domain": slug,
            "owner_email": email,
            "owner_name": f"Admin {prefix}",
            "password": "Password123!",
            "plan_code": "enterprise",
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    tenant_id = reg_resp.json()["tenant_id"]

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
    }


# ==============================================================================
# 1. Direct Schema Validation Unit Tests (StoreCreate & StoreUpdate)
# ==============================================================================

def test_schema_valid_address():
    """Valid addresses with letters, digits, and standard punctuation should pass."""
    valid_addresses = [
        "Linking Road, Bandra West",
        "Dadar West",
        "123 High Street",
        "Shop No: 12, Ground Floor, Central Mall",
        "Plot 45/A, Sector-18, Near St. John's School",
        "Flat #402, B-Wing, M.G. Road (Opp. Bus Depot)",
        "FC Road, Deccan Gymkhana, Shivajinagar",
    ]
    for addr in valid_addresses:
        # StoreCreate
        create_schema = StoreCreate(name="Branch One", address=addr)
        assert create_schema.address == addr

        # StoreUpdate
        update_schema = StoreUpdate(address=addr)
        assert update_schema.address == addr


def test_schema_empty_address_rejected():
    """Empty or whitespace-only addresses should be rejected."""
    for empty in ["", "   ", "\t", "\n"]:
        with pytest.raises(ValidationError) as exc_create:
            StoreCreate(name="Branch One", address=empty)
        assert "Address is required" in str(exc_create.value)

        with pytest.raises(ValidationError) as exc_update:
            StoreUpdate(address=empty)
        assert "Address is required" in str(exc_update.value)


def test_schema_address_with_normal_spaces():
    """Addresses with normal internal spaces or multiple spaces should be preserved and stripped."""
    addr_with_spaces = "  123   Main   Street,   Sector 5  "
    create_schema = StoreCreate(name="Branch One", address=addr_with_spaces)
    assert create_schema.address == "123   Main   Street,   Sector 5"

    update_schema = StoreUpdate(address=addr_with_spaces)
    assert update_schema.address == "123   Main   Street,   Sector 5"


def test_schema_address_with_commas_and_standard_characters():
    """Addresses with commas, colons, slashes, hyphens, periods, hash, ampersand, apostrophe, parentheses."""
    addr = "Shop No: 12, Plot 45/A, Sector-18, St. Mary's Road (Near Town & Country Club) #5"
    create_schema = StoreCreate(name="Branch One", address=addr)
    assert create_schema.address == addr

    update_schema = StoreUpdate(address=addr)
    assert update_schema.address == addr


def test_schema_invalid_address_rejected():
    """Short (<5 chars), pure numbers, pure symbols, or forbidden special chars must be rejected."""
    # Too short (< 5 chars)
    with pytest.raises(ValidationError) as exc:
        StoreCreate(name="Branch One", address="Road")
    assert "Address must contain at least 5 characters" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        StoreUpdate(address="Road")
    assert "Address must contain at least 5 characters" in str(exc.value)

    # Pure digits (no letters)
    with pytest.raises(ValidationError) as exc:
        StoreCreate(name="Branch One", address="1234567")
    assert "Address must contain at least one letter" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        StoreUpdate(address="1234567")
    assert "Address must contain at least one letter" in str(exc.value)

    # Pure symbols
    with pytest.raises(ValidationError) as exc:
        StoreCreate(name="Branch One", address="!@#$%^&*")
    assert "Address must contain at least one letter" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        StoreUpdate(address="!@#$%^&*")
    assert "Address must contain at least one letter" in str(exc.value)

    # Invalid special characters like $, %, @, !
    with pytest.raises(ValidationError) as exc:
        StoreCreate(name="Branch One", address="Shop @ Mall #12 $50")
    assert "Address contains invalid characters" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        StoreUpdate(address="Shop @ Mall #12 $50")
    assert "Address contains invalid characters" in str(exc.value)


def test_schema_none_address_preserved():
    """None / omitted address remains optional."""
    create_schema = StoreCreate(name="Branch One", address=None)
    assert create_schema.address is None

    update_schema = StoreUpdate(address=None)
    assert update_schema.address is None


# ==============================================================================
# 2. Integration Tests: Add Store (POST /api/v1/stores/)
# ==============================================================================

def test_add_store_address_validation():
    tenant = create_tenant_and_admin("add-store-addr")
    headers = tenant["headers"]

    # 1. Valid address with letters only (no numbers)
    resp1 = client.post(
        "/api/v1/stores/",
        json={
            "name": "Bandra Retail Branch",
            "code": f"BND-{uuid.uuid4().hex[:4].upper()}",
            "address": "Linking Road, Bandra West",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400050",
            "phone": "9820011223",
        },
        headers=headers,
    )
    assert resp1.status_code == 201, resp1.text
    assert resp1.json()["address"] == "Linking Road, Bandra West"

    # 2. Valid address with standard characters (colons, commas, slashes, etc.)
    resp2 = client.post(
        "/api/v1/stores/",
        json={
            "name": "Central Mall Outlet",
            "code": f"CML-{uuid.uuid4().hex[:4].upper()}",
            "address": "Shop No: 12, Ground Floor, Central Mall, M.G. Road",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "phone": "9820011224",
        },
        headers=headers,
    )
    assert resp2.status_code == 201, resp2.text
    assert resp2.json()["address"] == "Shop No: 12, Ground Floor, Central Mall, M.G. Road"

    # 3. Empty address rejected with 422
    resp_empty = client.post(
        "/api/v1/stores/",
        json={
            "name": "Empty Address Branch",
            "code": f"EMP-{uuid.uuid4().hex[:4].upper()}",
            "address": "   ",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "phone": "9820011225",
        },
        headers=headers,
    )
    assert resp_empty.status_code == 422, resp_empty.text

    # 4. Invalid characters in address rejected with 422
    resp_invalid = client.post(
        "/api/v1/stores/",
        json={
            "name": "Invalid Char Branch",
            "code": f"INV-{uuid.uuid4().hex[:4].upper()}",
            "address": "Shop @ Market Mall $500",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "phone": "9820011226",
        },
        headers=headers,
    )
    assert resp_invalid.status_code == 422, resp_invalid.text
    assert "Address contains invalid characters" in resp_invalid.text


# ==============================================================================
# 3. Integration Tests: Update Store (PATCH /api/v1/stores/{store_id})
# ==============================================================================

def test_update_store_address_validation():
    tenant = create_tenant_and_admin("upd-store-addr")
    headers = tenant["headers"]

    # 1. Create a store initially
    create_resp = client.post(
        "/api/v1/stores/",
        json={
            "name": "Original Branch",
            "code": f"ORG-{uuid.uuid4().hex[:4].upper()}",
            "address": "123 Initial Street, Andheri East",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400069",
            "phone": "9820011227",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    store_id = create_resp.json()["id"]

    # 2. Update address to valid address WITHOUT building numbers
    # (previously failed with 'Address must include a building number or other location number')
    upd_resp1 = client.patch(
        f"/api/v1/stores/{store_id}",
        json={"address": "Linking Road, Bandra West"},
        headers=headers,
    )
    assert upd_resp1.status_code == 200, upd_resp1.text
    assert upd_resp1.json()["address"] == "Linking Road, Bandra West"

    # 3. Update address with colons, commas, and standard characters
    upd_resp2 = client.patch(
        f"/api/v1/stores/{store_id}",
        json={"address": "Shop No: 402, 4th Floor, Phoenix Marketcity, L.B.S. Marg"},
        headers=headers,
    )
    assert upd_resp2.status_code == 200, upd_resp2.text
    assert upd_resp2.json()["address"] == "Shop No: 402, 4th Floor, Phoenix Marketcity, L.B.S. Marg"

    # 4. Update address with empty string rejected with 422
    upd_empty = client.patch(
        f"/api/v1/stores/{store_id}",
        json={"address": "   "},
        headers=headers,
    )
    assert upd_empty.status_code == 422, upd_empty.text

    # 5. Update address with invalid characters rejected with 422
    upd_invalid = client.patch(
        f"/api/v1/stores/{store_id}",
        json={"address": "Shop @ Central Mall %!"},
        headers=headers,
    )
    assert upd_invalid.status_code == 422, upd_invalid.text
    assert "Address contains invalid characters" in upd_invalid.text

    # 6. Updating another field (phone) without providing address preserves address
    upd_phone = client.patch(
        f"/api/v1/stores/{store_id}",
        json={"phone": "9820099887"},
        headers=headers,
    )
    assert upd_phone.status_code == 200, upd_phone.text
    assert upd_phone.json()["phone"] == "9820099887"
    assert upd_phone.json()["address"] == "Shop No: 402, 4th Floor, Phoenix Marketcity, L.B.S. Marg"

