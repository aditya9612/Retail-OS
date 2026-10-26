import io
import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.store import Store
from app.models.user import User
from app.services.document_settings_service import DocumentSettingsService

client = TestClient(app)

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
    b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def create_branding_tenant(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"owner-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Branding Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Branding Admin",
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
    user = db.query(User).filter(User.email == email).first()
    tenant_id = user.tenant_id

    store = Store(
        tenant_id=tenant_id,
        name=f"BrandStore-{uuid.uuid4().hex[:4]}",
        address="100 Brand St",
        is_active=True,
        is_main=True,
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    store_id = store.id
    db.close()

    return {
        "headers": headers,
        "tenant_id": tenant_id,
        "store_id": store_id,
        "slug": slug,
    }


def test_document_logo_upload_auto_syncs_to_storefront():
    """Uploading a logo via Document Settings auto-syncs to the E-Commerce Storefront."""
    tenant = create_branding_tenant("doc-sync")
    headers = tenant["headers"]

    # 1. Upload logo in Document Settings
    file_payload = ("logo.png", io.BytesIO(TINY_PNG), "image/png")
    upload_res = client.post(
        "/api/v1/document-settings/logo",
        files={"file": file_payload},
        headers=headers,
    )
    assert upload_res.status_code == 200, upload_res.text
    doc_logo_url = upload_res.json()["logo_url"]
    assert doc_logo_url.startswith("/uploads/logos/")

    # 2. Verify Storefront settings now automatically has this logo
    sf_res = client.get("/api/v1/ecommerce/storefront/settings", headers=headers)
    assert sf_res.status_code == 200
    sf_data = sf_res.json()
    assert sf_data["logo_url"] == doc_logo_url


def test_storefront_logo_upload_auto_syncs_to_document_branding():
    """Uploading a logo via Storefront Asset Upload auto-syncs to Document Effective Branding."""
    tenant = create_branding_tenant("sf-sync")
    headers = tenant["headers"]

    # 1. Upload logo in Storefront
    file_payload = ("sf_logo.png", io.BytesIO(TINY_PNG), "image/png")
    sf_upload = client.post(
        "/api/v1/ecommerce/storefront/upload-asset",
        data={"asset_type": "logo"},
        files={"file": file_payload},
        headers=headers,
    )
    assert sf_upload.status_code == 200, sf_upload.text
    sf_logo_url = sf_upload.json()["url"]
    assert sf_logo_url.startswith("/uploads/storefront/")

    # 2. Verify Document Effective Branding immediately reflects this logo
    eff_res = client.get("/api/v1/document-settings/effective", headers=headers)
    assert eff_res.status_code == 200
    eff_data = eff_res.json()
    assert eff_data["logo_url"] == sf_logo_url


def test_store_level_branding_sync_and_isolation():
    """Store-level logo uploaded in Storefront propagates to store-level document branding."""
    tenant = create_branding_tenant("store-brand")
    headers = tenant["headers"]
    store_id = tenant["store_id"]

    # 1. Upload logo for specific store in storefront
    file_payload = ("branch_logo.png", io.BytesIO(TINY_PNG), "image/png")
    sf_upload = client.post(
        f"/api/v1/ecommerce/storefront/upload-asset?store_id={store_id}",
        data={"asset_type": "logo"},
        files={"file": file_payload},
        headers=headers,
    )
    assert sf_upload.status_code == 200, sf_upload.text
    store_logo_url = sf_upload.json()["url"]

    # 2. Verify store effective branding has the store logo
    eff_res = client.get(f"/api/v1/document-settings/effective?store_id={store_id}", headers=headers)
    assert eff_res.status_code == 200
    assert eff_res.json()["logo_url"] == store_logo_url


def test_document_setting_update_auto_syncs_to_storefront():
    """Updating business name and contact in Document Settings auto-syncs to Storefront."""
    tenant = create_branding_tenant("bname-sync")
    headers = tenant["headers"]

    # First initialize storefront settings
    init_sf = client.get("/api/v1/ecommerce/storefront/settings", headers=headers)
    assert init_sf.status_code == 200

    # Update document setting
    doc_upd = client.put(
        "/api/v1/document-settings",
        json={
            "business_name": "Omnichannel Retail Hub",
            "address": "42 High Street, Mumbai",
            "phone": "9876543210",
            "email": "contact@omnichannel.in",
        },
        headers=headers,
    )
    assert doc_upd.status_code == 200

    # Storefront settings should reflect the new company branding
    sf_res = client.get("/api/v1/ecommerce/storefront/settings", headers=headers)
    assert sf_res.status_code == 200
    sf = sf_res.json()
    assert sf["store_name"] == "Omnichannel Retail Hub"
    assert sf["address"] == "42 High Street, Mumbai"
    assert sf["contact_phone"] == "9876543210"
    assert sf["contact_email"] == "contact@omnichannel.in"


def test_storefront_update_auto_syncs_to_document_branding():
    """Updating company details in Storefront auto-syncs to Document Effective Branding."""
    tenant = create_branding_tenant("sf-bname-sync")
    headers = tenant["headers"]

    # Update storefront settings
    sf_upd = client.put(
        "/api/v1/ecommerce/storefront/settings",
        json={
            "store_name": "Global Supermart",
            "address": "Terminal 2, Pune",
            "contact_phone": "9123456780",
            "contact_email": "hello@globalsuper.com",
        },
        headers=headers,
    )
    assert sf_upd.status_code == 200

    # Effective branding for Invoices/Bills/POs should now reflect this info
    eff_res = client.get("/api/v1/document-settings/effective", headers=headers)
    assert eff_res.status_code == 200
    eff = eff_res.json()
    assert eff["business_name"] == "Global Supermart"
    assert eff["address"] == "Terminal 2, Pune"
    assert eff["phone"] == "9123456780"
    assert eff["email"] == "hello@globalsuper.com"


def test_document_logo_delete_auto_cleans_storefront():
    """Deleting logo via Document Settings also clears logo in Storefront."""
    tenant = create_branding_tenant("del-logo-sync")
    headers = tenant["headers"]

    # 1. Upload logo
    file_payload = ("logo.png", io.BytesIO(TINY_PNG), "image/png")
    upload_res = client.post(
        "/api/v1/document-settings/logo",
        files={"file": file_payload},
        headers=headers,
    )
    assert upload_res.status_code == 200
    logo_url = upload_res.json()["logo_url"]

    # Verify storefront has it
    sf1 = client.get("/api/v1/ecommerce/storefront/settings", headers=headers).json()
    assert sf1["logo_url"] == logo_url

    # 2. Delete logo in Document Settings
    del_res = client.delete("/api/v1/document-settings/logo", headers=headers)
    assert del_res.status_code == 200

    # Verify storefront logo is now None
    sf2 = client.get("/api/v1/ecommerce/storefront/settings", headers=headers).json()
    assert sf2["logo_url"] is None


def test_universal_branding_fallback_in_service():
    """DocumentSettingsService.resolve_branding gracefully falls back across levels."""
    tenant = create_branding_tenant("fallback-srv")
    tenant_id = tenant["tenant_id"]
    store_id = tenant["store_id"]

    db = SessionLocal()
    svc = DocumentSettingsService(db)

    # Initially defaults
    branding = svc.resolve_branding(tenant_id, store_id)
    assert branding.business_name != ""
    assert branding.invoice_prefix == "INV"
    assert branding.bill_prefix == "BILL"
    db.close()


def test_cross_tenant_isolation_in_universal_branding():
    """Tenants cannot see or affect each other's synced branding."""
    t_a = create_branding_tenant("tenant-a")
    t_b = create_branding_tenant("tenant-b")

    # Tenant A sets branding
    client.put(
        "/api/v1/document-settings",
        json={"business_name": "Tenant A Secret Brand"},
        headers=t_a["headers"],
    )

    # Tenant B should see their own default, not Tenant A's branding
    b_eff = client.get("/api/v1/document-settings/effective", headers=t_b["headers"]).json()
    assert b_eff["business_name"] != "Tenant A Secret Brand"

    b_sf = client.get("/api/v1/ecommerce/storefront/settings", headers=t_b["headers"]).json()
    assert b_sf["store_name"] != "Tenant A Secret Brand"

