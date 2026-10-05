import random
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.product import Product
from app.models.role import Role
from app.models.store import Store
from app.models.tenant import Tenant
from app.utils.constants import UserRole

client = TestClient(app)


def _gen_phone():
    return f"9{random.randint(100000000, 999999999)}"


def _gen_barcode(length: int = 12):
    return "".join(str(random.randint(0, 9)) for _ in range(length))


@pytest.fixture(scope="module")
def setup_fixture():
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:6]

    try:
        # 1. Register Primary Tenant (Tenant 1)
        owner_email = f"var_owner_{suffix}@retailtest.com"
        owner_pass = "OwnerPass123!"
        reg_res = client.post(
            "/api/v1/auth/register",
            json={
                "store_name": f"Variant Tenant {suffix}",
                "domain": f"variant-{suffix}",
                "owner_email": owner_email,
                "owner_name": f"Owner {suffix}",
                "password": owner_pass,
                "owner_phone": _gen_phone(),
                "plan_code": "enterprise",
            },
        )
        assert reg_res.status_code == 200, reg_res.text
        tenant1_id = reg_res.json()["tenant_id"]

        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": owner_email, "password": owner_pass},
        )
        assert login_res.status_code == 200
        owner_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Store for Tenant 1
        s1 = client.post(
            "/api/v1/stores/",
            headers=owner_headers,
            json={
                "name": f"Store Main {suffix}",
                "code": f"STM_{suffix}",
                "city": "Pune",
                "state": "Maharashtra",
            },
        )
        assert s1.status_code == 201, s1.text
        store1_id = s1.json()["id"]

        # Cashier user under Tenant 1 (no products:write permission)
        cashier_role = (
            db.query(Role)
            .filter(Role.name == UserRole.CASHIER.value, Role.tenant_id == tenant1_id)
            .first()
        )
        cashier_email = f"cashier_{suffix}@retailtest.com"
        c_res = client.post(
            "/api/v1/users/",
            headers=owner_headers,
            json={
                "email": cashier_email,
                "full_name": "Cashier User",
                "phone": _gen_phone(),
                "password": "Password123!",
                "role_id": cashier_role.id,
                "store_id": store1_id,
            },
        )
        assert c_res.status_code == 201, c_res.text
        c_log = client.post(
            "/api/v1/auth/login",
            json={"email": cashier_email, "password": "Password123!"},
        )
        cashier_headers = {"Authorization": f"Bearer {c_log.json()['access_token']}"}

        # 2. Register Secondary Tenant (Tenant 2) for cross-tenant tests
        t2_suffix = uuid.uuid4().hex[:6]
        t2_owner_email = f"t2_owner_{t2_suffix}@retailtest.com"
        t2_reg = client.post(
            "/api/v1/auth/register",
            json={
                "store_name": f"Cross Tenant {t2_suffix}",
                "domain": f"cross-{t2_suffix}",
                "owner_email": t2_owner_email,
                "owner_name": f"T2 Owner {t2_suffix}",
                "password": owner_pass,
                "owner_phone": _gen_phone(),
                "plan_code": "enterprise",
            },
        )
        assert t2_reg.status_code == 200, t2_reg.text
        tenant2_id = t2_reg.json()["tenant_id"]

        t2_log = client.post(
            "/api/v1/auth/login",
            json={"email": t2_owner_email, "password": owner_pass},
        )
        assert t2_log.status_code == 200
        t2_headers = {"Authorization": f"Bearer {t2_log.json()['access_token']}"}

        # 3. Create a base product under Tenant 1
        p_res = client.post(
            "/api/v1/products",
            headers=owner_headers,
            json={
                "name": f"Classic T-Shirt {suffix}",
                "sku": f"TSHIRT-{suffix}".upper(),
                "price": "499.00",
                "gst_rate": "5.00",
                "barcode": _gen_barcode(12),
            },
        )
        assert p_res.status_code == 201, p_res.text
        parent_product = p_res.json()

        # Set parent product cost_price in DB for testing cost fallback
        parent_db_obj = db.query(Product).filter(Product.id == parent_product["id"]).first()
        if parent_db_obj:
            parent_db_obj.cost_price = Decimal("200.00")
            db.commit()

        # 4. Create a base product under Tenant 2
        p2_res = client.post(
            "/api/v1/products",
            headers=t2_headers,
            json={
                "name": f"T2 Product {t2_suffix}",
                "sku": f"T2PROD-{t2_suffix}".upper(),
                "price": "799.00",
                "gst_rate": "12.00",
                "barcode": _gen_barcode(12),
            },
        )
        assert p2_res.status_code == 201, p2_res.text
        t2_product = p2_res.json()

        return {
            "tenant1_id": tenant1_id,
            "tenant2_id": tenant2_id,
            "owner_headers": owner_headers,
            "cashier_headers": cashier_headers,
            "t2_headers": t2_headers,
            "parent_product": parent_product,
            "t2_product": t2_product,
            "suffix": suffix,
        }
    finally:
        db.close()


# ============================================================================
# 1. VARIANT CREATION & PRICE FALLBACK TESTS
# ============================================================================


def test_create_variant_success(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]
    barcode = _gen_barcode(12)

    res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Size L - Navy Blue",
            "sku": f"TSHIRT-L-BLU-{suffix}",
            "barcode": barcode,
            "size": "L",
            "color": "Navy Blue",
            "attributes": {"material": "100% Cotton", "fit": "Regular"},
            "selling_price": "549.00",
            "cost_price": "220.00",
            "is_active": True,
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["id"] > 0
    assert data["product_id"] == prod_id
    assert data["variant_name"] == "Size L - Navy Blue"
    assert data["sku"] == f"TSHIRT-L-BLU-{suffix}".upper()
    assert data["barcode"] == barcode
    assert data["size"] == "L"
    assert data["color"] == "Navy Blue"
    assert data["attributes"] == {"material": "100% Cotton", "fit": "Regular"}
    assert Decimal(str(data["selling_price"])) == Decimal("549.00")
    assert Decimal(str(data["cost_price"])) == Decimal("220.00")
    assert Decimal(str(data["effective_selling_price"])) == Decimal("549.00")
    assert Decimal(str(data["effective_cost_price"])) == Decimal("220.00")
    assert data["is_active"] is True


def test_create_variant_direct_endpoint(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]

    res = client.post(
        "/api/v1/variants",
        headers=h,
        json={
            "product_id": prod_id,
            "variant_name": "Direct POST Variant",
            "sku": f"DIR-POST-{suffix}".upper(),
            "selling_price": "600.00",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["product_id"] == prod_id
    assert data["variant_name"] == "Direct POST Variant"
    assert Decimal(str(data["selling_price"])) == Decimal("600.00")


def test_create_variant_minimal_fields(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]

    res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Size M - Plain White",
            "sku": f"TSHIRT-M-WHT-{suffix}",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["variant_name"] == "Size M - Plain White"
    assert data["sku"] == f"TSHIRT-M-WHT-{suffix}".upper()
    assert data["barcode"] is None
    assert data["size"] is None
    assert data["color"] is None
    assert data["attributes"] is None
    assert data["selling_price"] is None
    assert data["cost_price"] is None
    # Price fallback to parent product
    parent_selling = Decimal(str(setup_fixture["parent_product"]["selling_price"]))
    assert Decimal(str(data["effective_selling_price"])) == parent_selling
    assert Decimal(str(data["effective_cost_price"])) == Decimal("200.00")


def test_variant_effective_price_partial_fallback(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]

    # Only cost_price is overridden, selling_price is None
    res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Size XL - Black",
            "sku": f"TSHIRT-XL-BLK-{suffix}",
            "cost_price": "260.00",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["selling_price"] is None
    assert Decimal(str(data["cost_price"])) == Decimal("260.00")
    assert Decimal(str(data["effective_selling_price"])) == Decimal(
        str(setup_fixture["parent_product"]["selling_price"])
    )
    assert Decimal(str(data["effective_cost_price"])) == Decimal("260.00")


def test_create_variant_sku_uppercase_normalization(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]

    res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Size S - Red",
            "sku": f"  tshirt-s-red-{suffix}  ",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["sku"] == f"TSHIRT-S-RED-{suffix}".upper()


# ============================================================================
# 2. VALIDATION & ERROR HANDLING
# ============================================================================


def test_create_variant_validation_empty_name(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]

    res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "   ",
            "sku": "VAR-ERR-NAME",
        },
    )
    assert res.status_code == 422


def test_create_variant_validation_empty_sku(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]

    res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Sample Variant",
            "sku": "   ",
        },
    )
    assert res.status_code == 422


def test_create_variant_validation_invalid_barcode_format(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]

    # Non-digit barcode
    res1 = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Sample Variant",
            "sku": "VAR-ERR-BAR1",
            "barcode": "BARCODE123",
        },
    )
    assert res1.status_code == 422

    # Too short barcode (< 8 digits)
    res2 = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Sample Variant",
            "sku": "VAR-ERR-BAR2",
            "barcode": "12345",
        },
    )
    assert res2.status_code == 422


def test_create_variant_validation_negative_prices(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]

    res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Sample Variant",
            "sku": "VAR-ERR-PRIC",
            "selling_price": "-10.00",
        },
    )
    assert res.status_code == 422


def test_create_variant_parent_not_found(setup_fixture):
    h = setup_fixture["owner_headers"]

    res = client.post(
        "/api/v1/products/999999/variants",
        headers=h,
        json={
            "variant_name": "Ghost Variant",
            "sku": "VAR-GHOST-01",
        },
    )
    assert res.status_code == 404


def test_create_variant_invalid_parent_id(setup_fixture):
    h = setup_fixture["owner_headers"]

    res = client.post(
        "/api/v1/products/0/variants",
        headers=h,
        json={
            "variant_name": "Invalid ID Variant",
            "sku": "VAR-INVAL-01",
        },
    )
    assert res.status_code in (404, 422)


# ============================================================================
# 3. SKU & BARCODE UNIQUENESS & CROSS-TABLE COLLISION CHECKS
# ============================================================================


def test_duplicate_variant_sku_same_tenant_conflict(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    sku = f"DUP-VAR-SKU-{setup_fixture['suffix']}".upper()

    res1 = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={"variant_name": "Variant 1", "sku": sku},
    )
    assert res1.status_code == 201

    res2 = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={"variant_name": "Variant 2", "sku": sku},
    )
    assert res2.status_code == 409
    assert "already exists" in res2.text.lower()


def test_variant_sku_collides_with_product_sku_conflict(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    parent_sku = setup_fixture["parent_product"]["sku"]

    # Attempt to create variant with the existing product's SKU
    res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={"variant_name": "Variant Collision", "sku": parent_sku},
    )
    assert res.status_code == 409
    assert "already exists" in res.text.lower()


def test_product_sku_collides_with_variant_sku_conflict(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    var_sku = f"VAR-FOR-PROD-COLL-{setup_fixture['suffix']}".upper()

    # Create variant first
    v_res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={"variant_name": "Variant Pre-existing", "sku": var_sku},
    )
    assert v_res.status_code == 201

    # Attempt to create a new product with the same SKU
    p_res = client.post(
        "/api/v1/products",
        headers=h,
        json={
            "name": "Collision Product",
            "sku": var_sku,
            "price": "100.00",
            "gst_rate": "18.00",
        },
    )
    assert p_res.status_code == 409
    assert "already exists" in p_res.text.lower()


def test_duplicate_variant_barcode_same_tenant_conflict(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    barcode = _gen_barcode(12)
    suffix = setup_fixture["suffix"]

    res1 = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Barcode Var 1",
            "sku": f"BAR-VAR-1-{suffix}".upper(),
            "barcode": barcode,
        },
    )
    assert res1.status_code == 201

    res2 = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Barcode Var 2",
            "sku": f"BAR-VAR-2-{suffix}".upper(),
            "barcode": barcode,
        },
    )
    assert res2.status_code == 409
    assert "already exists" in res2.text.lower()


def test_variant_barcode_collides_with_product_barcode_conflict(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    product_barcode = setup_fixture["parent_product"]["barcode"]
    suffix = setup_fixture["suffix"]

    # Attempt to create variant using parent product's barcode
    res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Barcode Var Collide",
            "sku": f"BAR-COLL-{suffix}".upper(),
            "barcode": product_barcode,
        },
    )
    assert res.status_code == 409
    assert "already exists" in res.text.lower()


def test_product_barcode_collides_with_variant_barcode_conflict(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    var_barcode = _gen_barcode(12)
    suffix = setup_fixture["suffix"]

    v_res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Barcode For Product Collide",
            "sku": f"VAR-BAR-PCOLL-{suffix}".upper(),
            "barcode": var_barcode,
        },
    )
    assert v_res.status_code == 201

    # Attempt to create product with that variant barcode
    p_res = client.post(
        "/api/v1/products",
        headers=h,
        json={
            "name": "Barcode Collide Product",
            "sku": f"PROD-BAR-COLL-{suffix}".upper(),
            "price": "199.00",
            "gst_rate": "12.00",
            "barcode": var_barcode,
        },
    )
    assert p_res.status_code == 409
    assert "already exists" in p_res.text.lower()


def test_same_sku_and_barcode_allowed_across_different_tenants(setup_fixture):
    t1_headers = setup_fixture["owner_headers"]
    t2_headers = setup_fixture["t2_headers"]
    t1_prod_id = setup_fixture["parent_product"]["id"]
    t2_prod_id = setup_fixture["t2_product"]["id"]

    shared_sku = f"SHARED-SKU-{setup_fixture['suffix']}".upper()
    shared_barcode = _gen_barcode(12)

    # Create variant in Tenant 1
    res1 = client.post(
        f"/api/v1/products/{t1_prod_id}/variants",
        headers=t1_headers,
        json={
            "variant_name": "Tenant 1 Shared Var",
            "sku": shared_sku,
            "barcode": shared_barcode,
        },
    )
    assert res1.status_code == 201

    # Create variant with identical SKU and barcode in Tenant 2 -> Allowed!
    res2 = client.post(
        f"/api/v1/products/{t2_prod_id}/variants",
        headers=t2_headers,
        json={
            "variant_name": "Tenant 2 Shared Var",
            "sku": shared_sku,
            "barcode": shared_barcode,
        },
    )
    assert res2.status_code == 201
    assert res2.json()["tenant_id"] == setup_fixture["tenant2_id"]


# ============================================================================
# 4. LISTING, FILTERING & RETRIEVAL TESTS
# ============================================================================


def test_list_variants_with_pagination(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]

    res = client.get(
        f"/api/v1/products/{prod_id}/variants?page=1&page_size=2",
        headers=h,
    )
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "items" in data
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) <= 2
    assert data["total"] >= 2


def test_list_variants_inactive_filter(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]

    # Create an inactive variant
    v_res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Inactive Variant Item",
            "sku": f"INACT-VAR-{suffix}".upper(),
            "is_active": False,
        },
    )
    assert v_res.status_code == 201
    inactive_id = v_res.json()["id"]

    # By default (include_inactive=False), inactive variant is omitted
    res_active = client.get(
        f"/api/v1/products/{prod_id}/variants?include_inactive=false&page_size=100",
        headers=h,
    )
    assert res_active.status_code == 200
    active_ids = [item["id"] for item in res_active.json()["items"]]
    assert inactive_id not in active_ids

    # With include_inactive=True, inactive variant is included
    res_all = client.get(
        f"/api/v1/products/{prod_id}/variants?include_inactive=true&page_size=100",
        headers=h,
    )
    assert res_all.status_code == 200
    all_ids = [item["id"] for item in res_all.json()["items"]]
    assert inactive_id in all_ids


def test_get_variant_by_id(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]

    v_res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Direct Get Variant",
            "sku": f"DIR-GET-{suffix}".upper(),
            "selling_price": "399.00",
        },
    )
    assert v_res.status_code == 201
    var_id = v_res.json()["id"]

    # Standalone variant endpoint: GET /api/v1/variants/{id}
    res = client.get(f"/api/v1/variants/{var_id}", headers=h)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == var_id
    assert data["variant_name"] == "Direct Get Variant"
    assert Decimal(str(data["effective_selling_price"])) == Decimal("399.00")


def test_get_variant_nested_route(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]

    v_res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Nested Route Variant",
            "sku": f"NEST-GET-{suffix}".upper(),
        },
    )
    assert v_res.status_code == 201
    var_id = v_res.json()["id"]

    # Nested variant endpoint: GET /api/v1/products/{prod_id}/variants/{id}
    res = client.get(f"/api/v1/products/{prod_id}/variants/{var_id}", headers=h)
    assert res.status_code == 200
    assert res.json()["id"] == var_id


def test_get_variant_not_found(setup_fixture):
    h = setup_fixture["owner_headers"]
    res = client.get("/api/v1/variants/999999", headers=h)
    assert res.status_code == 404


# ============================================================================
# 5. UPDATE (PUT / PATCH) TESTS
# ============================================================================


def test_update_variant_fields(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]

    v_res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Before Update",
            "sku": f"UPD-INIT-{suffix}".upper(),
            "size": "S",
            "selling_price": "300.00",
        },
    )
    assert v_res.status_code == 201
    var_id = v_res.json()["id"]

    # PUT /api/v1/variants/{id}
    upd_res = client.put(
        f"/api/v1/variants/{var_id}",
        headers=h,
        json={
            "variant_name": "After Update Name",
            "size": "M",
            "color": "Green",
            "selling_price": "350.00",
            "cost_price": "180.00",
        },
    )
    assert upd_res.status_code == 200
    data = upd_res.json()
    assert data["variant_name"] == "After Update Name"
    assert data["size"] == "M"
    assert data["color"] == "Green"
    assert Decimal(str(data["selling_price"])) == Decimal("350.00")
    assert Decimal(str(data["cost_price"])) == Decimal("180.00")


def test_update_variant_sku_to_unique_value(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]

    v_res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "SKU Change Var",
            "sku": f"OLD-SKU-{suffix}".upper(),
        },
    )
    assert v_res.status_code == 201
    var_id = v_res.json()["id"]

    new_sku = f"NEW-SKU-{suffix}".upper()
    patch_res = client.patch(
        f"/api/v1/variants/{var_id}",
        headers=h,
        json={"sku": new_sku},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["sku"] == new_sku


def test_update_variant_sku_duplicate_conflict(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]
    taken_sku = f"TAKEN-SKU-{suffix}".upper()

    # Create variant 1 with taken_sku
    client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={"variant_name": "Taken SKU Var", "sku": taken_sku},
    )

    # Create variant 2
    v2_res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={"variant_name": "V2 To Update", "sku": f"V2-TEMP-{suffix}".upper()},
    )
    v2_id = v2_res.json()["id"]

    # Try to update variant 2's SKU to taken_sku -> Conflict!
    patch_res = client.patch(
        f"/api/v1/variants/{v2_id}",
        headers=h,
        json={"sku": taken_sku},
    )
    assert patch_res.status_code == 409


def test_update_variant_same_sku_no_conflict(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]
    same_sku = f"SAME-SKU-{suffix}".upper()

    v_res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={"variant_name": "Same SKU Var", "sku": same_sku},
    )
    var_id = v_res.json()["id"]

    # Updating with identical SKU must NOT trigger self-conflict
    put_res = client.put(
        f"/api/v1/variants/{var_id}",
        headers=h,
        json={"sku": same_sku, "variant_name": "Same SKU Renamed"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["variant_name"] == "Same SKU Renamed"


def test_update_variant_same_barcode_no_conflict(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]
    barcode = _gen_barcode(12)

    v_res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "Same Barcode Var",
            "sku": f"SAME-BAR-{suffix}".upper(),
            "barcode": barcode,
        },
    )
    var_id = v_res.json()["id"]

    # Updating with identical barcode must NOT trigger self-conflict
    patch_res = client.patch(
        f"/api/v1/variants/{var_id}",
        headers=h,
        json={"barcode": barcode, "size": "XL"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["barcode"] == barcode
    assert patch_res.json()["size"] == "XL"


# ============================================================================
# 6. SOFT DELETION / LIFECYCLE TESTS
# ============================================================================


def test_soft_delete_variant(setup_fixture):
    h = setup_fixture["owner_headers"]
    prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]

    v_res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=h,
        json={
            "variant_name": "To Be Deleted",
            "sku": f"DEL-VAR-{suffix}".upper(),
        },
    )
    assert v_res.status_code == 201
    var_id = v_res.json()["id"]

    # Delete variant: sets is_active = False
    del_res = client.delete(f"/api/v1/variants/{var_id}", headers=h)
    assert del_res.status_code == 200
    assert del_res.json()["is_active"] is False

    # Check via direct GET: returns is_active = False
    get_res = client.get(f"/api/v1/variants/{var_id}", headers=h)
    assert get_res.status_code == 200
    assert get_res.json()["is_active"] is False

    # Check via default listing: omitted
    list_res = client.get(
        f"/api/v1/products/{prod_id}/variants?include_inactive=false&page_size=100",
        headers=h,
    )
    ids = [i["id"] for i in list_res.json()["items"]]
    assert var_id not in ids


def test_delete_variant_not_found(setup_fixture):
    h = setup_fixture["owner_headers"]
    res = client.delete("/api/v1/variants/999999", headers=h)
    assert res.status_code == 404


# ============================================================================
# 7. MULTI-TENANCY & AUTHORIZATION / IDOR PROTECTION
# ============================================================================


def test_cross_tenant_variant_isolation_idor(setup_fixture):
    t1_headers = setup_fixture["owner_headers"]
    t2_headers = setup_fixture["t2_headers"]
    t1_prod_id = setup_fixture["parent_product"]["id"]
    suffix = setup_fixture["suffix"]

    # Create variant in Tenant 1
    v_res = client.post(
        f"/api/v1/products/{t1_prod_id}/variants",
        headers=t1_headers,
        json={
            "variant_name": "T1 Secret Variant",
            "sku": f"T1-SEC-{suffix}".upper(),
        },
    )
    assert v_res.status_code == 201
    t1_var_id = v_res.json()["id"]

    # Tenant 2 attempts to GET Tenant 1's variant -> 404
    get_res = client.get(f"/api/v1/variants/{t1_var_id}", headers=t2_headers)
    assert get_res.status_code == 404

    # Tenant 2 attempts to UPDATE Tenant 1's variant -> 404
    put_res = client.put(
        f"/api/v1/variants/{t1_var_id}",
        headers=t2_headers,
        json={"variant_name": "Hacked Name"},
    )
    assert put_res.status_code == 404

    # Tenant 2 attempts to DELETE Tenant 1's variant -> 404
    del_res = client.delete(f"/api/v1/variants/{t1_var_id}", headers=t2_headers)
    assert del_res.status_code == 404

    # Tenant 2 attempts to create variant under Tenant 1's product -> 404
    post_res = client.post(
        f"/api/v1/products/{t1_prod_id}/variants",
        headers=t2_headers,
        json={"variant_name": "Cross Post Var", "sku": f"CROSS-POST-{suffix}"},
    )
    assert post_res.status_code == 404


def test_unauthenticated_variant_access(setup_fixture):
    res = client.get("/api/v1/variants/1")
    assert res.status_code == 401


def test_cashier_forbidden_variant_write(setup_fixture):
    c_headers = setup_fixture["cashier_headers"]
    prod_id = setup_fixture["parent_product"]["id"]

    # Cashier cannot create variant -> 403 Forbidden
    post_res = client.post(
        f"/api/v1/products/{prod_id}/variants",
        headers=c_headers,
        json={"variant_name": "Cashier Var", "sku": "CASHIER-SKU-01"},
    )
    assert post_res.status_code == 403

    # Cashier cannot update variant -> 403 Forbidden
    put_res = client.put(
        "/api/v1/variants/1",
        headers=c_headers,
        json={"variant_name": "Cashier Renamed"},
    )
    assert put_res.status_code == 403

    # Cashier cannot delete variant -> 403 Forbidden
    del_res = client.delete(
        "/api/v1/variants/1",
        headers=c_headers,
    )
    assert del_res.status_code == 403


# ============================================================================
# 8. BACKWARD COMPATIBILITY TESTS
# ============================================================================


def test_parent_product_variants_property_backward_compat(setup_fixture):
    db = SessionLocal()
    try:
        prod_id = setup_fixture["parent_product"]["id"]
        prod = db.query(Product).filter(Product.id == prod_id).first()
        assert prod is not None

        # Verify backward-compatible .variants property exists and contains list of dicts
        variants = prod.variants
        assert isinstance(variants, list)
        assert len(variants) > 0
        v = variants[0]
        assert "variant_name" in v or "sku" in v
    finally:
        db.close()
