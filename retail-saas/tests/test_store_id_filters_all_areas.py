import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.credit_note import CreditNote
from app.models.customer import Customer
from app.models.delivery import Delivery
from app.models.delivery_method import DeliveryMethod
from app.models.delivery_partner import DeliveryPartner
from app.models.grn import GRN
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_return import OrderReturn
from app.models.payment import Payment
from app.models.pos_shift import POSShift
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_return import PurchaseOrderReturn
from app.models.refund import Refund
from app.models.store import Store
from app.models.supplier import Supplier
from app.models.user import User

client = TestClient(app)


def setup_multi_store_environment():
    """Sets up a tenant with 2 separate stores and returns session details."""
    slug = f"ms-{uuid.uuid4().hex[:8]}"
    email = f"owner-{slug}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Enterprise Retail {slug}",
            "slug": slug,
            "email": email,
            "admin_name": "Super Owner",
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

    # Store A (Pune)
    store_a = Store(
        tenant_id=tenant_id,
        name="Pune FC Road Branch",
        address="100 FC Road, Pune",
        is_active=True,
        is_main=True,
    )
    # Store B (Mumbai)
    store_b = Store(
        tenant_id=tenant_id,
        name="Mumbai Bandra Branch",
        address="200 Linking Road, Bandra, Mumbai",
        is_active=True,
        is_main=False,
    )
    db.add_all([store_a, store_b])
    db.commit()
    db.refresh(store_a)
    db.refresh(store_b)

    customer = Customer(
        tenant_id=tenant_id,
        name="Ramesh Sharma",
        phone="9876543210",
        email=f"ramesh-{uuid.uuid4().hex[:6]}@example.com",
    )
    db.add(customer)

    supplier = Supplier(
        tenant_id=tenant_id,
        name="Apex Vendor Pvt Ltd",
        email=f"vendor-{uuid.uuid4().hex[:6]}@example.com",
        phone="9123456789",
    )
    db.add(supplier)

    product_a = Product(
        tenant_id=tenant_id,
        name="Pune Special Chai Masala",
        sku=f"CHAI-{uuid.uuid4().hex[:4].upper()}",
        price=Decimal("150.00"),
        cost_price=Decimal("90.00"),
    )
    product_b = Product(
        tenant_id=tenant_id,
        name="Mumbai Vada Pav Mix",
        sku=f"VADA-{uuid.uuid4().hex[:4].upper()}",
        price=Decimal("120.00"),
        cost_price=Decimal("70.00"),
    )
    db.add_all([product_a, product_b])
    db.commit()
    db.refresh(customer)
    db.refresh(supplier)
    db.refresh(product_a)
    db.refresh(product_b)

    return {
        "db": db,
        "headers": headers,
        "tenant_id": tenant_id,
        "user": user,
        "store_a": store_a,
        "store_b": store_b,
        "customer": customer,
        "supplier": supplier,
        "product_a": product_a,
        "product_b": product_b,
    }


def test_area1_delivery_store_id_filters():
    ctx = setup_multi_store_environment()
    db = ctx["db"]
    headers = ctx["headers"]
    tenant_id = ctx["tenant_id"]
    store_a = ctx["store_a"]
    store_b = ctx["store_b"]
    customer = ctx["customer"]

    # Order A in Store A
    order_a = Order(
        tenant_id=tenant_id,
        store_id=store_a.id,
        customer_id=customer.id,
        order_number=f"ORD-A-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("500.00"),
        status="confirmed",
    )
    # Order B in Store B
    order_b = Order(
        tenant_id=tenant_id,
        store_id=store_b.id,
        customer_id=customer.id,
        order_number=f"ORD-B-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("800.00"),
        status="confirmed",
    )
    db.add_all([order_a, order_b])
    db.commit()
    db.refresh(order_a)
    db.refresh(order_b)

    # Deliveries
    del_a = Delivery(
        tenant_id=tenant_id,
        order_id=order_a.id,
        status="pending",
        delivery_person="Rider Pune",
        is_cod=True,
        cod_amount=Decimal("500.00"),
        cod_collected=False,
    )
    del_b = Delivery(
        tenant_id=tenant_id,
        order_id=order_b.id,
        status="delivered",
        delivery_person="Rider Mumbai",
        is_cod=True,
        cod_amount=Decimal("800.00"),
        cod_collected=True,
    )
    db.add_all([del_a, del_b])
    db.commit()
    db.refresh(del_a)
    db.refresh(del_b)

    # 1. list_deliveries with store_id
    res_a = client.get(f"/api/v1/delivery?store_id={store_a.id}", headers=headers)
    assert res_a.status_code == 200, res_a.text
    items_a = res_a.json()["data"]
    assert len(items_a) == 1
    assert items_a[0]["order_id"] == order_a.id

    res_b = client.get(f"/api/v1/delivery?store_id={store_b.id}", headers=headers)
    assert res_b.status_code == 200, res_b.text
    items_b = res_b.json()["data"]
    assert len(items_b) == 1
    assert items_b[0]["order_id"] == order_b.id

    # 2. get_stats with store_id
    stats_a = client.get(f"/api/v1/delivery/stats?store_id={store_a.id}", headers=headers)
    assert stats_a.status_code == 200, stats_a.text
    data_a = stats_a.json()["data"]
    assert data_a["total_deliveries"] == 1
    assert data_a["pending_deliveries"] == 1
    assert data_a["delivered_deliveries"] == 0

    stats_b = client.get(f"/api/v1/delivery/stats?store_id={store_b.id}", headers=headers)
    assert stats_b.status_code == 200, stats_b.text
    data_b = stats_b.json()["data"]
    assert data_b["total_deliveries"] == 1
    assert data_b["pending_deliveries"] == 0
    assert data_b["delivered_deliveries"] == 1

    # 3. export with store_id
    exp_a = client.get(f"/api/v1/delivery/export?format=csv&store_id={store_a.id}", headers=headers)
    assert exp_a.status_code == 200, exp_a.text
    assert order_a.order_number in exp_a.text
    assert order_b.order_number not in exp_a.text

    # 4. cod-reconciliation with store_id
    cod_a = client.get(f"/api/v1/delivery/cod-reconciliation?store_id={store_a.id}", headers=headers)
    assert cod_a.status_code == 200, cod_a.text
    cod_summary_a = cod_a.json()["summary"]
    assert cod_summary_a["total_cod_orders"] == 1
    assert float(cod_summary_a["total_cod_amount"]) == 500.0
    assert cod_summary_a["collected_orders_count"] == 0

    db.close()


def test_area2_returns_refunds_credit_notes_store_id_filters():
    ctx = setup_multi_store_environment()
    db = ctx["db"]
    headers = ctx["headers"]
    tenant_id = ctx["tenant_id"]
    store_a = ctx["store_a"]
    store_b = ctx["store_b"]
    customer = ctx["customer"]

    order_a = Order(
        tenant_id=tenant_id,
        store_id=store_a.id,
        customer_id=customer.id,
        order_number=f"ORD-A2-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("1000.00"),
        status="confirmed",
    )
    order_b = Order(
        tenant_id=tenant_id,
        store_id=store_b.id,
        customer_id=customer.id,
        order_number=f"ORD-B2-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("2000.00"),
        status="confirmed",
    )
    db.add_all([order_a, order_b])
    db.commit()
    db.refresh(order_a)
    db.refresh(order_b)

    inv_a = Invoice(
        tenant_id=tenant_id,
        store_id=store_a.id,
        order_id=order_a.id,
        invoice_number=f"INV-A-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("1000.00"),
    )
    inv_b = Invoice(
        tenant_id=tenant_id,
        store_id=store_b.id,
        order_id=order_b.id,
        invoice_number=f"INV-B-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("2000.00"),
    )
    db.add_all([inv_a, inv_b])
    db.commit()
    db.refresh(inv_a)
    db.refresh(inv_b)

    # Refunds
    ref_a = Refund(
        tenant_id=tenant_id,
        invoice_id=inv_a.id,
        refund_amount=Decimal("200.00"),
        status="completed",
        refund_status="completed",
        refund_method="cash",
    )
    ref_b = Refund(
        tenant_id=tenant_id,
        invoice_id=inv_b.id,
        refund_amount=Decimal("500.00"),
        status="completed",
        refund_status="completed",
        refund_method="upi",
    )
    db.add_all([ref_a, ref_b])
    db.commit()
    db.refresh(ref_a)
    db.refresh(ref_b)

    # Credit Notes
    cn_a = CreditNote(
        tenant_id=tenant_id,
        invoice_id=inv_a.id,
        refund_id=ref_a.id,
        credit_note_no=f"CN-A-{uuid.uuid4().hex[:6]}",
        refund_amount=Decimal("200.00"),
    )
    cn_b = CreditNote(
        tenant_id=tenant_id,
        invoice_id=inv_b.id,
        refund_id=ref_b.id,
        credit_note_no=f"CN-B-{uuid.uuid4().hex[:6]}",
        refund_amount=Decimal("500.00"),
    )
    db.add_all([cn_a, cn_b])

    # Order Returns
    ret_a = OrderReturn(
        tenant_id=tenant_id,
        order_id=order_a.id,
        customer_id=customer.id,
        reason="Damaged in transit",
        status="approved",
    )
    ret_b = OrderReturn(
        tenant_id=tenant_id,
        order_id=order_b.id,
        customer_id=customer.id,
        reason="Wrong item received",
        status="approved",
    )
    db.add_all([ret_a, ret_b])
    db.commit()

    # 1. Refunds filtered by store_id
    res_ref_a = client.get(f"/api/v1/refunds?store_id={store_a.id}", headers=headers)
    assert res_ref_a.status_code == 200, res_ref_a.text
    refs_a = res_ref_a.json()
    assert len(refs_a) == 1
    assert refs_a[0]["invoice_id"] == inv_a.id

    # 2. Credit Notes filtered by store_id
    res_cn_a = client.get(f"/api/v1/credit-notes?store_id={store_a.id}", headers=headers)
    assert res_cn_a.status_code == 200, res_cn_a.text
    cns_a = res_cn_a.json()
    assert len(cns_a) == 1
    assert cns_a[0]["credit_note_no"] == cn_a.credit_note_no

    # 3. Order Returns filtered by store_id
    res_ret_a = client.get(f"/api/v1/order-returns?store_id={store_a.id}", headers=headers)
    assert res_ret_a.status_code == 200, res_ret_a.text
    rets_a = res_ret_a.json()
    assert len(rets_a) == 1
    assert rets_a[0]["order_id"] == order_a.id

    res_ret_b = client.get(f"/api/v1/order-returns?store_id={store_b.id}", headers=headers)
    assert res_ret_b.status_code == 200, res_ret_b.text
    rets_b = res_ret_b.json()
    assert len(rets_b) == 1
    assert rets_b[0]["order_id"] == order_b.id

    db.close()


def test_area3_payment_reports_and_closure_store_id_filters():
    ctx = setup_multi_store_environment()
    db = ctx["db"]
    headers = ctx["headers"]
    tenant_id = ctx["tenant_id"]
    store_a = ctx["store_a"]
    store_b = ctx["store_b"]
    customer = ctx["customer"]

    order_a = Order(
        tenant_id=tenant_id,
        store_id=store_a.id,
        customer_id=customer.id,
        order_number=f"ORD-PA-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("1500.00"),
        status="confirmed",
    )
    order_b = Order(
        tenant_id=tenant_id,
        store_id=store_b.id,
        customer_id=customer.id,
        order_number=f"ORD-PB-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("2500.00"),
        status="confirmed",
    )
    db.add_all([order_a, order_b])
    db.commit()
    db.refresh(order_a)
    db.refresh(order_b)

    inv_a = Invoice(
        tenant_id=tenant_id,
        store_id=store_a.id,
        order_id=order_a.id,
        invoice_number=f"INV-PA-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("1500.00"),
    )
    inv_b = Invoice(
        tenant_id=tenant_id,
        store_id=store_b.id,
        order_id=order_b.id,
        invoice_number=f"INV-PB-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("2500.00"),
    )
    db.add_all([inv_a, inv_b])

    # Payments
    pmt_a = Payment(
        tenant_id=tenant_id,
        order_id=order_a.id,
        amount=Decimal("1500.00"),
        payment_method="cash",
        status="completed",
    )
    pmt_b = Payment(
        tenant_id=tenant_id,
        order_id=order_b.id,
        amount=Decimal("2500.00"),
        payment_method="upi",
        status="completed",
    )
    db.add_all([pmt_a, pmt_b])
    db.commit()

    # 1. list_payments with store_id
    res_pmt_a = client.get(f"/api/v1/payments?store_id={store_a.id}", headers=headers)
    assert res_pmt_a.status_code == 200, res_pmt_a.text
    pmts_a = res_pmt_a.json()
    assert len(pmts_a) == 1
    assert pmts_a[0]["order_id"] == order_a.id

    # 2. payment_history with store_id
    res_hist_b = client.get(f"/api/v1/payments/history?store_id={store_b.id}", headers=headers)
    assert res_hist_b.status_code == 200, res_hist_b.text
    pmts_b = res_hist_b.json()
    assert len(pmts_b) == 1
    assert pmts_b[0]["order_id"] == order_b.id

    # 3. daily_billing_closure with store_id
    dbc_a = client.get(f"/api/v1/reports/daily-billing?store_id={store_a.id}", headers=headers)
    assert dbc_a.status_code == 200, dbc_a.text
    data_dbc_a = dbc_a.json()
    assert float(data_dbc_a["total_sales"]) == 1500.0

    dbc_b = client.get(f"/api/v1/reports/daily-billing?store_id={store_b.id}", headers=headers)
    assert dbc_b.status_code == 200, dbc_b.text
    data_dbc_b = dbc_b.json()
    assert float(data_dbc_b["total_sales"]) == 2500.0

    # 4. payment_summary with store_id
    today_str = date.today().isoformat()
    ps_a = client.get(f"/api/v1/reports/payment-summary?start_date={today_str}&end_date={today_str}&store_id={store_a.id}", headers=headers)
    assert ps_a.status_code == 200, ps_a.text
    by_method_a = ps_a.json()["payment_breakdown"]
    assert "cash" in by_method_a
    assert "upi" not in by_method_a

    db.close()


def test_area4_procurement_stats_store_id_filters():
    ctx = setup_multi_store_environment()
    db = ctx["db"]
    headers = ctx["headers"]
    tenant_id = ctx["tenant_id"]
    store_a = ctx["store_a"]
    store_b = ctx["store_b"]
    supplier = ctx["supplier"]

    # 1. Purchase Orders
    po_a = PurchaseOrder(
        tenant_id=tenant_id,
        supplier_id=supplier.id,
        store_id=store_a.id,
        order_number=f"PO-A-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("5000.00"),
        status="pending",
    )
    po_b = PurchaseOrder(
        tenant_id=tenant_id,
        supplier_id=supplier.id,
        store_id=store_b.id,
        order_number=f"PO-B-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("8000.00"),
        status="completed",
    )
    db.add_all([po_a, po_b])
    db.commit()

    po_stats_a = client.get(f"/api/v1/purchase-orders/stats?store_id={store_a.id}", headers=headers)
    assert po_stats_a.status_code == 200, po_stats_a.text
    assert po_stats_a.json()["total_orders"] == 1

    # 2. GRNs
    grn_a = GRN(
        tenant_id=tenant_id,
        store_id=store_a.id,
        grn_number=f"GRN-A-{uuid.uuid4().hex[:6]}",
        status="pending",
    )
    grn_b = GRN(
        tenant_id=tenant_id,
        store_id=store_b.id,
        grn_number=f"GRN-B-{uuid.uuid4().hex[:6]}",
        status="received",
    )
    db.add_all([grn_a, grn_b])
    db.commit()

    grn_stats_a = client.get(f"/api/v1/grn/stats?store_id={store_a.id}", headers=headers)
    assert grn_stats_a.status_code == 200, grn_stats_a.text
    assert grn_stats_a.json()["total_grns"] == 1
    assert grn_stats_a.json()["pending_grns"] == 1

    grn_stats_b = client.get(f"/api/v1/grn/stats?store_id={store_b.id}", headers=headers)
    assert grn_stats_b.status_code == 200, grn_stats_b.text
    assert grn_stats_b.json()["total_grns"] == 1
    assert grn_stats_b.json()["received_grns"] == 1

    # 3. PO Returns
    por_a = PurchaseOrderReturn(
        tenant_id=tenant_id,
        purchase_order_id=po_a.id,
        store_id=store_a.id,
        return_number=f"POR-A-{uuid.uuid4().hex[:6]}",
        status="requested",
        total_amount=Decimal("1200.00"),
        reason="Defective stock Pune",
    )
    por_b = PurchaseOrderReturn(
        tenant_id=tenant_id,
        purchase_order_id=po_b.id,
        store_id=store_b.id,
        return_number=f"POR-B-{uuid.uuid4().hex[:6]}",
        status="completed",
        total_amount=Decimal("3400.00"),
        reason="Wrong SKU Mumbai",
    )
    db.add_all([por_a, por_b])
    db.commit()

    por_stats_a = client.get(f"/api/v1/purchase-order-returns/stats?store_id={store_a.id}", headers=headers)
    assert por_stats_a.status_code == 200, por_stats_a.text
    assert por_stats_a.json()["total_returns"] == 1
    assert por_stats_a.json()["requested_count"] == 1
    assert float(por_stats_a.json()["total_debit_amount"]) == 1200.0

    db.close()


def test_area5_analytics_and_ai_predictions_store_id_filters():
    ctx = setup_multi_store_environment()
    db = ctx["db"]
    headers = ctx["headers"]
    tenant_id = ctx["tenant_id"]
    store_a = ctx["store_a"]
    store_b = ctx["store_b"]
    customer = ctx["customer"]
    product_a = ctx["product_a"]
    product_b = ctx["product_b"]

    # Store A order sells 10 of Product A
    order_a = Order(
        tenant_id=tenant_id,
        store_id=store_a.id,
        customer_id=customer.id,
        order_number=f"ORD-AI-A-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("1500.00"),
        status="delivered",
    )
    db.add(order_a)
    db.commit()
    db.refresh(order_a)

    item_a = OrderItem(
        order_id=order_a.id,
        product_id=product_a.id,
        quantity=10,
        unit_price=Decimal("150.00"),
        total_amount=Decimal("1500.00"),
    )
    db.add(item_a)

    # Store B order sells 25 of Product B
    order_b = Order(
        tenant_id=tenant_id,
        store_id=store_b.id,
        customer_id=customer.id,
        order_number=f"ORD-AI-B-{uuid.uuid4().hex[:6]}",
        total_amount=Decimal("3000.00"),
        status="delivered",
    )
    db.add(order_b)
    db.commit()
    db.refresh(order_b)

    item_b = OrderItem(
        order_id=order_b.id,
        product_id=product_b.id,
        quantity=25,
        unit_price=Decimal("120.00"),
        total_amount=Decimal("3000.00"),
    )
    db.add(item_b)
    db.commit()

    # 1. Product performance analytics filtered by store_id
    perf_a = client.get(f"/api/v1/analytics/products?store_id={store_a.id}", headers=headers)
    assert perf_a.status_code == 200, perf_a.text
    rows_a = perf_a.json()
    assert len(rows_a) == 1
    assert rows_a[0]["product_id"] == product_a.id
    assert rows_a[0]["quantity_sold"] == 10

    # 2. AI Best Sellers filtered by store_id
    bs_b = client.get(f"/api/v1/ai/best-sellers?store_id={store_b.id}", headers=headers)
    assert bs_b.status_code == 200, bs_b.text
    b_rows = bs_b.json()
    assert len(b_rows) == 1
    assert b_rows[0]["product_id"] == product_b.id
    assert b_rows[0]["quantity_sold"] == 25

    # 3. AI Demand Forecast filtered by store_id
    df_a = client.get(f"/api/v1/ai/demand-forecast/{product_a.id}?store_id={store_a.id}", headers=headers)
    assert df_a.status_code == 200, df_a.text
    assert df_a.json()["total_sold"] == 10

    # Demand for Product A in Store B should be 0
    df_a_in_b = client.get(f"/api/v1/ai/demand-forecast/{product_a.id}?store_id={store_b.id}", headers=headers)
    assert df_a_in_b.status_code == 200, df_a_in_b.text
    assert df_a_in_b.json()["total_sold"] == 0

    db.close()


def test_area6_pos_active_shift_store_id_filter():
    ctx = setup_multi_store_environment()
    db = ctx["db"]
    headers = ctx["headers"]
    tenant_id = ctx["tenant_id"]
    store_a = ctx["store_a"]
    store_b = ctx["store_b"]
    user = ctx["user"]

    shift_a = POSShift(
        tenant_id=tenant_id,
        store_id=store_a.id,
        cashier_id=user.id,
        status="open",
        opening_cash_float=Decimal("1000.00"),
        opened_at=datetime.utcnow() - timedelta(hours=2),
    )
    shift_b = POSShift(
        tenant_id=tenant_id,
        store_id=store_b.id,
        cashier_id=user.id,
        status="open",
        opening_cash_float=Decimal("5000.00"),
        opened_at=datetime.utcnow() - timedelta(hours=1),
    )
    db.add_all([shift_a, shift_b])
    db.commit()

    # User query with store_id=store_a.id
    res_a = client.get(f"/api/v1/pos/shifts/current?store_id={store_a.id}", headers=headers)
    assert res_a.status_code == 200, res_a.text
    assert res_a.json()["store_id"] == store_a.id
    assert float(res_a.json()["opening_cash_float"]) == 1000.0

    # User query with store_id=store_b.id
    res_b = client.get(f"/api/v1/pos/shifts/current?store_id={store_b.id}", headers=headers)
    assert res_b.status_code == 200, res_b.text
    assert res_b.json()["store_id"] == store_b.id
    assert float(res_b.json()["opening_cash_float"]) == 5000.0

    db.close()
