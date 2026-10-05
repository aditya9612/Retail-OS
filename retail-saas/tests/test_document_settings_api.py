import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def doc_settings_setup(unique_slug):
    email = f"docset-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Doc Settings Tenant",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Docset Admin",
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
        json={"name": "Docset Store", "code": f"D{unique_slug[:3]}"},
        headers=headers,
    ).json()

    return {
        "headers": headers,
        "store_id": store["id"],
        "slug": unique_slug,
    }


def test_get_document_settings_initially_none(doc_settings_setup):
    headers = doc_settings_setup["headers"]
    # Get raw setting before update -> returns None / 200 with null
    res = client.get("/api/v1/document-settings", headers=headers)
    assert res.status_code == 200
    assert res.json() is None


def test_get_effective_branding_defaults(doc_settings_setup):
    headers = doc_settings_setup["headers"]
    # Get effective branding -> falls back to tenant name and defaults
    res = client.get("/api/v1/document-settings/effective", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["business_name"] == "Doc Settings Tenant"
    assert data["invoice_prefix"] == "INV"
    assert data["bill_prefix"] == "BILL"
    assert data["show_gstin"] is True
    assert data["show_qr"] is True


def test_update_and_get_tenant_document_setting(doc_settings_setup):
    headers = doc_settings_setup["headers"]
    payload = {
        "business_name": "Acme Megastore",
        "address": "123 High Street, Mumbai",
        "phone": "+91 9876543210",
        "email": "contact@acme.com",
        "website": "https://acme.example.com",
        "gstin": "27AAPCA1234A1Z5",
        "footer_text": "Thank you for shopping at Acme!",
        "invoice_prefix": "ACME-INV",
        "bill_prefix": "ACME-BILL",
        "show_gstin": True,
        "show_qr": True,
        "show_signature": True,
        "show_payment_details": True,
    }
    update_res = client.put("/api/v1/document-settings", json=payload, headers=headers)
    assert update_res.status_code == 200
    res_data = update_res.json()
    assert res_data["business_name"] == "Acme Megastore"
    assert res_data["invoice_prefix"] == "ACME-INV"
    assert res_data["show_signature"] is True

    # Verify get effective returns updated values
    eff_res = client.get("/api/v1/document-settings/effective", headers=headers)
    assert eff_res.status_code == 200
    eff_data = eff_res.json()
    assert eff_data["business_name"] == "Acme Megastore"
    assert eff_data["invoice_prefix"] == "ACME-INV"
    assert eff_data["footer_text"] == "Thank you for shopping at Acme!"


def test_store_level_branding_override(doc_settings_setup):
    headers = doc_settings_setup["headers"]
    store_id = doc_settings_setup["store_id"]

    # Set tenant branding
    client.put(
        "/api/v1/document-settings",
        json={"business_name": "Tenant Brand", "invoice_prefix": "TEN-INV"},
        headers=headers,
    )

    # Set store branding override
    client.put(
        f"/api/v1/document-settings?store_id={store_id}",
        json={"business_name": "Store Branch Brand", "invoice_prefix": "STR-INV"},
        headers=headers,
    )

    # Effective without store_id gives tenant brand
    tenant_eff = client.get("/api/v1/document-settings/effective", headers=headers).json()
    assert tenant_eff["business_name"] == "Tenant Brand"
    assert tenant_eff["invoice_prefix"] == "TEN-INV"

    # Effective with store_id gives store override
    store_eff = client.get(f"/api/v1/document-settings/effective?store_id={store_id}", headers=headers).json()
    assert store_eff["business_name"] == "Store Branch Brand"
    assert store_eff["invoice_prefix"] == "STR-INV"


def test_upload_logo_security_and_success(doc_settings_setup):
    headers = doc_settings_setup["headers"]

    # 1. Invalid extension rejection (.exe / .pdf)
    bad_file = ("bad.exe", b"not-a-real-exe", "application/octet-stream")
    res_bad_ext = client.post(
        "/api/v1/document-settings/logo",
        files={"file": bad_file},
        headers=headers,
    )
    assert res_bad_ext.status_code == 400

    # 2. Invalid MIME type rejection
    bad_mime = ("image.png", b"fake-png-content", "text/plain")
    res_bad_mime = client.post(
        "/api/v1/document-settings/logo",
        files={"file": bad_mime},
        headers=headers,
    )
    assert res_bad_mime.status_code == 400

    # 3. Valid PNG upload
    # Minimal 1x1 PNG binary
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
        b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    good_file = ("store_logo.png", png_bytes, "image/png")
    upload_res = client.post(
        "/api/v1/document-settings/logo",
        files={"file": good_file},
        headers=headers,
    )
    assert upload_res.status_code == 200
    upload_data = upload_res.json()
    assert "logo_url" in upload_data
    assert upload_data["logo_url"].startswith("/uploads/logos/")
    assert upload_data["setting"]["logo_path"] == upload_data["logo_url"]


def test_tenant_isolation_on_document_settings(doc_settings_setup, unique_slug):
    # Register a second tenant
    headers_a = doc_settings_setup["headers"]
    client.put(
        "/api/v1/document-settings",
        json={"business_name": "Tenant A Secret Brand"},
        headers=headers_a,
    )

    slug_b = f"b-{unique_slug}"
    email_b = f"tenant-b-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Tenant B Corp",
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
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    # Tenant B should see their own default branding, not Tenant A's
    eff_b = client.get("/api/v1/document-settings/effective", headers=headers_b).json()
    assert eff_b["business_name"] == "Tenant B Corp"
    assert eff_b["business_name"] != "Tenant A Secret Brand"


def test_delete_logo(doc_settings_setup):
    headers = doc_settings_setup["headers"]

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
        b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    good_file = ("delete_me.png", png_bytes, "image/png")
    upload_res = client.post(
        "/api/v1/document-settings/logo",
        files={"file": good_file},
        headers=headers,
    )
    assert upload_res.status_code == 200
    assert upload_res.json()["setting"]["logo_path"] is not None

    # Delete logo
    del_res = client.delete("/api/v1/document-settings/logo", headers=headers)
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["message"] == "Logo deleted successfully"
    assert del_data["setting"]["logo_path"] is None

    # Delete again -> 404
    del_again = client.delete("/api/v1/document-settings/logo", headers=headers)
    assert del_again.status_code == 404


