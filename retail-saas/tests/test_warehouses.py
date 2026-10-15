import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def tenant_fixture():
    slug = f"wh-{uuid.uuid4().hex[:8]}"
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
    return {"headers": headers, "slug": slug}


def test_warehouse_create_valid_and_invalid_address(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Valid warehouse creation
    valid_payload = {
        "name": "Central Hub Pune",
        "code": "WH-PUN-01",
        "address": "Plot 42, MIDC Bhosari, Pune, Maharashtra",
    }
    resp = client.post("/api/v1/warehouses", json=valid_payload, headers=headers)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["name"] == "Central Hub Pune"
    assert created["code"] == "WH-PUN-01"
    assert created["address"] == "Plot 42, MIDC Bhosari, Pune, Maharashtra"

    # Invalid addresses that must be rejected (422)
    invalid_addresses = [
        "1234",          # Reported in screenshot: purely numeric short address
        "12345",         # purely numeric
        "99999999",      # numeric only
        "####",          # special chars only
        "aaaaa",         # repeating single char
        "test",          # placeholder
        "string",        # placeholder
        "dummy",         # placeholder
        "   ",           # whitespace
    ]
    for bad_addr in invalid_addresses:
        bad_payload = {
            "name": "Valid Warehouse Name",
            "code": f"WH-{uuid.uuid4().hex[:4].upper()}",
            "address": bad_addr,
        }
        res = client.post("/api/v1/warehouses", json=bad_payload, headers=headers)
        assert res.status_code == 422, f"Expected 422 for address '{bad_addr}', got {res.status_code}: {res.text}"


def test_warehouse_create_invalid_name_and_code(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Invalid names
    for bad_name in ["ppp", "12345", "string", "test", ""]:
        res = client.post(
            "/api/v1/warehouses",
            json={
                "name": bad_name,
                "code": f"WH-{uuid.uuid4().hex[:4].upper()}",
            },
            headers=headers,
        )
        assert res.status_code == 422, f"Expected 422 for name '{bad_name}', got {res.status_code}: {res.text}"

    # Invalid codes
    for bad_code in ["00000", "12345", "string", ""]:
        res = client.post(
            "/api/v1/warehouses",
            json={
                "name": "Valid Warehouse",
                "code": bad_code,
            },
            headers=headers,
        )
        assert res.status_code == 422, f"Expected 422 for code '{bad_code}', got {res.status_code}: {res.text}"


def test_warehouse_patch_invalid_json_expected_value_message(tenant_fixture):
    headers = tenant_fixture["headers"]

    # Create warehouse first
    resp = client.post(
        "/api/v1/warehouses",
        json={
            "name": "West Coast Warehouse",
            "code": "WH-WEST-01",
            "address": "Gala No 5, Highway Hub, Mumbai",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    wh_id = resp.json()["id"]

    # 1. QA reported: PATCH with unquoted is_active: fdf
    bad_json_resp = client.patch(
        f"/api/v1/warehouses/{wh_id}",
        content=b'{\n  "is_active": fdf\n}',
        headers={**headers, "Content-Type": "application/json"},
    )
    assert bad_json_resp.status_code == 422, bad_json_resp.text
    data = bad_json_resp.json()
    assert data["errors"][0]["field"] == "is_active"
    assert "Expected a boolean: true or false" in data["message"]

    # 2. QA reported: PATCH with missing value: "is_active": 
    bad_json_resp2 = client.patch(
        f"/api/v1/warehouses/{wh_id}",
        content=b'{\n  "is_active": \n}',
        headers={**headers, "Content-Type": "application/json"},
    )
    assert bad_json_resp2.status_code == 422, bad_json_resp2.text
    data2 = bad_json_resp2.json()
    assert data2["errors"][0]["field"] == "is_active"
    assert "Expected a boolean: true or false" in data2["message"]

    # 3. PATCH with invalid address: "1234"
    bad_addr_resp = client.patch(
        f"/api/v1/warehouses/{wh_id}",
        json={"address": "1234"},
        headers=headers,
    )
    assert bad_addr_resp.status_code == 422

    # 4. Valid PATCH
    good_patch = client.patch(
        f"/api/v1/warehouses/{wh_id}",
        json={"name": "Renamed Coast Warehouse", "is_active": False},
        headers=headers,
    )
    assert good_patch.status_code == 200
    assert good_patch.json()["name"] == "Renamed Coast Warehouse"
    assert good_patch.json()["is_active"] is False
