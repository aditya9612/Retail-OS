import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.document_setting import DocumentSetting
from app.services.document_number_service import DocumentNumberService

client = TestClient(app)


@pytest.fixture
def doc_settings_setup(unique_slug):
    email = f"docset-enh-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Docset Enhanced Corp",
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
        json={"name": "Docset Flagship Store", "code": f"E{unique_slug[:3]}"},
        headers=headers,
    ).json()

    return {
        "headers": headers,
        "store_id": store["id"],
        "slug": unique_slug,
    }


def test_custom_styling_and_terms(doc_settings_setup):
    headers = doc_settings_setup["headers"]

    payload = {
        "business_name": "Modern Retailers",
        "primary_color": "#2563EB",
        "secondary_color": "#10B981",
        "terms_and_conditions": "1. Goods once sold are not returnable without bill.\n2. Warranty as per manufacturer terms.",
        "padding_length": 8,
        "invoice_prefix": "MRET-INV",
    }
    res = client.put("/api/v1/document-settings", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["primary_color"] == "#2563EB"
    assert data["secondary_color"] == "#10B981"
    assert "Goods once sold" in data["terms_and_conditions"]
    assert data["padding_length"] == 8

    # Verify effective branding reflects styling
    eff = client.get("/api/v1/document-settings/effective", headers=headers)
    assert eff.status_code == 200
    eff_data = eff.json()
    assert eff_data["primary_color"] == "#2563EB"
    assert eff_data["secondary_color"] == "#10B981"
    assert eff_data["padding_length"] == 8
    assert "Goods once sold" in eff_data["terms_and_conditions"]


def test_hex_color_and_padding_validation(doc_settings_setup):
    headers = doc_settings_setup["headers"]

    # Invalid hex color
    res = client.put(
        "/api/v1/document-settings",
        json={"primary_color": "not-a-color"},
        headers=headers,
    )
    assert res.status_code == 422

    # Invalid padding length (too large > 12)
    res_pad = client.put(
        "/api/v1/document-settings",
        json={"padding_length": 15},
        headers=headers,
    )
    assert res_pad.status_code == 422


def test_delete_store_document_setting_reverts_to_tenant(doc_settings_setup):
    headers = doc_settings_setup["headers"]
    store_id = doc_settings_setup["store_id"]

    # 1. Setup tenant branding
    client.put(
        "/api/v1/document-settings",
        json={"business_name": "Tenant Master Brand", "primary_color": "#111827"},
        headers=headers,
    )

    # 2. Setup store-specific branding override
    client.put(
        f"/api/v1/document-settings?store_id={store_id}",
        json={"business_name": "Store Branch Custom", "primary_color": "#DC2626"},
        headers=headers,
    )

    store_eff = client.get(f"/api/v1/document-settings/effective?store_id={store_id}", headers=headers).json()
    assert store_eff["business_name"] == "Store Branch Custom"
    assert store_eff["primary_color"] == "#DC2626"

    # 3. Delete / revert store document setting
    del_res = client.delete(f"/api/v1/document-settings?store_id={store_id}", headers=headers)
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert "reverted to defaults" in del_data["message"].lower()

    # 4. Now effective branding for store falls back to tenant defaults
    store_reverted = client.get(f"/api/v1/document-settings/effective?store_id={store_id}", headers=headers).json()
    assert store_reverted["business_name"] == "Tenant Master Brand"
    assert store_reverted["primary_color"] == "#111827"


def test_preview_document_pdf_invoice(doc_settings_setup):
    headers = doc_settings_setup["headers"]

    # Set custom styling and terms
    client.put(
        "/api/v1/document-settings",
        json={
            "business_name": "Preview Mart",
            "invoice_prefix": "PRV-INV",
            "primary_color": "#1E40AF",
            "terms_and_conditions": "Preview terms test line.",
        },
        headers=headers,
    )

    # Call preview endpoint for invoice
    res = client.get(
        "/api/v1/document-settings/preview?document_type=invoice",
        headers=headers,
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert len(res.content) > 100
    assert res.content.startswith(b"%PDF")


def test_preview_document_pdf_bill(doc_settings_setup):
    headers = doc_settings_setup["headers"]

    # Call preview endpoint for bill
    res = client.get(
        "/api/v1/document-settings/preview?document_type=bill",
        headers=headers,
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert len(res.content) > 100
    assert res.content.startswith(b"%PDF")


def test_dynamic_padding_length_in_document_number_service(unique_slug):
    from app.models.tenant import Tenant
    from app.models.store import Store

    db = SessionLocal()
    try:
        # Create tenant and store
        tenant = Tenant(name="Padding Tenant", slug=f"pad-{unique_slug}")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        store = Store(name="Padding Store", code=f"P{unique_slug[:3]}", tenant_id=tenant.id)
        db.add(store)
        db.commit()
        db.refresh(store)

        # Configure custom 8-digit padding length
        doc_setting = DocumentSetting(
            tenant_id=tenant.id,
            store_id=None,
            invoice_prefix="PAD-INV",
            padding_length=8,
        )
        db.add(doc_setting)
        db.commit()

        service = DocumentNumberService(db)
        seq_num = service.generate_invoice_number(
            tenant_id=tenant.id,
            store_id=store.id,
        )
        # Form: PAD-INV-2026-00000001 (8-digit padding)
        parts = seq_num.split("-")
        assert parts[0] == "PAD"
        assert parts[1] == "INV"
        # Last part should be 8 digits long
        seq_str = parts[-1]
        assert len(seq_str) == 8
        assert seq_str == "00000001"
    finally:
        db.close()
