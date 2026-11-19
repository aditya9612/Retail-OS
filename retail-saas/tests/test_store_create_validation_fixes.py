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
# 1. Direct Schema Tests: Store Name Validation
# ==============================================================================

@pytest.mark.parametrize(
    "valid_name",
    [
        "BHAGYALAXMI KIRANA",
        "BHAGYALAXMI MART",
        "BHAGYALAXMI WAREHOUSE",
        "ABC RETAIL STORE",
        "Om",
        "Sai",
        "Riya Boutique",
        "Sai Krupa Traders",
        "Main Retail Store",
        "   BHAGYALAXMI   MART   ",  # Normalized consecutive spaces
    ],
)
def test_schema_valid_store_names(valid_name):
    schema = StoreCreate(name=valid_name)
    assert len(schema.name) >= 2


@pytest.mark.parametrize(
    "invalid_name,expected_err",
    [
        ("A", "at least 2 characters"),
        ("O", "at least 2 characters"),
        ("KIRANA", "Generic name 'KIRANA' cannot be provided alone"),
        ("MART", "Generic name 'MART' cannot be provided alone"),
        ("WAREHOUSE", "Generic name 'WAREHOUSE' cannot be provided alone"),
        ("BHAGYALAXMI", "Incomplete store name"),
        ("", "at least 2 characters"),
        ("   ", "Store name is required"),
        ("12345", "Store name cannot be numeric-only"),
        ("@#$%^&*", "must contain at least one letter"),
        ("Store@123", "Store name contains invalid characters"),
        ("Sai#Store", "Store name contains invalid characters"),
        ("AAAAAA AAAAAA", "Store name contains meaningless or invalid text"),
    ],
)
def test_schema_invalid_store_names(invalid_name, expected_err):
    with pytest.raises(ValidationError) as exc:
        StoreCreate(name=invalid_name)
    assert expected_err.lower() in str(exc.value).lower()


# ==============================================================================
# 2. Direct Schema Tests: Complete Address Validation
# ==============================================================================

@pytest.mark.parametrize(
    "valid_address",
    [
        "Shop No. 5, College Road, Gangapur, Nashik",
        "FC Road, Deccan Gymkhana, Shivajinagar",
        "Plot 45/A, Sector-18, Near St. John's School",
        "Linking Road, Bandra West",
        "Shop 12, Phoenix Marketcity, Kurla West, Mumbai",
    ],
)
def test_schema_valid_addresses(valid_address):
    schema = StoreCreate(name="Bhagyalaxmi Mart", address=valid_address)
    assert schema.address == valid_address


@pytest.mark.parametrize(
    "invalid_address,expected_err",
    [
        ("Road", "at least 5 characters"),
        ("Main Road", "only road name provided"),
        ("Nashik", "only city/location name provided"),
        ("Mumbai", "only city/location name provided"),
        ("House No. 10", "only house/shop number provided"),
        ("Shop No. 5, Main Road", "Incomplete address details"),
        ("", "Address is required"),
        ("    ", "Address is required"),
        ("asdf asdf asdf", "meaningless or invalid text"),
        ("!!! @@@ ###", "Address must contain at least one letter"),
    ],
)
def test_schema_invalid_addresses(invalid_address, expected_err):
    with pytest.raises(ValidationError) as exc:
        StoreCreate(name="Bhagyalaxmi Mart", address=invalid_address)
    assert expected_err.lower() in str(exc.value).lower()


# ==============================================================================
# 3. Direct Schema Tests: City Field Validation
# ==============================================================================

@pytest.mark.parametrize(
    "valid_city",
    [
        "Nashik",
        "Pune",
        "Mumbai",
        "Nagpur",
        "Thane",
    ],
)
def test_schema_valid_cities(valid_city):
    schema = StoreCreate(name="Bhagyalaxmi Mart", city=valid_city)
    assert schema.city.lower() == valid_city.lower()


@pytest.mark.parametrize(
    "invalid_city,expected_err",
    [
        ("12345", "City cannot be numeric-only"),
        ("@#$%", "City contains invalid special characters"),
        ("", "City is required"),
        ("   ", "City is required"),
        ("Shop 5, College Road, Nashik", "City field must contain only the city name"),
        ("Nashik, Maharashtra, India", "City field must contain only the city name"),
        ("Maharashtra", "City cannot be a state or union territory name"),
        ("India", "Please enter a valid city name"),
        ("AAAA", "City cannot consist of repetitive characters"),
    ],
)
def test_schema_invalid_cities(invalid_city, expected_err):
    with pytest.raises(ValidationError) as exc:
        StoreCreate(name="Bhagyalaxmi Mart", city=invalid_city)
    assert expected_err.lower() in str(exc.value).lower()


# ==============================================================================
# 4. Direct Schema Tests: Address & City Matching Validation
# ==============================================================================

def test_schema_address_city_match_success():
    # Gangapur Road, Nashik + Nashik
    s1 = StoreCreate(name="Bhagyalaxmi Kirana", address="Gangapur Road, Nashik", city="Nashik")
    assert s1.city == "Nashik"

    # FC Road, Pune + Pune
    s2 = StoreCreate(name="Bhagyalaxmi Mart", address="FC Road, Pune", city="Pune")
    assert s2.city == "Pune"

    # Full address with locality belonging to Nashik
    s3 = StoreCreate(
        name="Bhagyalaxmi Warehouse",
        address="Shop No. 5, College Road, Gangapur, Nashik",
        city="Nashik",
    )
    assert s3.city == "Nashik"


def test_schema_address_city_match_rejections():
    # FC Road, Pune + Nashik -> Reject
    with pytest.raises(ValidationError) as exc1:
        StoreCreate(name="Bhagyalaxmi Mart", address="FC Road, Pune", city="Nashik")
    assert "does not match city 'nashik'" in str(exc1.value).lower()

    # College Road, Nashik + Mumbai -> Reject
    with pytest.raises(ValidationError) as exc2:
        StoreCreate(name="Bhagyalaxmi Mart", address="College Road, Nashik", city="Mumbai")
    assert "does not match city 'mumbai'" in str(exc2.value).lower()

    # Mumbai address + Pune -> Reject
    with pytest.raises(ValidationError) as exc3:
        StoreCreate(
            name="Bhagyalaxmi Mart",
            address="Shop 12, Phoenix Marketcity, Kurla West, Mumbai",
            city="Pune",
        )
    assert "does not match city 'pune'" in str(exc3.value).lower()

    # Nashik + Nashik -> Reject (fails complete address check: city only)
    with pytest.raises(ValidationError) as exc4:
        StoreCreate(name="Bhagyalaxmi Mart", address="Nashik", city="Nashik")
    assert "only city/location name provided" in str(exc4.value).lower()


# ==============================================================================
# 5. Integration API Tests: POST /api/v1/stores/
# ==============================================================================

def test_api_store_create_positive_cases():
    auth = _create_tenant_and_auth("pos-test")
    headers = auth["headers"]

    test_cases = [
        {
            "name": "BHAGYALAXMI KIRANA",
            "address": "Shop No. 5, College Road, Gangapur, Nashik",
            "city": "Nashik",
            "state": "Maharashtra",
            "pincode": "422005",
            "phone": "9876543210",
        },
        {
            "name": "BHAGYALAXMI MART",
            "address": "FC Road, Deccan Gymkhana, Shivajinagar",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411004",
            "phone": "9876543211",
        },
        {
            "name": "BHAGYALAXMI WAREHOUSE",
            "address": "Hadapsar Industrial Estate, Pune",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411028",
            "phone": "9876543212",
        },
        {
            "name": "ABC RETAIL STORE",
            "address": "Shop 12, Phoenix Marketcity, Kurla West, Mumbai",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400070",
            "phone": "9876543213",
        },
        {
            "name": "Om",
            "address": "Shop 1, Linking Road, Bandra West",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400050",
            "phone": "9876543214",
        },
    ]

    for tc in test_cases:
        code = f"STR-{uuid.uuid4().hex[:4].upper()}"
        payload = {**tc, "code": code}
        res = client.post("/api/v1/stores/", headers=headers, json=payload)
        assert res.status_code == 201, f"Failed for {tc['name']}: {res.text}"
        data = res.json()
        assert data["name"] == tc["name"]
        assert data["city"].lower() == tc["city"].lower()


def test_api_store_create_negative_cases_and_no_db_insertion():
    auth = _create_tenant_and_auth("neg-test")
    headers = auth["headers"]
    db = SessionLocal()

    # Count stores initially for this tenant
    init_count = db.query(Store).filter(Store.tenant_id == auth["tenant_id"]).count()
    db.close()

    negative_payloads = [
        # 1. Single character store name
        {"name": "A", "code": "ST-A1", "address": "FC Road, Pune", "city": "Pune"},
        # 2. Generic name alone
        {"name": "KIRANA", "code": "ST-K1", "address": "FC Road, Pune", "city": "Pune"},
        # 3. Incomplete store name
        {"name": "BHAGYALAXMI", "code": "ST-B1", "address": "FC Road, Pune", "city": "Pune"},
        # 4. Road-only address
        {"name": "BHAGYALAXMI MART", "code": "ST-R1", "address": "Main Road", "city": "Nashik"},
        # 5. House-only address
        {"name": "BHAGYALAXMI MART", "code": "ST-H1", "address": "House No. 10", "city": "Nashik"},
        # 6. City-only address
        {"name": "BHAGYALAXMI MART", "code": "ST-C1", "address": "Nashik", "city": "Nashik"},
        # 7. Incomplete address
        {"name": "BHAGYALAXMI MART", "code": "ST-I1", "address": "Shop No. 5, Main Road", "city": "Nashik"},
        # 8. Numeric-only city
        {"name": "BHAGYALAXMI MART", "code": "ST-NC1", "address": "FC Road, Pune", "city": "12345"},
        # 9. Special character city
        {"name": "BHAGYALAXMI MART", "code": "ST-SC1", "address": "FC Road, Pune", "city": "@#$%"},
        # 10. Address-city mismatch: FC Road, Pune + Nashik
        {"name": "BHAGYALAXMI MART", "code": "ST-M1", "address": "FC Road, Pune", "city": "Nashik"},
        # 11. Address-city mismatch: College Road, Nashik + Mumbai
        {"name": "BHAGYALAXMI MART", "code": "ST-M2", "address": "College Road, Nashik", "city": "Mumbai"},
        # 12. Address-city mismatch: Mumbai address + Pune
        {
            "name": "BHAGYALAXMI MART",
            "code": "ST-M3",
            "address": "Shop 12, Phoenix Marketcity, Kurla West, Mumbai",
            "city": "Pune",
        },
    ]

    for payload in negative_payloads:
        res = client.post("/api/v1/stores/", headers=headers, json=payload)
        assert res.status_code == 422, f"Expected 422 for payload {payload}, got {res.status_code}: {res.text}"

    # Verify no records were inserted into the database
    db = SessionLocal()
    final_count = db.query(Store).filter(Store.tenant_id == auth["tenant_id"]).count()
    db.close()
    assert final_count == init_count, f"Expected {init_count} stores in DB, found {final_count}"


# ==============================================================================
# 6. Regression Tests: Store Listing, Update, and Delete Unaffected
# ==============================================================================

def test_api_regression_store_crud():
    auth = _create_tenant_and_auth("regr-test")
    headers = auth["headers"]

    # 1. Create store with valid payload
    create_payload = {
        "name": "Sai Krupa Traders",
        "code": f"SKT-{uuid.uuid4().hex[:4].upper()}",
        "address": "Shop No. 5, College Road, Gangapur, Nashik",
        "city": "Nashik",
        "state": "Maharashtra",
        "pincode": "422005",
        "phone": "9876543210",
        "reference_number": "REF-001/A",
    }
    create_res = client.post("/api/v1/stores/", headers=headers, json=create_payload)
    assert create_res.status_code == 201, create_res.text
    store_id = create_res.json()["id"]

    # 2. Get store list (GET /api/v1/stores/)
    list_res = client.get("/api/v1/stores/", headers=headers)
    assert list_res.status_code == 200, list_res.text
    res_data = list_res.json()
    stores = res_data if isinstance(res_data, list) else res_data.get("items", [])
    assert any(s["id"] == store_id for s in stores)

    # 3. Get store by ID (GET /api/v1/stores/{id})
    get_res = client.get(f"/api/v1/stores/{store_id}", headers=headers)
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["name"] == "Sai Krupa Traders"

    # 4. Partial update (PATCH /api/v1/stores/{id})
    # StoreUpdate remains flexible and allows updating specific fields
    patch_res = client.patch(
        f"/api/v1/stores/{store_id}",
        headers=headers,
        json={"name": "Sai Krupa Superstore"},
    )
    assert patch_res.status_code == 200, patch_res.text
    assert patch_res.json()["name"] == "Sai Krupa Superstore"

    # 5. Delete store (DELETE /api/v1/stores/{id})
    del_res = client.delete(f"/api/v1/stores/{store_id}", headers=headers)
    assert del_res.status_code == 200, del_res.text
    assert del_res.json()["success"] is True

    # Verify soft-deleted / deactivated
    get_del = client.get(f"/api/v1/stores/{store_id}", headers=headers)
    assert get_del.status_code == 200
    assert get_del.json()["is_active"] is False
