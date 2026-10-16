import random
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.product import Product

client = TestClient(app)


def _gen_phone():
    return f"9{random.randint(100000000, 999999999)}"


def _gen_barcode(length: int = 12):
    return "".join(str(random.randint(0, 9)) for _ in range(length))


@pytest.fixture(scope="module")
def setup_variants_fixture():
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:6]

    try:
        owner_email = f"adv_var_{suffix}@retailtest.com"
        owner_pass = "OwnerPass123!"
        reg_res = client.post(
            "/api/v1/auth/register",
            json={
                "store_name": f"Variant Advanced {suffix}",
                "domain": f"varadv-{suffix}",
                "owner_email": owner_email,
                "owner_name": f"Owner {suffix}",
                "password": owner_pass,
                "owner_phone": _gen_phone(),
                "plan_code": "enterprise",
            },
        )
        assert reg_res.status_code == 200, reg_res.text
        tenant_id = reg_res.json()["tenant_id"]

        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": owner_email, "password": owner_pass},
        )
        assert login_res.status_code == 200
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Create base product
        p_res = client.post(
            "/api/v1/products",
            headers=headers,
            json={
                "name": f"Polo Sports T-Shirt {suffix}",
                "sku": f"POLO-{suffix}".upper(),
                "price": "899.00",
                "cost_price": "400.00",
                "gst_rate": "12.00",
                "barcode": _gen_barcode(12),
            },
        )
        assert p_res.status_code == 201, p_res.text
        product = p_res.json()

        return {
            "tenant_id": tenant_id,
            "headers": headers,
            "product": product,
            "suffix": suffix,
        }
    finally:
        db.close()


def test_matrix_generate_endpoint(setup_variants_fixture):
    """
    Test POST /api/v1/variants/matrix-generate:
    Generates matrix of 3 sizes x 2 colors = 6 variants in one request.
    """
    headers = setup_variants_fixture["headers"]
    prod_id = setup_variants_fixture["product"]["id"]
    suffix = setup_variants_fixture["suffix"]

    res = client.post(
        "/api/v1/variants/matrix-generate",
        headers=headers,
        json={
            "product_id": prod_id,
            "sizes": ["S", "M", "L"],
            "colors": ["Black", "White"],
            "sku_prefix": f"POLO-MAT-{suffix}".upper(),
            "selling_price": "949.00",
            "cost_price": "420.00",
            "attributes": {"fabric": "Polyester Dry-Fit"},
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["product_id"] == prod_id
    assert data["generated_count"] == 6
    assert len(data["variants"]) == 6

    # Verify attributes and generated SKUs
    skus = [v["sku"] for v in data["variants"]]
    assert f"POLO-MAT-{suffix}-S-BLACK".upper() in skus
    assert f"POLO-MAT-{suffix}-M-WHITE".upper() in skus
    assert f"POLO-MAT-{suffix}-L-BLACK".upper() in skus

    # Verify fallback and effective prices
    for v in data["variants"]:
        assert Decimal(str(v["effective_selling_price"])) == Decimal("949.00")
        assert Decimal(str(v["effective_cost_price"])) == Decimal("420.00")
        assert v["attributes"]["fabric"] == "Polyester Dry-Fit"
        assert v["product_name"] == setup_variants_fixture["product"]["name"]


def test_list_all_variants_with_filters(setup_variants_fixture):
    """
    Test GET /api/v1/variants:
    Lists variants with pagination, search, size, and color filters.
    """
    headers = setup_variants_fixture["headers"]
    prod_id = setup_variants_fixture["product"]["id"]

    # 1. Global list without filters
    res_all = client.get("/api/v1/variants", headers=headers)
    assert res_all.status_code == 200, res_all.text
    data = res_all.json()
    assert "total" in data
    assert "items" in data
    assert data["total"] >= 6

    # 2. Filter by product_id
    res_prod = client.get(f"/api/v1/variants?product_id={prod_id}", headers=headers)
    assert res_prod.status_code == 200
    assert res_prod.json()["total"] >= 6

    # 3. Filter by size
    res_size = client.get("/api/v1/variants?size=M", headers=headers)
    assert res_size.status_code == 200
    for v in res_size.json()["items"]:
        assert v["size"] == "M"

    # 4. Filter by color
    res_color = client.get("/api/v1/variants?color=Black", headers=headers)
    assert res_color.status_code == 200
    for v in res_color.json()["items"]:
        assert v["color"] == "Black"

    # 5. Search by keyword
    res_search = client.get("/api/v1/variants?search=Dry-Fit", headers=headers)
    assert res_search.status_code == 200


def test_lookup_by_barcode_and_sku(setup_variants_fixture):
    """
    Test:
    GET /api/v1/variants/by-barcode/{barcode}
    GET /api/v1/variants/by-sku/{sku}
    """
    headers = setup_variants_fixture["headers"]
    prod_id = setup_variants_fixture["product"]["id"]
    suffix = setup_variants_fixture["suffix"]
    barcode = _gen_barcode(12)
    sku = f"SCAN-VAR-{suffix}".upper()

    # Create variant with specific barcode and SKU
    create_res = client.post(
        "/api/v1/variants",
        headers=headers,
        json={
            "product_id": prod_id,
            "variant_name": "Scanner Test Item",
            "sku": sku,
            "barcode": barcode,
            "size": "XL",
        },
    )
    assert create_res.status_code == 201
    var_id = create_res.json()["id"]

    # 1. Lookup by Barcode (POS Scanner)
    res_bar = client.get(f"/api/v1/variants/by-barcode/{barcode}", headers=headers)
    assert res_bar.status_code == 200, res_bar.text
    assert res_bar.json()["id"] == var_id
    assert res_bar.json()["sku"] == sku
    assert res_bar.json()["barcode"] == barcode
    assert res_bar.json()["product_name"] == setup_variants_fixture["product"]["name"]

    # Barcode not found -> 404
    res_bar_404 = client.get("/api/v1/variants/by-barcode/999999999999", headers=headers)
    assert res_bar_404.status_code == 404

    # 2. Lookup by SKU (Warehouse)
    res_sku = client.get(f"/api/v1/variants/by-sku/{sku}", headers=headers)
    assert res_sku.status_code == 200, res_sku.text
    assert res_sku.json()["id"] == var_id
    assert res_sku.json()["barcode"] == barcode

    # SKU not found -> 404
    res_sku_404 = client.get("/api/v1/variants/by-sku/NONEXISTENT-SKU", headers=headers)
    assert res_sku_404.status_code == 404


def test_activate_and_deactivate_variant_endpoints(setup_variants_fixture):
    """
    Test:
    PATCH /api/v1/variants/{variant_id}/deactivate
    PATCH /api/v1/variants/{variant_id}/activate
    """
    headers = setup_variants_fixture["headers"]
    prod_id = setup_variants_fixture["product"]["id"]
    suffix = setup_variants_fixture["suffix"]

    create_res = client.post(
        "/api/v1/variants",
        headers=headers,
        json={
            "product_id": prod_id,
            "variant_name": "Toggle Status Item",
            "sku": f"TOGGLE-VAR-{suffix}".upper(),
            "is_active": True,
        },
    )
    assert create_res.status_code == 201
    var_id = create_res.json()["id"]

    # 1. Deactivate
    deact_res = client.patch(f"/api/v1/variants/{var_id}/deactivate", headers=headers)
    assert deact_res.status_code == 200, deact_res.text
    assert deact_res.json()["is_active"] is False

    # 2. Activate
    act_res = client.patch(f"/api/v1/variants/{var_id}/activate", headers=headers)
    assert act_res.status_code == 200, act_res.text
    assert act_res.json()["is_active"] is True


def test_variant_auto_barcode_and_missing_barcodes_generation(setup_variants_fixture):
    """
    Test:
    1. Matrix generation automatically assigns unique 13-digit EAN barcodes.
    2. POST /api/v1/variants/{variant_id}/generate-barcode generates barcode for item with null barcode.
    3. POST /api/v1/variants/generate-missing-barcodes populates barcodes for all null barcode variants.
    """
    headers = setup_variants_fixture["headers"]
    prod_id = setup_variants_fixture["product"]["id"]
    suffix = setup_variants_fixture["suffix"]

    # 1. Create a variant with barcode=None explicitly
    res_no_bc = client.post(
        "/api/v1/variants",
        headers=headers,
        json={
            "product_id": prod_id,
            "variant_name": "No Barcode Item 1",
            "sku": f"NO-BC-1-{suffix}".upper(),
            "barcode": None,
        },
    )
    assert res_no_bc.status_code == 201
    var1_id = res_no_bc.json()["id"]
    assert res_no_bc.json()["barcode"] is None

    res_no_bc2 = client.post(
        "/api/v1/variants",
        headers=headers,
        json={
            "product_id": prod_id,
            "variant_name": "No Barcode Item 2",
            "sku": f"NO-BC-2-{suffix}".upper(),
            "barcode": None,
        },
    )
    assert res_no_bc2.status_code == 201
    var2_id = res_no_bc2.json()["id"]
    assert res_no_bc2.json()["barcode"] is None

    # 2. Generate barcode for single variant
    gen_single = client.post(f"/api/v1/variants/{var1_id}/generate-barcode", headers=headers)
    assert gen_single.status_code == 200, gen_single.text
    body_single = gen_single.json()
    assert body_single["success"] is True
    assert body_single["variant_id"] == var1_id
    assert body_single["barcode"] is not None
    assert len(body_single["barcode"]) == 13
    assert body_single["barcode"].startswith("890")

    # Verify via get
    get_v1 = client.get(f"/api/v1/variants/{var1_id}", headers=headers)
    assert get_v1.json()["barcode"] == body_single["barcode"]

    # 3. Generate missing barcodes in bulk
    bulk_gen = client.post("/api/v1/variants/generate-missing-barcodes", headers=headers)
    assert bulk_gen.status_code == 200, bulk_gen.text
    body_bulk = bulk_gen.json()
    assert body_bulk["success"] is True
    assert body_bulk["updated_count"] >= 1
    # var2 must now have barcode
    get_v2 = client.get(f"/api/v1/variants/{var2_id}", headers=headers)
    assert get_v2.json()["barcode"] is not None
    assert len(get_v2.json()["barcode"]) == 13

    # 4. Generate matrix with auto_generate_barcode=True (default)
    mat_res = client.post(
        "/api/v1/variants/matrix-generate",
        headers=headers,
        json={
            "product_id": prod_id,
            "sizes": ["S", "M"],
            "colors": ["Green"],
            "sku_prefix": f"BC-MAT-{suffix}".upper(),
            "auto_generate_barcode": True,
        },
    )
    assert mat_res.status_code == 201
    mat_data = mat_res.json()
    for v in mat_data["variants"]:
        assert v["barcode"] is not None
        assert len(v["barcode"]) == 13
        assert v["barcode"].startswith("890")


