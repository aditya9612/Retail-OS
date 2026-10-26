import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.order_return import OrderReturnCreate, OrderReturnUpdate

client = TestClient(app)


def test_order_return_schema_rejects_invalid_reason():
    """Verify that reason rejects invalid junk, symbols, or placeholders."""
    # 1. QA issue payload: "o//"
    with pytest.raises(ValidationError) as exc:
        OrderReturnCreate(order_id=1, customer_id=1, reason="o//", remarks="Valid remarks here")
    assert "Reason" in str(exc.value)

    # 2. Placeholders like "string", "null", "test"
    with pytest.raises(ValidationError):
        OrderReturnCreate(order_id=1, customer_id=1, reason="string")

    with pytest.raises(ValidationError):
        OrderReturnCreate(order_id=1, customer_id=1, reason="test")

    # 3. Numeric digits only
    with pytest.raises(ValidationError):
        OrderReturnCreate(order_id=1, customer_id=1, reason="12345")

    # 4. Repetitive characters
    with pytest.raises(ValidationError):
        OrderReturnCreate(order_id=1, customer_id=1, reason="aaaaa")

    # 5. Consecutive special characters
    with pytest.raises(ValidationError):
        OrderReturnCreate(order_id=1, customer_id=1, reason="item//damaged")


def test_order_return_schema_rejects_invalid_remarks():
    """Verify that remarks rejects invalid junk, symbols, or placeholders."""
    # 1. QA issue payload: "p./"
    with pytest.raises(ValidationError) as exc:
        OrderReturnCreate(order_id=1, customer_id=1, reason="Defective product received", remarks="p./")
    assert "Remarks" in str(exc.value)

    # 2. Placeholders like "string", "test", "na"
    with pytest.raises(ValidationError):
        OrderReturnCreate(order_id=1, customer_id=1, reason="Defective product received", remarks="string")

    with pytest.raises(ValidationError):
        OrderReturnCreate(order_id=1, customer_id=1, reason="Defective product received", remarks="test")

    # 3. Numeric digits only
    with pytest.raises(ValidationError):
        OrderReturnCreate(order_id=1, customer_id=1, reason="Defective product received", remarks="12345")

    # 4. Consecutive special characters
    with pytest.raises(ValidationError):
        OrderReturnCreate(order_id=1, customer_id=1, reason="Defective product received", remarks="box..broken")


def test_order_return_schema_accepts_valid_inputs():
    """Verify valid reasons and optional/valid remarks pass."""
    # Remarks provided
    r1 = OrderReturnCreate(
        order_id=1,
        customer_id=1,
        reason="Defective item received",
        remarks="Customer found package damaged on delivery",
    )
    assert r1.reason == "Defective item received"
    assert r1.remarks == "Customer found package damaged on delivery"

    # Remarks None / omitted
    r2 = OrderReturnCreate(
        order_id=1,
        customer_id=1,
        reason="Wrong size delivered",
    )
    assert r2.reason == "Wrong size delivered"
    assert r2.remarks is None


@pytest.fixture
def setup_return_flow(unique_slug):
    email = f"return-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Return Test",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Return Admin",
            "password": "testpass123",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "testpass123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    store = client.post(
        "/api/v1/stores",
        json={"name": "Return Store", "code": "RS1"},
        headers=headers,
    ).json()

    customer = client.post(
        "/api/v1/customers",
        json={"name": "Test Customer", "phone": "9811223344", "email": "test@cust.com"},
        headers=headers,
    ).json()

    product = client.post(
        "/api/v1/products",
        json={"name": "Return Product", "sku": "RET-001", "price": "200.00"},
        headers=headers,
    ).json()

    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store["id"], "product_id": product["id"], "quantity": 20},
        headers=headers,
    )

    # Create order
    order = client.post(
        "/api/v1/orders",
        json={
            "store_id": store["id"],
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers=headers,
    ).json()

    return headers, order, customer


def test_api_order_return_validation_endpoint(setup_return_flow):
    headers, order, customer = setup_return_flow

    # 1. QA test case: "reason": "o//", "remarks": "p./" -> Must return 422 Unprocessable Entity
    resp_invalid = client.post(
        "/api/v1/order-returns",
        json={
            "order_id": order["id"],
            "customer_id": customer["id"],
            "reason": "o//",
            "remarks": "p./",
        },
        headers=headers,
    )
    assert resp_invalid.status_code == 422

    # 2. Invalid reason alone
    resp_inv_reason = client.post(
        "/api/v1/order-returns",
        json={
            "order_id": order["id"],
            "customer_id": customer["id"],
            "reason": "o//",
            "remarks": "Valid remarks here",
        },
        headers=headers,
    )
    assert resp_inv_reason.status_code == 422

    # 3. Invalid remarks alone
    resp_inv_remarks = client.post(
        "/api/v1/order-returns",
        json={
            "order_id": order["id"],
            "customer_id": customer["id"],
            "reason": "Defective item received",
            "remarks": "p./",
        },
        headers=headers,
    )
    assert resp_inv_remarks.status_code == 422

    # 4. Valid reason and remarks -> Must return 201 Created
    resp_valid = client.post(
        "/api/v1/order-returns",
        json={
            "order_id": order["id"],
            "customer_id": customer["id"],
            "reason": "Defective item received",
            "remarks": "Screen cracked inside box",
        },
        headers=headers,
    )
    assert resp_valid.status_code == 201
    data = resp_valid.json()
    assert data["reason"] == "Defective item received"
    assert data["remarks"] == "Screen cracked inside box"
    assert data["status"] == "requested"
