from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register_tenant_admin(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@testcorp.com"
    password = "Password123!"

    reg_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": f"Admin {prefix}",
            "password": password,
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    tenant_id = reg_resp.json()["tenant_id"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    return {
        "tenant_id": tenant_id,
        "token": token,
        "headers": headers,
        "slug": slug,
        "email": email,
    }


@pytest.fixture
def tenant_fixture():
    return _register_tenant_admin("gst-adv")


def test_create_gold_and_diamond_special_slabs(tenant_fixture):
    """Verifies that Indian 3% (Gold) and 0.25% (Diamonds) special slabs are accepted and split correctly."""
    headers = tenant_fixture["headers"]

    # 1. Gold jewellery slab 3%
    gold_resp = client.post(
        "/api/v1/gst-rates",
        json={
            "hsn_code": "7113",
            "gst_rate": "3.00",
            "description": "Gold and silver ornaments",
            "code_type": "HSN",
        },
        headers=headers,
    )
    assert gold_resp.status_code == 201, gold_resp.text
    gold_data = gold_resp.json()
    assert gold_data["hsn_code"] == "7113"
    assert Decimal(str(gold_data["gst_rate"])) == Decimal("3.00")
    assert Decimal(str(gold_data["cgst"])) == Decimal("1.50")
    assert Decimal(str(gold_data["sgst"])) == Decimal("1.50")
    assert Decimal(str(gold_data["igst"])) == Decimal("3.00")
    assert gold_data["description"] == "Gold and silver ornaments"
    assert gold_data["code_type"] == "HSN"

    # 2. Diamonds slab 0.25%
    dia_resp = client.post(
        "/api/v1/gst-rates",
        json={
            "hsn_code": "7102",
            "gst_rate": "0.25",
            "description": "Cut and polished diamonds",
            "code_type": "HSN",
        },
        headers=headers,
    )
    assert dia_resp.status_code == 201, dia_resp.text
    dia_data = dia_resp.json()
    assert dia_data["hsn_code"] == "7102"
    assert Decimal(str(dia_data["gst_rate"])) == Decimal("0.25")
    assert Decimal(str(dia_data["cgst"])) + Decimal(str(dia_data["sgst"])) == Decimal("0.25")


def test_direct_hsn_lookup_endpoint(tenant_fixture):
    """Tests fast direct lookup of active GST rate via GET /gst-rates/hsn/{hsn_code}."""
    headers = tenant_fixture["headers"]

    # Create HSN rate
    client.post(
        "/api/v1/gst-rates",
        json={"hsn_code": "8471", "gst_rate": "18.00", "description": "Computers and laptops"},
        headers=headers,
    )

    # Lookup by HSN
    resp = client.get("/api/v1/gst-rates/hsn/8471", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["hsn_code"] == "8471"
    assert Decimal(str(data["gst_rate"])) == Decimal("18.00")
    assert data["description"] == "Computers and laptops"

    # Lookup with intra_state view
    resp_intra = client.get("/api/v1/gst-rates/hsn/8471?supply_type=intra_state", headers=headers)
    assert resp_intra.status_code == 200
    assert Decimal(str(resp_intra.json()["igst"])) == Decimal("0.00")
    assert Decimal(str(resp_intra.json()["cgst"])) == Decimal("9.00")

    # Non-existent HSN lookup
    resp_404 = client.get("/api/v1/gst-rates/hsn/9999", headers=headers)
    assert resp_404.status_code == 404


def test_update_gst_rate_with_hsn_and_description(tenant_fixture):
    """Verifies PUT /gst-rates/{rate_id} correctly updates HSN, description, rate, and status."""
    headers = tenant_fixture["headers"]

    create_resp = client.post(
        "/api/v1/gst-rates",
        json={"hsn_code": "6109", "gst_rate": "5.00", "description": "Cotton t-shirts"},
        headers=headers,
    )
    rate_id = create_resp.json()["id"]

    # Update to 12%, change description and HSN
    update_resp = client.put(
        f"/api/v1/gst-rates/{rate_id}",
        json={
            "hsn_code": "6110",
            "gst_rate": "12.00",
            "description": "Premium apparel and jerseys",
            "status": True,
        },
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    updated = update_resp.json()
    assert updated["hsn_code"] == "6110"
    assert Decimal(str(updated["gst_rate"])) == Decimal("12.00")
    assert Decimal(str(updated["cgst"])) == Decimal("6.00")
    assert Decimal(str(updated["sgst"])) == Decimal("6.00")
    assert updated["description"] == "Premium apparel and jerseys"


def test_delete_gst_rate_endpoint(tenant_fixture):
    """Tests DELETE /gst-rates/{rate_id} works cleanly when no products are bound."""
    headers = tenant_fixture["headers"]

    create_resp = client.post(
        "/api/v1/gst-rates",
        json={"hsn_code": "4820", "gst_rate": "12.00", "description": "Stationery registers"},
        headers=headers,
    )
    rate_id = create_resp.json()["id"]

    # Delete
    del_resp = client.delete(f"/api/v1/gst-rates/{rate_id}", headers=headers)
    assert del_resp.status_code == 200, del_resp.text
    assert "deleted successfully" in del_resp.json()["message"]

    # Verify 404 after deletion
    get_resp = client.get(f"/api/v1/gst-rates/{rate_id}", headers=headers)
    assert get_resp.status_code == 404


def test_delete_gst_rate_blocked_when_products_linked(tenant_fixture):
    """Verifies that deleting a GST rate currently linked to active products fails with 409 Conflict."""
    headers = tenant_fixture["headers"]

    # 1. Create GST Rate
    create_resp = client.post(
        "/api/v1/gst-rates",
        json={"hsn_code": "8504", "gst_rate": "18.00", "description": "Power adapters"},
        headers=headers,
    )
    rate_id = create_resp.json()["id"]

    # 2. Create Product with this HSN code
    prod_resp = client.post(
        "/api/v1/products",
        json={
            "name": "Fast Charger 65W",
            "sku": f"CHG-{uuid.uuid4().hex[:6]}",
            "price": "1499.00",
            "gst_rate": "18.00",
            "hsn_code": "8504",
        },
        headers=headers,
    )
    assert prod_resp.status_code == 201, prod_resp.text

    # 3. Attempt to DELETE the GST rate -> should fail with 409
    del_resp = client.delete(f"/api/v1/gst-rates/{rate_id}", headers=headers)
    assert del_resp.status_code == 409
    assert "product(s) are currently associated" in str(del_resp.json()).lower()


def test_seed_default_retail_gst_rates(tenant_fixture):
    """Tests POST /gst-rates/seed-defaults to pre-populate standard retail slabs in one click."""
    headers = tenant_fixture["headers"]

    seed_resp = client.post("/api/v1/gst-rates/seed-defaults", headers=headers)
    assert seed_resp.status_code == 201, seed_resp.text
    data = seed_resp.json()

    assert data["seeded_count"] >= 10
    assert any(r["hsn_code"] == "7113" for r in data["rates"])
    assert any(r["hsn_code"] == "8471" for r in data["rates"])
    assert any(r["hsn_code"] == "9983" for r in data["rates"])

    # Calling seed a second time should be idempotent (0 newly seeded)
    seed_again = client.post("/api/v1/gst-rates/seed-defaults", headers=headers)
    assert seed_again.status_code == 201
    assert seed_again.json()["seeded_count"] == 0


def test_bulk_import_gst_rates(tenant_fixture):
    """Tests POST /gst-rates/bulk-import for multiple rates in one payload."""
    headers = tenant_fixture["headers"]

    payload = {
        "items": [
            {"hsn_code": "6401", "gst_rate": "12.00", "description": "Waterproof footwear", "code_type": "HSN"},
            {"hsn_code": "6402", "gst_rate": "12.00", "description": "Other rubber footwear", "code_type": "HSN"},
            {"hsn_code": "9965", "gst_rate": "5.00", "description": "Goods transport services", "code_type": "SAC"},
        ]
    }
    resp = client.post("/api/v1/gst-rates/bulk-import", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["created_count"] == 3

    # Re-import with an update
    payload_update = {
        "items": [
            {"hsn_code": "6401", "gst_rate": "18.00", "description": "Updated waterproof footwear", "code_type": "HSN"}
        ]
    }
    resp_up = client.post("/api/v1/gst-rates/bulk-import", json=payload_update, headers=headers)
    assert resp_up.status_code == 200
    assert resp_up.json()["updated_count"] == 1


def test_search_filter_and_pagination(tenant_fixture):
    """Tests search, code_type filter, and pagination on GET /gst-rates."""
    headers = tenant_fixture["headers"]

    # Seed first
    client.post("/api/v1/gst-rates/seed-defaults", headers=headers)

    # 1. Search keyword "apparel"
    search_resp = client.get("/api/v1/gst-rates?search=apparel", headers=headers)
    assert search_resp.status_code == 200
    items = search_resp.json()
    assert len(items) >= 1
    assert any("apparel" in (i["description"] or "").lower() for i in items)

    # 2. Filter by code_type="SAC" (Services)
    sac_resp = client.get("/api/v1/gst-rates?code_type=SAC", headers=headers)
    assert sac_resp.status_code == 200
    sac_items = sac_resp.json()
    assert len(sac_items) >= 2
    assert all(i["code_type"] == "SAC" for i in sac_items)

    # 3. Pagination
    page_resp = client.get("/api/v1/gst-rates?page=1&page_size=4", headers=headers)
    assert page_resp.status_code == 200
    page_data = page_resp.json()
    assert "total" in page_data
    assert page_data["page"] == 1
    assert page_data["page_size"] == 4
    assert len(page_data["items"]) == 4

