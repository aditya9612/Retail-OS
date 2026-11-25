import unittest.mock
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_full_real_admin_lifecycle_and_multistore_audit():
    """
    Comprehensive End-to-End Audit testing the real Admin journey across:
    1. Tenant & Admin onboarding
    2. Multi-store branch creation
    3. Master product catalog creation
    4. Multi-store inventory allocation (Stock-In)
    5. In-store POS sale & Strict Store Stock Isolation
    6. Over-selling protection validation
    7. Store-to-Store stock transfer workflow (dispatch & receive)
    8. Document branding & live PDF preview
    9. Online storefront customer shopping & automatic stock deduction
    10. Multi-store analytics & store performance comparison
    """
    slug = f"audit-{uuid.uuid4().hex[:6]}"
    admin_email = f"admin@{slug}.com"
    password = "AdminSecurePass123!"

    print(f"\n[PHASE 1] Registering Admin & Tenant: {slug}")
    reg_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "RetailOS Supermart Group",
            "slug": slug,
            "email": admin_email,
            "admin_name": "Gaurav Admin",
            "password": password,
        },
    )
    assert reg_resp.status_code in (200, 201), f"Admin registration failed: {reg_resp.text}"

    # Login Admin
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": admin_email, "password": password},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {token}"}

    # --------------------------------------------------------------------------
    # PHASE 2: Multiple Store Outlets Creation
    # --------------------------------------------------------------------------
    print("\n[PHASE 2] Creating Multiple Store Outlets (Store 1: Pune, Store 2: Mumbai)")
    # Store 1 (Main Store)
    s1_resp = client.post(
        "/api/v1/stores/",
        json={
            "name": "Supermart Pune FC Road",
            "code": f"PUN-{slug[:4].upper()}",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411004",
            "address": "123 FC Road, Deccan, Pune",
            "phone": "9876543210",
            "email": f"pune@{slug}.com",
            "is_main": True,
        },
        headers=admin_headers,
    )
    assert s1_resp.status_code in (200, 201), f"Store 1 creation failed: {s1_resp.text}"
    store1 = s1_resp.json()
    store1_id = store1["id"]

    # Store 2 (Branch Store)
    s2_resp = client.post(
        "/api/v1/stores/",
        json={
            "name": "Supermart Mumbai Bandra",
            "code": f"MUM-{slug[:4].upper()}",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400050",
            "address": "456 Hill Road, Bandra West, Mumbai",
            "phone": "9876543211",
            "email": f"mumbai@{slug}.com",
            "is_main": False,
        },
        headers=admin_headers,
    )
    assert s2_resp.status_code in (200, 201), f"Store 2 creation failed: {s2_resp.text}"
    store2 = s2_resp.json()
    store2_id = store2["id"]

    # Verify both stores appear in store list
    stores_list = client.get("/api/v1/stores/", headers=admin_headers)
    assert stores_list.status_code == 200
    store_ids = [s["id"] for s in stores_list.json()]
    assert store1_id in store_ids
    assert store2_id in store_ids

    # --------------------------------------------------------------------------
    # PHASE 3: Category & Master Product Catalog Creation
    # --------------------------------------------------------------------------
    print("\n[PHASE 3] Creating Category and Master Product")
    cat_resp = client.post(
        "/api/v1/categories",
        json={
            "name": f"Staples-{slug[:4]}",
            "description": "Daily food staples and pulses",
        },
        headers=admin_headers,
    )
    assert cat_resp.status_code in (200, 201), f"Category creation failed: {cat_resp.text}"
    cat_id = cat_resp.json()["id"]

    # Create Master Product 1 (Daawat Basmati Rice 5kg)
    prod_sku = f"RICE-{slug[:4].upper()}"
    prod_resp = client.post(
        "/api/v1/products",
        json={
            "name": "Daawat Rozana Basmati Rice 5kg",
            "sku": prod_sku,
            "category_id": cat_id,
            "selling_price": 380.00,
            "cost_price": 310.00,
            "mrp": 420.00,
            "tax_rate": 5.00,
            "hsn_code": "1006",
            "unit": "bag",
            "min_stock_alert": 5,
        },
        headers=admin_headers,
    )
    assert prod_resp.status_code in (200, 201), f"Product creation failed: {prod_resp.text}"
    product = prod_resp.json()
    product_id = product["id"]

    # --------------------------------------------------------------------------
    # PHASE 4: Multi-Store Stock Allocation (Stock-In)
    # --------------------------------------------------------------------------
    print("\n[PHASE 4] Allocating Stock: Store 1 gets 50 units, Store 2 gets 30 units")
    # Stock-In Store 1: 50 units
    stk1_resp = client.post(
        "/api/v1/inventory/stock-in",
        json={
            "store_id": store1_id,
            "product_id": product_id,
            "quantity": 50,
            "unit_cost": 310.00,
            "notes": "Initial inventory batch for Pune Store",
        },
        headers=admin_headers,
    )
    assert stk1_resp.status_code in (200, 201), f"Store 1 stock-in failed: {stk1_resp.text}"

    # Stock-In Store 2: 30 units
    stk2_resp = client.post(
        "/api/v1/inventory/stock-in",
        json={
            "store_id": store2_id,
            "product_id": product_id,
            "quantity": 30,
            "unit_cost": 310.00,
            "notes": "Initial inventory batch for Mumbai Store",
        },
        headers=admin_headers,
    )
    assert stk2_resp.status_code in (200, 201), f"Store 2 stock-in failed: {stk2_resp.text}"

    # Verify inventory per store
    inv1_resp = client.get(f"/api/v1/inventory?store_id={store1_id}&product_id={product_id}", headers=admin_headers)
    assert inv1_resp.status_code == 200
    inv1_data = inv1_resp.json()
    assert len(inv1_data) == 1
    assert float(inv1_data[0]["quantity"]) == 50.0

    inv2_resp = client.get(f"/api/v1/inventory?store_id={store2_id}&product_id={product_id}", headers=admin_headers)
    assert inv2_resp.status_code == 200
    inv2_data = inv2_resp.json()
    assert len(inv2_data) == 1
    assert float(inv2_data[0]["quantity"]) == 30.0

    # --------------------------------------------------------------------------
    # PHASE 5: POS Sale in Store 1 & Strict Multi-Store Stock Isolation Check
    # --------------------------------------------------------------------------
    print("\n[PHASE 5] POS Sale of 10 units in Store 1 -> Verify Store 1=40, Store 2=30")
    sale_resp = client.post(
        "/api/v1/sales",
        json={
            "store_id": store1_id,
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 10,
                    "unit_price": 380.00,
                    "discount": 0.00,
                }
            ],
            "payment_method": "cash",
            "notes": "Store 1 Walk-in Customer Sale",
        },
        headers=admin_headers,
    )
    assert sale_resp.status_code in (200, 201), f"Sale creation failed: {sale_resp.text}"
    sale_data = sale_resp.json()
    assert "sale_number" in sale_data
    assert float(sale_data["total_amount"]) > 0

    # Check Store 1 inventory: MUST BE EXACTLY 40 (50 - 10)
    inv1_after = client.get(f"/api/v1/inventory?store_id={store1_id}&product_id={product_id}", headers=admin_headers).json()
    assert float(inv1_after[0]["quantity"]) == 40.0, f"Expected 40.0 in Store 1, got {inv1_after[0]['quantity']}"

    # Check Store 2 inventory: MUST BE EXACTLY 30 (UNTOUCHED!)
    inv2_after = client.get(f"/api/v1/inventory?store_id={store2_id}&product_id={product_id}", headers=admin_headers).json()
    assert float(inv2_after[0]["quantity"]) == 30.0, f"Store 2 stock was corrupted! Expected 30.0, got {inv2_after[0]['quantity']}"

    # --------------------------------------------------------------------------
    # PHASE 6: Over-Selling Protection Validation
    # --------------------------------------------------------------------------
    print("\n[PHASE 6] Testing Over-selling Protection in Store 1 (Trying to sell 45 when 40 available)")
    oversell_resp = client.post(
        "/api/v1/sales",
        json={
            "store_id": store1_id,
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 45,
                    "unit_price": 380.00,
                }
            ],
            "payment_method": "cash",
        },
        headers=admin_headers,
    )
    assert oversell_resp.status_code in (400, 422), f"Oversell should fail but got: {oversell_resp.status_code}"
    # Verify stock stayed at 40
    inv1_safe = client.get(f"/api/v1/inventory?store_id={store1_id}&product_id={product_id}", headers=admin_headers).json()
    assert float(inv1_safe[0]["quantity"]) == 40.0

    # --------------------------------------------------------------------------
    # PHASE 7: Store-to-Store Stock Transfer Workflow
    # --------------------------------------------------------------------------
    print("\n[PHASE 7] Transferring 5 units from Store 1 to Store 2")
    transfer_resp = client.post(
        "/api/v1/store-transfers",
        json={
            "source_store_id": store1_id,
            "destination_store_id": store2_id,
            "notes": "Inter-branch balance transfer",
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 5,
                    "notes": "Transfer 5 bags of rice",
                }
            ],
        },
        headers=admin_headers,
    )
    assert transfer_resp.status_code in (200, 201), f"Transfer creation failed: {transfer_resp.text}"
    transfer_id = transfer_resp.json()["id"]

    # Approve transfer -> moves to Approved
    appr_resp = client.put(f"/api/v1/store-transfers/{transfer_id}/approve", headers=admin_headers)
    assert appr_resp.status_code == 200, f"Approve failed: {appr_resp.text}"

    # Dispatch transfer -> deducts from source store (40 - 5 = 35)
    disp_resp = client.put(f"/api/v1/store-transfers/{transfer_id}/dispatch", headers=admin_headers)
    assert disp_resp.status_code == 200, f"Dispatch failed: {disp_resp.text}"

    # Check Store 1 after dispatch: 35
    inv1_disp = client.get(f"/api/v1/inventory?store_id={store1_id}&product_id={product_id}", headers=admin_headers).json()
    assert float(inv1_disp[0]["quantity"]) == 35.0

    # Receive transfer -> adds to destination store (30 + 5 = 35)
    rec_resp = client.put(f"/api/v1/store-transfers/{transfer_id}/receive", headers=admin_headers)
    assert rec_resp.status_code == 200, f"Receive failed: {rec_resp.text}"

    # Check Store 2 after receive: 35
    inv2_rec = client.get(f"/api/v1/inventory?store_id={store2_id}&product_id={product_id}", headers=admin_headers).json()
    assert float(inv2_rec[0]["quantity"]) == 35.0

    # --------------------------------------------------------------------------
    # PHASE 8: Document Settings, Branding & Live PDF Invoice Preview
    # --------------------------------------------------------------------------
    print("\n[PHASE 8] Updating Document Settings and Previewing Live Invoice PDF")
    doc_put = client.put(
        "/api/v1/document-settings",
        json={
            "business_name": "RetailOS Supermart HQ",
            "address": "Corporate Park, Pune 411001",
            "phone": "9876543210",
            "email": "info@supermart.com",
            "gstin": "27AAACP0123M1Z5",
            "invoice_prefix": "SUP-INV",
            "show_gstin": True,
            "show_qr": True,
        },
        headers=admin_headers,
    )
    assert doc_put.status_code == 200

    # Effective branding
    eff_doc = client.get("/api/v1/document-settings/effective", headers=admin_headers)
    assert eff_doc.status_code == 200
    assert eff_doc.json()["business_name"] == "RetailOS Supermart HQ"

    # Preview Tax Invoice PDF
    prev_resp = client.get("/api/v1/document-settings/preview?document_type=invoice&mode=download", headers=admin_headers)
    assert prev_resp.status_code == 200
    assert prev_resp.headers["content-type"] == "application/pdf"
    assert len(prev_resp.content) > 1000

    # --------------------------------------------------------------------------
    # PHASE 9: Online Storefront Customer Browsing, Cart & Checkout
    # --------------------------------------------------------------------------
    print("\n[PHASE 9] Customer Storefront: Mobile OTP Login, Cart, Checkout, Stock Deduction")
    cust_phone = "9811223344"
    # 0. Onboard Customer in system
    unique_cust_phone = f"98{uuid.uuid4().int % 100000000:08d}"
    cust_create = client.post(
        "/api/v1/customers",
        json={
            "name": "Amit Kumar",
            "phone": unique_cust_phone,
            "email": f"amit-{slug[:4]}@example.com",
            "address": "Flat 301, Lake View, Pune",
        },
        headers=admin_headers,
    )
    assert cust_create.status_code in (200, 201), f"Customer creation failed: {cust_create.text}"
    created_cust_data = cust_create.json()
    print("\nCREATED CUSTOMER:", created_cust_data)

    # Unified Customer Mobile OTP login
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.auth_service.secrets.randbelow", lambda _: 889900)
        req_resp = client.post("/api/v1/auth/login/mobile-otp/request", json={"phone": unique_cust_phone})
        print("OTP REQUEST:", req_resp.status_code, req_resp.text)
        cust_login = client.post("/api/v1/auth/login/mobile-otp/verify", json={"phone": unique_cust_phone, "otp": "889900"})
        print("OTP VERIFY:", cust_login.status_code, cust_login.text)
        assert cust_login.status_code == 200, f"Customer OTP login failed: {cust_login.text}"
        cust_token = cust_login.json()["access_token"]
        cust_headers = {"Authorization": f"Bearer {cust_token}"}

    # 1. Customer browses products with store_id=store1_id
    cat_items = client.get(f"/api/v1/storefront/products?store_id={store1_id}", headers=cust_headers)
    print("BROWSE PRODUCTS:", cat_items.status_code, cat_items.text)
    assert cat_items.status_code == 200, f"Storefront products browse failed: {cat_items.status_code} - {cat_items.text}"
    prods = cat_items.json()["items"]
    assert any(p["id"] == product_id for p in prods)
    matched_prod = next(p for p in prods if p["id"] == product_id)
    assert matched_prod["in_stock"] is True
    assert float(matched_prod["stock_quantity"]) == 35.0

    # 2. Customer adds 2 units to cart
    add_cart = client.post(
        "/api/v1/storefront/cart/items",
        json={"product_id": product_id, "quantity": 2},
        headers=cust_headers,
    )
    assert add_cart.status_code == 200
    assert add_cart.json()["total_items"] == 2

    # 3. Customer Checkouts for Store 1
    with unittest.mock.patch("app.tasks.whatsapp_tasks.send_order_confirmation_task.delay"):
        chk_resp = client.post(
            "/api/v1/storefront/checkout",
            json={
                "store_id": store1_id,
                "delivery_type": "delivery",
                "delivery_address": "Flat 301, Lake View, Pune",
                "payment_method": "cod",
                "notes": "Please call before delivery",
            },
            headers=cust_headers,
        )
    assert chk_resp.status_code in (200, 201), f"Storefront checkout failed: {chk_resp.text}"
    order_data = chk_resp.json()
    assert "order_number" in order_data
    order_id = order_data["order_id"]

    # 4. Verify Stock Deduction in Store 1: (35 - 2 = 33)
    inv1_online = client.get(f"/api/v1/inventory?store_id={store1_id}&product_id={product_id}", headers=admin_headers).json()
    assert float(inv1_online[0]["quantity"]) == 33.0, f"Expected 33 in Store 1 after online order, got {inv1_online[0]['quantity']}"

    # Verify Store 2 Stock: STILL 35.0!
    inv2_online = client.get(f"/api/v1/inventory?store_id={store2_id}&product_id={product_id}", headers=admin_headers).json()
    assert float(inv2_online[0]["quantity"]) == 35.0, f"Store 2 stock was corrupted by Store 1 online order!"

    # 5. Customer Cancels Order -> Verifies Stock Restores (33 + 2 = 35)
    can_resp = client.post(
        f"/api/v1/storefront/my-orders/{order_id}/cancel",
        json={"reason": "Placed by mistake"},
        headers=cust_headers,
    )
    assert can_resp.status_code == 200
    inv1_restored = client.get(f"/api/v1/inventory?store_id={store1_id}&product_id={product_id}", headers=admin_headers).json()
    assert float(inv1_restored[0]["quantity"]) == 35.0, f"Stock restoration failed after cancellation!"

    # --------------------------------------------------------------------------
    # PHASE 10: Multi-Store Analytics Comparison
    # --------------------------------------------------------------------------
    print("\n[PHASE 10] Checking Multi-Store Performance Analytics")
    analytics_resp = client.get("/api/v1/multi-store/revenue-comparison", headers=admin_headers)
    assert analytics_resp.status_code == 200, f"Revenue comparison failed: {analytics_resp.text}"

    inv_comparison = client.get("/api/v1/multi-store/inventory-comparison", headers=admin_headers)
    assert inv_comparison.status_code == 200, f"Inventory comparison failed: {inv_comparison.text}"

    print("\n=== AUDIT COMPLETE: ALL 10 PHASES PASSED WITH ZERO DATA LEAKS OR ANOMALIES ===")
