import io
import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.main import app
from app.models.role import Role
from app.models.store import Store
from app.models.user import User

client = TestClient(app)


def create_storefront_tenant(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"owner-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Storefront Owner",
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

    store1 = Store(
        tenant_id=tenant_id,
        name=f"Main-Outlet-{uuid.uuid4().hex[:4]}",
        address="100 Main St",
        is_active=True,
        is_main=True,
    )
    store2 = Store(
        tenant_id=tenant_id,
        name=f"Branch-Outlet-{uuid.uuid4().hex[:4]}",
        address="200 West St",
        is_active=True,
        is_main=False,
    )
    db.add_all([store1, store2])
    db.commit()
    db.refresh(store1)
    db.refresh(store2)

    store1_id = store1.id
    store2_id = store2.id
    db.close()

    return {
        "headers": headers,
        "tenant_id": tenant_id,
        "store1_id": store1_id,
        "store2_id": store2_id,
        "slug": slug,
    }


def test_get_storefront_settings_default():
    data = create_storefront_tenant("sf-def")
    headers = data["headers"]

    resp = client.get("/api/v1/ecommerce/storefront/settings", headers=headers)
    assert resp.status_code == 200, resp.text
    res = resp.json()

    assert res["is_online"] is True
    assert res["primary_color"] == "#4f46e5"
    assert res["accent_color"] == "#10b981"
    assert res["theme_name"] == "modern_light"
    assert "tagline" in res
    assert "store_name" in res


def test_update_storefront_branding():
    data = create_storefront_tenant("sf-brand")
    headers = data["headers"]

    update_payload = {
        "store_name": "RetailOS Brand Flagship",
        "tagline": "The best products in town — now online!",
        "primary_color": "#2563eb",
        "accent_color": "#059669",
        "theme_name": "dark_bold",
    }
    resp = client.put("/api/v1/ecommerce/storefront/settings", json=update_payload, headers=headers)
    assert resp.status_code == 200, resp.text
    res = resp.json()

    assert res["store_name"] == "RetailOS Brand Flagship"
    assert res["tagline"] == "The best products in town — now online!"
    assert res["primary_color"] == "#2563eb"
    assert res["accent_color"] == "#059669"
    assert res["theme_name"] == "dark_bold"

    # Verify persistent via GET
    get_resp = client.get("/api/v1/ecommerce/storefront/settings", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["store_name"] == "RetailOS Brand Flagship"


def test_toggle_store_online_status():
    data = create_storefront_tenant("sf-toggle")
    headers = data["headers"]

    # Toggle store to offline
    resp1 = client.patch(
        "/api/v1/ecommerce/storefront/toggle-status",
        json={"is_online": False},
        headers=headers,
    )
    assert resp1.status_code == 200, resp1.text
    assert resp1.json()["is_online"] is False

    # Toggle store back to online
    resp2 = client.patch(
        "/api/v1/ecommerce/storefront/toggle-status",
        json={"is_online": True},
        headers=headers,
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["is_online"] is True


def test_upload_media_asset_logo():
    data = create_storefront_tenant("sf-upload")
    headers = data["headers"]

    # Create dummy PNG image bytes
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    file_tuple = ("logo.png", io.BytesIO(fake_png), "image/png")

    resp = client.post(
        "/api/v1/ecommerce/storefront/upload-asset",
        data={"asset_type": "logo"},
        files={"file": file_tuple},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["asset_type"] == "logo"
    assert "/uploads/storefront/logo_" in res["url"]

    # Verify that GET returns the updated logo_url
    get_resp = client.get("/api/v1/ecommerce/storefront/settings", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["logo_url"] == res["url"]


def test_upload_banner_and_favicon():
    data = create_storefront_tenant("sf-assets")
    headers = data["headers"]

    fake_bytes = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    
    # Upload banner
    resp_b = client.post(
        "/api/v1/ecommerce/storefront/upload-asset",
        data={"asset_type": "banner"},
        files={"file": ("hero_banner.jpg", io.BytesIO(fake_bytes), "image/jpeg")},
        headers=headers,
    )
    assert resp_b.status_code == 200, resp_b.text
    assert resp_b.json()["asset_type"] == "banner"

    # Upload favicon
    resp_f = client.post(
        "/api/v1/ecommerce/storefront/upload-asset",
        data={"asset_type": "favicon"},
        files={"file": ("favicon.ico", io.BytesIO(fake_bytes), "image/x-icon")},
        headers=headers,
    )
    assert resp_f.status_code == 200, resp_f.text
    assert resp_f.json()["asset_type"] == "favicon"

    # Verify settings have both
    get_resp = client.get("/api/v1/ecommerce/storefront/settings", headers=headers)
    assert get_resp.status_code == 200
    res = get_resp.json()
    assert res["banner_url"] is not None
    assert res["favicon_url"] is not None


def test_upload_asset_validation():
    data = create_storefront_tenant("sf-val")
    headers = data["headers"]

    # 1. Invalid asset type
    resp1 = client.post(
        "/api/v1/ecommerce/storefront/upload-asset",
        data={"asset_type": "invalid_type"},
        files={"file": ("test.png", io.BytesIO(b"data"), "image/png")},
        headers=headers,
    )
    assert resp1.status_code == 400

    # 2. Unsupported extension
    resp2 = client.post(
        "/api/v1/ecommerce/storefront/upload-asset",
        data={"asset_type": "logo"},
        files={"file": ("dangerous.exe", io.BytesIO(b"data"), "application/octet-stream")},
        headers=headers,
    )
    assert resp2.status_code == 400
    assert "Unsupported file format" in resp2.text


def test_update_seo_pages_contact_advanced():
    data = create_storefront_tenant("sf-full-tabs")
    headers = data["headers"]

    full_payload = {
        # SEO
        "custom_domain": "shop.myretailos.com",
        "subdomain": data["slug"],
        "meta_title": "Best Online Grocery Store",
        "meta_description": "Shop groceries online with 100% freshness guarantee",
        # Pages
        "about_us": "We are your friendly neighborhood retail shop.",
        "privacy_policy": "Your personal data is protected.",
        "terms_conditions": "All sales follow standard store terms.",
        # Contact & Social
        "contact_email": "support@myretailos.com",
        "contact_phone": "+91 9876543210",
        "whatsapp_number": "+91 9876543210",
        "instagram_url": "https://instagram.com/myretailos",
        # Advanced
        "google_analytics_id": "G-ABC123XYZ",
        "is_maintenance_mode": False,
    }

    resp = client.put("/api/v1/ecommerce/storefront/settings", json=full_payload, headers=headers)
    assert resp.status_code == 200, resp.text
    res = resp.json()

    assert res["custom_domain"] == "shop.myretailos.com"
    assert res["subdomain"] == data["slug"]
    assert res["meta_title"] == "Best Online Grocery Store"
    assert res["about_us"] == "We are your friendly neighborhood retail shop."
    assert res["contact_email"] == "support@myretailos.com"
    assert res["instagram_url"] == "https://instagram.com/myretailos"
    assert res["google_analytics_id"] == "G-ABC123XYZ"


def test_storefront_store_id_isolation():
    data = create_storefront_tenant("sf-iso")
    headers = data["headers"]
    s1 = data["store1_id"]
    s2 = data["store2_id"]

    # Configure store 1 branding
    resp1 = client.put(
        f"/api/v1/ecommerce/storefront/settings?store_id={s1}",
        json={"store_name": "Store 1 Exclusive Outlet", "primary_color": "#ff0000"},
        headers=headers,
    )
    assert resp1.status_code == 200
    assert resp1.json()["store_name"] == "Store 1 Exclusive Outlet"

    # Configure store 2 branding
    resp2 = client.put(
        f"/api/v1/ecommerce/storefront/settings?store_id={s2}",
        json={"store_name": "Store 2 Mega Branch", "primary_color": "#00ff00"},
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["store_name"] == "Store 2 Mega Branch"

    # Verify they don't overwrite each other
    check1 = client.get(f"/api/v1/ecommerce/storefront/settings?store_id={s1}", headers=headers).json()
    check2 = client.get(f"/api/v1/ecommerce/storefront/settings?store_id={s2}", headers=headers).json()
    assert check1["store_name"] == "Store 1 Exclusive Outlet"
    assert check1["primary_color"] == "#ff0000"
    assert check2["store_name"] == "Store 2 Mega Branch"
    assert check2["primary_color"] == "#00ff00"


def test_public_storefront_endpoint():
    data = create_storefront_tenant("sf-pub")
    headers = data["headers"]
    slug = data["slug"]

    # Set subdomain
    client.put(
        "/api/v1/ecommerce/storefront/settings",
        json={"subdomain": slug, "store_name": "Public Facing Shop"},
        headers=headers,
    )

    # Fetch publicly without Authorization header
    pub_resp = client.get(f"/api/v1/ecommerce/storefront/public?subdomain={slug}")
    assert pub_resp.status_code == 200, pub_resp.text
    res = pub_resp.json()
    assert res["store_name"] == "Public Facing Shop"
    assert res["is_online"] is True



def test_tab_seo_domain_endpoints():
    data = create_storefront_tenant("tab-seo")
    headers = data["headers"]

    # 1. GET initial SEO & Domain settings
    get_resp = client.get("/api/v1/ecommerce/storefront/seo-domain", headers=headers)
    assert get_resp.status_code == 200, get_resp.text
    seo_data = get_resp.json()
    assert "default_store_url" in seo_data
    assert "mystore.in" in seo_data["default_store_url"]

    # 2. PUT updated SEO & Domain settings
    update_payload = {
        "custom_domain": "shop.brandhub.in",
        "url_slug": "brand-hub",
        "meta_title": "Brand Hub | Best Online Store",
        "meta_description": "Exclusive deals on groceries and electronics",
        "keywords": "brand, groceries, deals",
        "google_analytics_id": "G-TEST9999",
    }
    put_resp = client.put("/api/v1/ecommerce/storefront/seo-domain", json=update_payload, headers=headers)
    assert put_resp.status_code == 200, put_resp.text
    updated = put_resp.json()
    assert updated["custom_domain"] == "shop.brandhub.in"
    assert updated["url_slug"] == "brand-hub"
    assert updated["meta_title"] == "Brand Hub | Best Online Store"
    assert updated["google_analytics_id"] == "G-TEST9999"


def test_tab_store_pages_endpoints():
    data = create_storefront_tenant("tab-pages")
    headers = data["headers"]

    # 1. GET default store pages
    get_resp = client.get("/api/v1/ecommerce/storefront/pages", headers=headers)
    assert get_resp.status_code == 200, get_resp.text
    pages = get_resp.json()
    assert "trusted retail store" in pages["about_us"]
    assert "privacy" in pages["privacy_policy"].lower()
    assert "return" in pages["return_policy"].lower()

    # 2. PUT updated store pages
    new_pages = {
        "about_us": "Custom About Us story here.",
        "contact_us": "Visit our outlet or email us anytime.",
        "privacy_policy": "Zero data selling policy.",
        "terms_conditions": "100% genuine products warranty.",
        "return_policy": "7-day hassle free replacement.",
    }
    put_resp = client.put("/api/v1/ecommerce/storefront/pages", json=new_pages, headers=headers)
    assert put_resp.status_code == 200, put_resp.text
    updated = put_resp.json()
    assert updated["about_us"] == "Custom About Us story here."
    assert updated["contact_us"] == "Visit our outlet or email us anytime."
    assert updated["return_policy"] == "7-day hassle free replacement."


def test_tab_contact_social_endpoints():
    data = create_storefront_tenant("tab-social")
    headers = data["headers"]

    # 1. GET Contact & Social settings
    get_resp = client.get("/api/v1/ecommerce/storefront/contact-social", headers=headers)
    assert get_resp.status_code == 200, get_resp.text
    cs = get_resp.json()
    assert "@retailos_shop" in cs["instagram_url"]

    # 2. PUT updated Contact & Social settings
    new_cs = {
        "contact_email": "hello@mycustomshop.com",
        "contact_phone": "+91 9988776655",
        "whatsapp_number": "+91 9988776655",
        "address": "456 Commercial Street, Pune",
        "instagram_url": "@custom_shop_official",
        "facebook_url": "facebook.com/customshop",
        "twitter_url": "@customshop_in",
    }
    put_resp = client.put("/api/v1/ecommerce/storefront/contact-social", json=new_cs, headers=headers)
    assert put_resp.status_code == 200, put_resp.text
    updated = put_resp.json()
    assert updated["contact_email"] == "hello@mycustomshop.com"
    assert updated["instagram_url"] == "@custom_shop_official"
    assert updated["twitter_url"] == "@customshop_in"


def test_tab_advanced_settings_endpoints():
    data = create_storefront_tenant("tab-adv")
    headers = data["headers"]

    # 1. GET Advanced feature switches
    get_resp = client.get("/api/v1/ecommerce/storefront/advanced", headers=headers)
    assert get_resp.status_code == 200, get_resp.text
    adv = get_resp.json()
    assert adv["enable_product_reviews"] is True
    assert adv["show_out_of_stock"] is True
    assert adv["guest_checkout"] is False
    assert adv["auto_sync_inventory"] is True
    assert adv["enable_coupons"] is True
    assert adv["gst_invoice_enabled"] is True

    # 2. PUT toggle switches (Enable Guest Checkout, Disable Out of Stock display)
    toggle_payload = {
        "guest_checkout": True,
        "show_out_of_stock": False,
        "enable_coupons": True,
    }
    put_resp = client.put("/api/v1/ecommerce/storefront/advanced", json=toggle_payload, headers=headers)
    assert put_resp.status_code == 200, put_resp.text
    updated = put_resp.json()
    assert updated["guest_checkout"] is True
    assert updated["show_out_of_stock"] is False
    assert updated["enable_product_reviews"] is True
