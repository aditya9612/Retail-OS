import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.customer import Customer, CustomerWallet
from app.models.inventory import Inventory, StockMovement
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_return import OrderReturn, OrderReturnItem
from app.models.product import Product
from app.models.store import Store
from app.models.user import User

client = TestClient(app)


def setup_test_context():
    """Sets up tenant, store, customer, products, and order for order return tests."""
    slug = f"ret-{uuid.uuid4().hex[:8]}"
    email = f"admin-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Returns Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Return Admin",
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

    # Store
    store = Store(
        tenant_id=tenant_id,
        name="Main Flagship Store",
        address="100 Commercial Blvd",
        is_active=True,
        is_main=True,
    )
    db.add(store)
    db.commit()
    db.refresh(store)

    # Customer
    customer = Customer(
        tenant_id=tenant_id,
        name="Sneha Patil",
        phone="9823000000",
        email=f"sneha-{uuid.uuid4().hex[:6]}@example.com",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    # Products
    prod_a = Product(
        tenant_id=tenant_id,
        name="Wireless Mouse",
        sku=f"MS-{uuid.uuid4().hex[:4].upper()}",
        selling_price=Decimal("500.00"),
        cost_price=Decimal("300.00"),
        is_active=True,
    )
    prod_b = Product(
        tenant_id=tenant_id,
        name="Mechanical Keyboard",
        sku=f"KB-{uuid.uuid4().hex[:4].upper()}",
        selling_price=Decimal("1500.00"),
        cost_price=Decimal("1000.00"),
        is_active=True,
    )
    db.add_all([prod_a, prod_b])
    db.commit()
    db.refresh(prod_a)
    db.refresh(prod_b)

    # Initial inventory
    inv_a = Inventory(
        tenant_id=tenant_id,
        store_id=store.id,
        product_id=prod_a.id,
        quantity=20,
    )
    inv_b = Inventory(
        tenant_id=tenant_id,
        store_id=store.id,
        product_id=prod_b.id,
        quantity=15,
    )
    db.add_all([inv_a, inv_b])
    db.commit()

    # Order with 2 items
    item_1 = OrderItem(
        product_id=prod_a.id,
        quantity=3,
        unit_price=Decimal("500.00"),
        total_amount=Decimal("1500.00"),
    )
    item_2 = OrderItem(
        product_id=prod_b.id,
        quantity=2,
        unit_price=Decimal("1500.00"),
        total_amount=Decimal("3000.00"),
    )
    order = Order(
        tenant_id=tenant_id,
        store_id=store.id,
        customer_id=customer.id,
        order_number=f"ORD-{uuid.uuid4().hex[:6].upper()}",
        order_type="pos",
        status="completed",
        subtotal=Decimal("4500.00"),
        total_amount=Decimal("4500.00"),
        items=[item_1, item_2],
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # Extract all primitive values before closing db session
    store_id = store.id
    customer_id = customer.id
    customer_name = customer.name
    prod_a_id = prod_a.id
    prod_b_id = prod_b.id
    order_id = order.id
    item_1_id = order.items[0].id
    item_2_id = order.items[1].id
    user_id = user.id

    db.close()

    return {
        "headers": headers,
        "tenant_id": tenant_id,
        "store_id": store_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "prod_a_id": prod_a_id,
        "prod_b_id": prod_b_id,
        "order_id": order_id,
        "item_1_id": item_1_id,
        "item_2_id": item_2_id,
        "user_id": user_id,
    }


def test_create_order_return_with_specific_items():
    ctx = setup_test_context()
    headers = ctx["headers"]
    order_id = ctx["order_id"]
    customer_id = ctx["customer_id"]
    item_1_id = ctx["item_1_id"]
    item_2_id = ctx["item_2_id"]

    payload = {
        "order_id": order_id,
        "customer_id": customer_id,
        "reason": "Defective item received",
        "remarks": "Left click button is not working properly",
        "return_type": "refund",
        "items": [
            {
                "order_item_id": item_1_id,
                "quantity": 2,
                "condition": "sellable",
                "reason": "Customer changed mind",
            },
            {
                "order_item_id": item_2_id,
                "quantity": 1,
                "condition": "damaged",
                "reason": "Key switch broken",
            },
        ],
    }

    res = client.post("/api/v1/order-returns", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["order_id"] == order_id
    assert data["customer_id"] == customer_id
    assert data["status"] == "requested"
    assert data["return_number"].startswith("RMA-")
    assert Decimal(str(data["total_amount"])) == Decimal("2500.00")  # (2 * 500) + (1 * 1500)
    assert len(data["items"]) == 2
    assert data["items"][0]["quantity"] == 2
    assert data["items"][1]["quantity"] == 1


def test_create_order_return_auto_populates_all_items():
    ctx = setup_test_context()
    headers = ctx["headers"]
    order_id = ctx["order_id"]
    customer_id = ctx["customer_id"]

    payload = {
        "order_id": order_id,
        "customer_id": customer_id,
        "reason": "Customer returned full order",
        "remarks": "Order cancelled after dispatch",
        "items": [],
    }

    res = client.post("/api/v1/order-returns", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["status"] == "requested"
    assert Decimal(str(data["total_amount"])) == Decimal("4500.00")
    assert len(data["items"]) == 2


def test_create_order_return_validations():
    ctx = setup_test_context()
    headers = ctx["headers"]
    order_id = ctx["order_id"]
    customer_id = ctx["customer_id"]
    item_1_id = ctx["item_1_id"]

    # 1. Quantity exceeds purchased quantity (ordered 3, trying to return 5)
    bad_payload = {
        "order_id": order_id,
        "customer_id": customer_id,
        "reason": "Exceeded return request",
        "items": [
            {
                "order_item_id": item_1_id,
                "quantity": 5,
            }
        ],
    }
    res = client.post("/api/v1/order-returns", json=bad_payload, headers=headers)
    assert res.status_code == 400
    assert "available for return" in res.text

    # 2. Customer ID mismatch
    db = SessionLocal()
    other_cust = Customer(tenant_id=ctx["tenant_id"], name="Other Person", phone="9999999999")
    db.add(other_cust)
    db.commit()
    db.refresh(other_cust)
    other_cust_id = other_cust.id
    db.close()

    mismatch_payload = {
        "order_id": order_id,
        "customer_id": other_cust_id,
        "reason": "Customer mismatch test",
        "items": [],
    }
    res2 = client.post("/api/v1/order-returns", json=mismatch_payload, headers=headers)
    assert res2.status_code == 400
    assert "does not belong" in res2.text

    # 3. Duplicate active return conflict
    valid_payload = {
        "order_id": order_id,
        "customer_id": customer_id,
        "reason": "Valid return request",
        "items": [],
    }
    res3 = client.post("/api/v1/order-returns", json=valid_payload, headers=headers)
    assert res3.status_code == 201

    res4 = client.post("/api/v1/order-returns", json=valid_payload, headers=headers)
    assert res4.status_code == 409
    assert "Active return already exists" in res4.text


def test_update_and_lifecycle_workflow():
    ctx = setup_test_context()
    headers = ctx["headers"]
    order_id = ctx["order_id"]
    customer_id = ctx["customer_id"]

    # 1. Create return
    res = client.post(
        "/api/v1/order-returns",
        json={
            "order_id": order_id,
            "customer_id": customer_id,
            "reason": "Original reason",
            "remarks": "Original remarks",
            "items": [],
        },
        headers=headers,
    )
    assert res.status_code == 201
    return_id = res.json()["id"]

    # 2. Update return fields
    patch_res = client.patch(
        f"/api/v1/order-returns/{return_id}",
        json={"reason": "Updated reason details", "remarks": "Updated remarks notes"},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["reason"] == "Updated reason details"

    # 3. Approve return
    appr_res = client.post(f"/api/v1/order-returns/{return_id}/approve", headers=headers)
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "approved"
    assert appr_res.json()["approved_at"] is not None

    # 4. Reject cannot be performed on approved return
    rej_res = client.post(
        f"/api/v1/order-returns/{return_id}/reject",
        json={"remarks": "Too late to reject"},
        headers=headers,
    )
    assert rej_res.status_code == 400


def test_reject_workflow():
    ctx = setup_test_context()
    headers = ctx["headers"]
    order_id = ctx["order_id"]
    customer_id = ctx["customer_id"]

    res = client.post(
        "/api/v1/order-returns",
        json={
            "order_id": order_id,
            "customer_id": customer_id,
            "reason": "Warranty claim",
            "items": [],
        },
        headers=headers,
    )
    return_id = res.json()["id"]

    rej_res = client.post(
        f"/api/v1/order-returns/{return_id}/reject",
        json={"remarks": "Physical damage not covered by warranty policy"},
        headers=headers,
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "rejected"
    assert rej_res.json()["rejection_reason"] == "Physical damage not covered by warranty policy"


def test_complete_return_restocks_inventory_and_updates_order_status():
    ctx = setup_test_context()
    headers = ctx["headers"]
    store_id = ctx["store_id"]
    prod_a_id = ctx["prod_a_id"]
    order_id = ctx["order_id"]
    customer_id = ctx["customer_id"]
    item_1_id = ctx["item_1_id"]

    db = SessionLocal()
    initial_inv = db.query(Inventory).filter(
        Inventory.store_id == store_id,
        Inventory.product_id == prod_a_id,
    ).first()
    starting_stock = initial_inv.quantity
    db.close()

    # Create return for item_1 (qty 2 sellable)
    create_res = client.post(
        "/api/v1/order-returns",
        json={
            "order_id": order_id,
            "customer_id": customer_id,
            "reason": "Partial return sellable",
            "items": [
                {
                    "order_item_id": item_1_id,
                    "quantity": 2,
                    "condition": "sellable",
                }
            ],
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    return_id = create_res.json()["id"]

    # Approve
    client.post(f"/api/v1/order-returns/{return_id}/approve", headers=headers)

    # Complete
    comp_res = client.post(f"/api/v1/order-returns/{return_id}/complete", headers=headers)
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    assert comp_data["status"] == "completed"
    assert Decimal(str(comp_data["refund_amount"])) == Decimal("1000.00")
    assert comp_data["completed_at"] is not None

    # Check inventory was restocked (+2)
    db = SessionLocal()
    updated_inv = db.query(Inventory).filter(
        Inventory.store_id == store_id,
        Inventory.product_id == prod_a_id,
    ).first()
    assert updated_inv.quantity == starting_stock + 2

    # Check stock movement
    mov = db.query(StockMovement).filter(
        StockMovement.reference_id == return_id,
        StockMovement.reference_type == "order_return",
    ).first()
    assert mov is not None
    assert mov.quantity == 2
    assert mov.movement_type == "return"

    # Check order status is partially_returned
    updated_order = db.query(Order).filter(Order.id == order_id).first()
    assert updated_order.status == "partially_returned"
    db.close()


def test_complete_store_credit_credits_customer_wallet():
    ctx = setup_test_context()
    headers = ctx["headers"]
    order_id = ctx["order_id"]
    customer_id = ctx["customer_id"]
    item_1_id = ctx["item_1_id"]

    create_res = client.post(
        "/api/v1/order-returns",
        json={
            "order_id": order_id,
            "customer_id": customer_id,
            "reason": "Store credit return",
            "return_type": "store_credit",
            "items": [
                {
                    "order_item_id": item_1_id,
                    "quantity": 1,
                    "condition": "sellable",
                }
            ],
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    return_id = create_res.json()["id"]

    client.post(f"/api/v1/order-returns/{return_id}/approve", headers=headers)
    client.post(f"/api/v1/order-returns/{return_id}/complete", headers=headers)

    # Verify wallet has 500 balance
    db = SessionLocal()
    wallet = db.query(CustomerWallet).filter(CustomerWallet.customer_id == customer_id).first()
    assert wallet is not None
    assert wallet.current_balance == Decimal("500.00")
    db.close()


def test_order_returns_stats():
    ctx = setup_test_context()
    headers = ctx["headers"]

    stats_res = client.get("/api/v1/order-returns/stats", headers=headers)
    assert stats_res.status_code == 200, stats_res.text
    stats = stats_res.json()
    assert "total_returns" in stats
    assert "requested_count" in stats
    assert "approved_count" in stats
    assert "completed_count" in stats
    assert "rejected_count" in stats
    assert "total_refund_amount" in stats


def test_order_return_slip_json_and_html():
    ctx = setup_test_context()
    headers = ctx["headers"]
    order_id = ctx["order_id"]
    customer_id = ctx["customer_id"]
    customer_name = ctx["customer_name"]
    item_1_id = ctx["item_1_id"]

    create_res = client.post(
        "/api/v1/order-returns",
        json={
            "order_id": order_id,
            "customer_id": customer_id,
            "reason": "Need slip receipt",
            "items": [
                {
                    "order_item_id": item_1_id,
                    "quantity": 1,
                    "condition": "sellable",
                }
            ],
        },
        headers=headers,
    )
    return_id = create_res.json()["id"]

    # 1. Visual Preview Mode (PNG Image rendered directly in Swagger UI)
    slip_prev = client.get(f"/api/v1/order-returns/{return_id}/slip?mode=preview", headers=headers)
    assert slip_prev.status_code == 200
    assert "image/png" in slip_prev.headers["content-type"]
    assert slip_prev.content[:8] == b"\x89PNG\r\n\x1a\n"

    # 2. JSON Slip
    slip_json = client.get(f"/api/v1/order-returns/{return_id}/slip?mode=json", headers=headers)
    assert slip_json.status_code == 200
    data = slip_json.json()
    assert data["return_id"] == return_id
    assert data["customer_name"] == customer_name
    assert len(data["items"]) == 1
    assert data["items"][0]["product_name"] == "Wireless Mouse"

    # 3. HTML Slip (View mode with auto-print)
    slip_html = client.get(f"/api/v1/order-returns/{return_id}/slip?mode=view", headers=headers)
    assert slip_html.status_code == 200
    assert "text/html" in slip_html.headers["content-type"]
    assert "RETURN SLIP / RMA" in slip_html.text
    assert "Wireless Mouse" in slip_html.text
    assert "window.print()" in slip_html.text

    # 4. Download mode (HTML file attachment)
    slip_dl = client.get(f"/api/v1/order-returns/{return_id}/slip?mode=download", headers=headers)
    assert slip_dl.status_code == 200
    assert "attachment" in slip_dl.headers["content-disposition"]


def test_order_return_exchange():
    ctx = setup_test_context()
    headers = ctx["headers"]
    order_id = ctx["order_id"]
    customer_id = ctx["customer_id"]
    prod_b_id = ctx["prod_b_id"]

    create_res = client.post(
        "/api/v1/order-returns",
        json={
            "order_id": order_id,
            "customer_id": customer_id,
            "reason": "Exchange requested",
            "items": [],
        },
        headers=headers,
    )
    return_id = create_res.json()["id"]
    client.post(f"/api/v1/order-returns/{return_id}/approve", headers=headers)

    # Process exchange with replacement product
    exch_payload = {
        "exchange_items": [
            {
                "product_id": prod_b_id,
                "quantity": 1,
                "unit_price": 1500.00,
            }
        ],
        "notes": "Customer exchanged for Mechanical Keyboard",
    }
    exch_res = client.post(f"/api/v1/order-returns/{return_id}/exchange", json=exch_payload, headers=headers)
    assert exch_res.status_code == 200
    exch_data = exch_res.json()
    assert exch_data["return_type"] == "exchange"
    assert exch_data["exchange_order_id"] is not None

    # Check that new exchange order was created
    db = SessionLocal()
    new_order = db.query(Order).filter(Order.id == exch_data["exchange_order_id"]).first()
    assert new_order is not None
    assert new_order.order_type == "exchange"
    assert new_order.total_amount == Decimal("1500.00")
    db.close()


def test_list_order_returns_filters():
    ctx = setup_test_context()
    headers = ctx["headers"]
    order_id = ctx["order_id"]
    customer_id = ctx["customer_id"]

    create_res = client.post(
        "/api/v1/order-returns",
        json={
            "order_id": order_id,
            "customer_id": customer_id,
            "reason": "Filter search test item",
            "remarks": "UniqueFilterRemark123",
            "items": [],
        },
        headers=headers,
    )
    ret_id = create_res.json()["id"]

    # Filter by status
    res_status = client.get("/api/v1/order-returns?status=requested", headers=headers)
    assert res_status.status_code == 200
    assert any(r["id"] == ret_id for r in res_status.json())

    # Filter by search
    res_search = client.get("/api/v1/order-returns?search=UniqueFilterRemark123", headers=headers)
    assert res_search.status_code == 200
    assert len(res_search.json()) == 1
    assert res_search.json()[0]["id"] == ret_id

    # Filter by customer_id
    res_cust = client.get(f"/api/v1/order-returns?customer_id={customer_id}", headers=headers)
    assert res_cust.status_code == 200
    assert any(r["id"] == ret_id for r in res_cust.json())

