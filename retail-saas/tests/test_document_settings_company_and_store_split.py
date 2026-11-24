import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def split_setup(unique_slug):
    email = f"split-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Split Corp",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Split Admin",
            "password": "Password123!",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    store = client.post(
        "/api/v1/stores",
        json={"name": "Split Store Pune", "code": f"SP{unique_slug[:3]}"},
        headers=headers,
    ).json()

    return {
        "headers": headers,
        "store_id": store["id"],
        "slug": unique_slug,
    }


def test_company_document_settings_flow(split_setup):
    headers = split_setup["headers"]

    # 1. Company GET initially None
    res = client.get("/api/v1/document-settings", headers=headers)
    assert res.status_code == 200
    assert res.json() is None

    # 2. Company PUT update (no store_id -> company level)
    payload = {
        "business_name": "Acme Global HQ",
        "address": "100 Corporate Tower, Mumbai",
        "phone": "+919876543210",
        "email": "hq@acme.com",
        "gstin": "27AAPCA1234A1Z5",
        "invoice_prefix": "HQ-INV",
        "show_signature": True,
    }
    put_res = client.put("/api/v1/document-settings", json=payload, headers=headers)
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["business_name"] == "Acme Global HQ"
    assert data["store_id"] is None
    assert data["invoice_prefix"] == "HQ-INV"

    # 3. Company POST alias update (no store_id -> company level)
    post_res = client.post(
        "/api/v1/document-settings",
        json={"terms_and_conditions": "HQ Terms 123"},
        headers=headers,
    )
    assert post_res.status_code == 200
    assert post_res.json()["terms_and_conditions"] == "HQ Terms 123"

    # 4. Company effective branding
    eff_res = client.get("/api/v1/document-settings/effective", headers=headers)
    assert eff_res.status_code == 200
    assert eff_res.json()["business_name"] == "Acme Global HQ"


def test_store_document_settings_flow(split_setup):
    headers = split_setup["headers"]
    store_id = split_setup["store_id"]

    # 1. Store GET initially None (inherits company defaults)
    res = client.get(f"/api/v1/document-settings?store_id={store_id}", headers=headers)
    assert res.status_code == 200
    assert res.json() is None

    # 2. Store PUT override (store_id query param)
    store_payload = {
        "business_name": "Acme Pune Branch",
        "address": "Shop 12, FC Road, Pune",
        "phone": "9876543210",
        "email": "pune@acme.com",
        "invoice_prefix": "PUN-INV",
    }
    put_res = client.put(f"/api/v1/document-settings?store_id={store_id}", json=store_payload, headers=headers)
    assert put_res.status_code == 200
    store_data = put_res.json()
    assert store_data["business_name"] == "Acme Pune Branch"
    assert store_data["store_id"] == store_id
    assert store_data["invoice_prefix"] == "PUN-INV"

    # 3. Store POST alias
    post_res = client.post(
        f"/api/v1/document-settings?store_id={store_id}",
        json={"bill_prefix": "PUN-BILL"},
        headers=headers,
    )
    assert post_res.status_code == 200
    assert post_res.json()["bill_prefix"] == "PUN-BILL"

    # 4. Store effective branding
    eff_res = client.get(f"/api/v1/document-settings/effective?store_id={store_id}", headers=headers)
    assert eff_res.status_code == 200
    assert eff_res.json()["business_name"] == "Acme Pune Branch"
    assert eff_res.json()["invoice_prefix"] == "PUN-INV"

    # 5. Delete store override -> reverts to company
    del_res = client.delete(f"/api/v1/document-settings?store_id={store_id}", headers=headers)
    assert del_res.status_code == 200

    # 6. GET store settings is None again
    get_after = client.get(f"/api/v1/document-settings?store_id={store_id}", headers=headers)
    assert get_after.status_code == 200
    assert get_after.json() is None


def test_unified_post_and_invalid_boolean_syntax(split_setup):
    headers = split_setup["headers"]

    # 1. Unified POST /api/v1/document-settings
    res = client.post(
        "/api/v1/document-settings",
        json={"business_name": "Unified Post Brand"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["business_name"] == "Unified Post Brand"

    # 2. Test malformed JSON with unquoted boolean value (the tester's scenario)
    bad_json_body = '{\n  "show_signature": Yes,\n}'
    bad_res = client.put(
        "/api/v1/document-settings",
        content=bad_json_body,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert bad_res.status_code == 422
    err_json = bad_res.json()
    assert "Expected a boolean: true or false for 'show_signature'" in err_json["message"]
