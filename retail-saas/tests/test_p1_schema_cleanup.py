import pytest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.customer import CustomerCreate, WalletCreditRequest, WalletDebitRequest
from app.schemas.store_expense import StoreExpenseCreate, PaymentMethod
from app.schemas.delivery import DeliveryMethodCreate, DeliveryZoneCreate
from app.schemas.order_return import OrderReturnCreate
from app.api.v1.auth.router import router as auth_router

client = TestClient(app)


def test_dead_schemas_are_removed():
    """Verify that dead duplicate schemas cannot be imported from their removed modules."""
    import app.schemas.user as user_schema
    assert not hasattr(user_schema, "StoreBase"), "StoreBase should be removed from user.py"
    assert not hasattr(user_schema, "StoreCreate"), "StoreCreate should be removed from user.py"
    assert not hasattr(user_schema, "StoreUpdate"), "StoreUpdate should be removed from user.py"

    import app.schemas.product as product_schema
    assert not hasattr(product_schema, "CategoryBase"), "CategoryBase should be removed from product.py"
    assert not hasattr(product_schema, "CategoryCreate"), "CategoryCreate should be removed from product.py"
    assert not hasattr(product_schema, "CategoryResponse"), "CategoryResponse should be removed from product.py"

    import app.schemas.order as order_schema
    assert not hasattr(order_schema, "PaymentCreate"), "PaymentCreate should be removed from order.py"


def test_customer_create_optional_address():
    """CustomerCreate.address is optional, but still validated if provided."""
    # 1. Address omitted / None
    c1 = CustomerCreate(name="Rajesh Kumar", phone="9876543210")
    assert c1.address is None

    c2 = CustomerCreate(name="Rajesh Kumar", phone="9876543210", address=None)
    assert c2.address is None

    # 2. Valid address
    c3 = CustomerCreate(name="Rajesh Kumar", phone="9876543210", address="123 MG Road, Pune, Maharashtra 411001")
    assert c3.address == "123 MG Road, Pune, Maharashtra 411001"

    # 3. Invalid address when provided (empty or placeholder)
    with pytest.raises(ValidationError):
        CustomerCreate(name="Rajesh Kumar", phone="9876543210", address="   ")

    with pytest.raises(ValidationError):
        CustomerCreate(name="Rajesh Kumar", phone="9876543210", address="string")


def test_store_expense_create_optional_description():
    """StoreExpenseCreate.description is optional, but validated if provided."""
    # 1. Description omitted / None
    e1 = StoreExpenseCreate(
        store_id=1,
        amount=Decimal("1500.00"),
        category="Utilities",
        expense_date=date.today(),
        payment_method=PaymentMethod.CASH,
    )
    assert e1.description is None

    e2 = StoreExpenseCreate(
        store_id=1,
        amount=Decimal("1500.00"),
        category="Utilities",
        description=None,
        expense_date=date.today(),
        payment_method=PaymentMethod.CASH,
    )
    assert e2.description is None

    # 2. Valid description
    e3 = StoreExpenseCreate(
        store_id=1,
        amount=Decimal("1500.00"),
        category="Utilities",
        description="Electricity Bill September",
        expense_date=date.today(),
        payment_method=PaymentMethod.CASH,
    )
    assert e3.description == "Electricity Bill September"

    # 3. Invalid description when provided (special characters or empty)
    with pytest.raises(ValidationError):
        StoreExpenseCreate(
            store_id=1,
            amount=Decimal("1500.00"),
            category="Utilities",
            description="   ",
            expense_date=date.today(),
            payment_method=PaymentMethod.CASH,
        )

    with pytest.raises(ValidationError):
        StoreExpenseCreate(
            store_id=1,
            amount=Decimal("1500.00"),
            category="Utilities",
            description="Bill@123#",
            expense_date=date.today(),
            payment_method=PaymentMethod.CASH,
        )


def test_delivery_method_create_optional_description():
    """DeliveryMethodCreate.description is optional, but validated if provided."""
    # 1. Description omitted / None
    dm1 = DeliveryMethodCreate(name="Standard Express", code="STD_EXP", cost=Decimal("50.00"))
    assert dm1.description is None

    dm2 = DeliveryMethodCreate(name="Standard Express", code="STD_EXP", description=None, cost=Decimal("50.00"))
    assert dm2.description is None

    # 2. Valid description
    dm3 = DeliveryMethodCreate(name="Standard Express", code="STD_EXP", description="Standard 2-day delivery", cost=Decimal("50.00"))
    assert dm3.description == "Standard 2-day delivery"

    # 3. Invalid description when provided
    with pytest.raises(ValidationError):
        DeliveryMethodCreate(name="Standard Express", code="STD_EXP", description="   ")

    with pytest.raises(ValidationError):
        DeliveryMethodCreate(name="Standard Express", code="STD_EXP", description="string")


def test_delivery_zone_create_optional_description():
    """DeliveryZoneCreate.description is optional, but validated if provided."""
    # 1. Description omitted / None
    dz1 = DeliveryZoneCreate(name="West Zone", code="WZ_01")
    assert dz1.description is None

    dz2 = DeliveryZoneCreate(name="West Zone", code="WZ_01", description=None)
    assert dz2.description is None

    # 2. Valid description
    dz3 = DeliveryZoneCreate(name="West Zone", code="WZ_01", description="Western suburbs coverage")
    assert dz3.description == "Western suburbs coverage"

    # 3. Invalid description when provided
    with pytest.raises(ValidationError):
        DeliveryZoneCreate(name="West Zone", code="WZ_01", description="   ")

    with pytest.raises(ValidationError):
        DeliveryZoneCreate(name="West Zone", code="WZ_01", description="string")


def test_order_return_create_optional_remarks():
    """OrderReturnCreate.remarks is optional, while reason remains required."""
    # 1. Remarks omitted / None
    r1 = OrderReturnCreate(order_id=10, customer_id=5, reason="Defective item received")
    assert r1.remarks is None

    r2 = OrderReturnCreate(order_id=10, customer_id=5, reason="Defective item received", remarks=None)
    assert r2.remarks is None

    # 2. Valid remarks
    r3 = OrderReturnCreate(order_id=10, customer_id=5, reason="Defective item received", remarks="Customer unpacked broken item")
    assert r3.remarks == "Customer unpacked broken item"

    # 3. Reason is strictly required
    with pytest.raises(ValidationError):
        OrderReturnCreate(order_id=10, customer_id=5, reason="", remarks="Valid remarks")

    with pytest.raises(ValidationError):
        OrderReturnCreate(order_id=10, customer_id=5, reason="string", remarks="Valid remarks")


def test_wallet_operation_base_optional_remarks():
    """WalletCreditRequest / WalletDebitRequest remarks are optional."""
    # 1. Remarks omitted / None
    w1 = WalletCreditRequest(customer_id=1, amount=Decimal("500.00"), reference_no="REF-12345")
    assert w1.remarks is None

    w2 = WalletDebitRequest(customer_id=1, amount=Decimal("200.00"), reference_no="REF-67890", remarks=None)
    assert w2.remarks is None

    # 2. Valid remarks
    w3 = WalletCreditRequest(customer_id=1, amount=Decimal("500.00"), reference_no="REF-12345", remarks="Loyalty bonus credit")
    assert w3.remarks == "Loyalty bonus credit"

    # 3. Invalid remarks when provided
    with pytest.raises(ValidationError):
        WalletCreditRequest(customer_id=1, amount=Decimal("500.00"), reference_no="REF-12345", remarks="string")


def test_auth_refresh_endpoints_and_deprecation():
    """Test both refresh and refresh-token endpoints and verify deprecation metadata."""
    # Check OpenAPI route metadata
    routes = {r.path: r for r in auth_router.routes}
    assert "/auth/refresh" in routes
    assert "/auth/refresh-token" in routes

    refresh_route = routes["/auth/refresh"]
    assert not getattr(refresh_route, "deprecated", False)

    refresh_token_route = routes["/auth/refresh-token"]
    assert getattr(refresh_token_route, "deprecated", False) is True

    # Check request behavior on both endpoints (both reject invalid token identically)
    resp1 = client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid_test_token"})
    resp2 = client.post("/api/v1/auth/refresh-token", json={"refresh_token": "invalid_test_token"})

    assert resp1.status_code == resp2.status_code
    assert resp1.json() == resp2.json()
