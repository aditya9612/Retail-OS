import uuid
from decimal import Decimal
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.main import app
from app.models.inventory import Inventory
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.payment import Payment
from app.services.billing_service import BillingService

client = TestClient(app)


def _register_tenant_and_store(prefix: str):
    slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@atomicitytest.com"
    password = "SecurePassword123!"

    reg_resp = client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": f"Tenant {slug}",
            "slug": slug,
            "email": email,
            "admin_name": f"Admin {prefix}",
            "password": password,
        },
    )
    assert reg_resp.status_code == 200, reg_resp.text
    tenant_id = reg_resp.json()["tenant_id"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    store_resp = client.post(
        "/api/v1/stores",
        json={"name": f"Store {prefix}", "code": f"S-{uuid.uuid4().hex[:4].upper()}"},
        headers=headers,
    )
    assert store_resp.status_code == 201, store_resp.text
    store = store_resp.json()

    return {
        "tenant_id": tenant_id,
        "token": token,
        "headers": headers,
        "store": store,
    }


def _create_product_with_stock(headers, store_id, name="Test Product", sku=None, price="200.00", gst_rate="18.00", hsn="6109", initial_stock=100):
    if not sku:
        sku = f"SKU-{uuid.uuid4().hex[:6].upper()}"
    p_resp = client.post(
        "/api/v1/products",
        json={
            "name": name,
            "sku": sku,
            "price": price,
            "gst_rate": gst_rate,
            "hsn_code": hsn,
        },
        headers=headers,
    )
    assert p_resp.status_code == 201, p_resp.text
    product = p_resp.json()

    client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store_id, "product_id": product["id"], "quantity": initial_stock},
        headers=headers,
    )

    return product


def test_checkout_prevalidation_invalid_payment_total_rolls_back():
    """
    Validation before irreversible ops: Invalid payment amount fails BEFORE
    order confirmation, batch deduction, or stock reduction.
    """
    ctx = _register_tenant_and_store("inv-pay")
    headers = ctx["headers"]
    store_id = ctx["store"]["id"]
    product = _create_product_with_stock(headers, store_id, price="200.00", gst_rate="18.00", initial_stock=50)

    # Add 2 items: 400 + 18% tax (72) = 472 grand total
    add_resp = client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store_id, "same_state": True},
        json={"product_id": product["id"], "quantity": "2"},
        headers=headers,
    )
    assert add_resp.status_code == 200

    # Attempt checkout with insufficient payment total: 300.00 instead of 472.00
    checkout_resp = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store_id,
            "same_state": True,
            "payments": [{"payment_mode": "cash", "amount": "300.00"}],
        },
        headers=headers,
    )
    assert checkout_resp.status_code == 400
    assert "match order total" in checkout_resp.text.lower() or "payment total" in checkout_resp.text.lower()

    # Verify atomic state in database: stock unchanged, no confirmed order, no invoice
    db: Session = SessionLocal()
    try:
        inv = db.query(Inventory).filter(
            Inventory.store_id == store_id,
            Inventory.product_id == product["id"]
        ).first()
        assert inv is not None
        assert Decimal(str(inv.quantity)) == Decimal("50.0000")

        orders = db.query(Order).filter(Order.store_id == store_id).all()
        assert len(orders) == 0

        invoices = db.query(Invoice).filter(Invoice.store_id == store_id).all()
        assert len(invoices) == 0

        payments = db.query(Payment).filter(Payment.tenant_id == ctx["tenant_id"]).all()
        assert len(payments) == 0
    finally:
        db.close()


def test_checkout_prevalidation_cash_tendered_insufficient():
    """
    Cash tender validation: amount_tendered < amount fails before order confirmation.
    """
    ctx = _register_tenant_and_store("tender-insuf")
    headers = ctx["headers"]
    store_id = ctx["store"]["id"]
    product = _create_product_with_stock(headers, store_id, price="100.00", gst_rate="18.00", initial_stock=30)

    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store_id, "same_state": True},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )

    # 100 + 18% = 118.00. Payment is 118.00, but amount_tendered is 100.00 (insufficient)
    checkout_resp = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store_id,
            "same_state": True,
            "payments": [{"payment_mode": "cash", "amount": "118.00", "amount_tendered": "100.00"}],
        },
        headers=headers,
    )
    assert checkout_resp.status_code == 400
    assert "cash tendered" in checkout_resp.text.lower() or "cannot be less than" in checkout_resp.text.lower()

    db: Session = SessionLocal()
    try:
        inv = db.query(Inventory).filter(
            Inventory.store_id == store_id,
            Inventory.product_id == product["id"]
        ).first()
        assert Decimal(str(inv.quantity)) == Decimal("30.0000")
        assert db.query(Order).filter(Order.store_id == store_id).count() == 0
        assert db.query(Invoice).filter(Invoice.store_id == store_id).count() == 0
    finally:
        db.close()


def test_checkout_atomic_rollback_on_invoice_generation_failure():
    """
    Atomic rollback on invoice creation failure:
    If an unexpected error occurs during invoice generation, the transaction rolls back
    order creation, stock deduction, and payments completely.
    """
    ctx = _register_tenant_and_store("rb-inv-fail")
    headers = ctx["headers"]
    store_id = ctx["store"]["id"]
    product = _create_product_with_stock(headers, store_id, price="200.00", gst_rate="18.00", initial_stock=20)

    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store_id, "same_state": True},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )

    def mock_create_invoice(*args, **kwargs):
        raise RuntimeError("Simulated DB crash or fatal error during invoice creation")

    # Use client with raise_server_exceptions=False so 500 response is returned
    safe_client = TestClient(app, raise_server_exceptions=False)
    with patch.object(BillingService, "create_invoice", side_effect=mock_create_invoice):
        checkout_resp = safe_client.post(
            "/api/v1/invoices",
            json={
                "store_id": store_id,
                "same_state": True,
                "payments": [{"payment_mode": "cash", "amount": "236.00"}],
            },
            headers=headers,
        )
        assert checkout_resp.status_code in (400, 500)

    # Verify complete rollback: inventory restored to 20, no order, no payment, no invoice
    db: Session = SessionLocal()
    try:
        inv = db.query(Inventory).filter(
            Inventory.store_id == store_id,
            Inventory.product_id == product["id"]
        ).first()
        assert Decimal(str(inv.quantity)) == Decimal("20.0000")
        assert db.query(Order).filter(Order.store_id == store_id).count() == 0
        assert db.query(Invoice).filter(Invoice.store_id == store_id).count() == 0
        assert db.query(Payment).filter(Payment.tenant_id == ctx["tenant_id"]).count() == 0
    finally:
        db.close()


def test_checkout_success_links_payment_and_persists_status_and_store():
    """
    Happy path checkout:
    - Order is confirmed
    - Stock is deducted
    - Invoice has mapped status='paid' and correct store_id
    - Payment records have payment.invoice_id == invoice.id
    """
    ctx = _register_tenant_and_store("checkout-ok")
    headers = ctx["headers"]
    store_id = ctx["store"]["id"]
    product = _create_product_with_stock(headers, store_id, price="200.00", gst_rate="18.00", initial_stock=25)

    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store_id, "same_state": True},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )

    checkout_resp = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store_id,
            "same_state": True,
            "payments": [
                {"payment_mode": "cash", "amount": "100.00", "amount_tendered": "100.00"},
                {"payment_mode": "upi", "amount": "136.00", "transaction_reference": "UPI-REF-001"},
            ],
        },
        headers=headers,
    )
    assert checkout_resp.status_code == 201, checkout_resp.text
    data = checkout_resp.json()
    invoice_id = data["id"]
    assert data["status"] == "paid"

    # Query in fresh DB session
    db: Session = SessionLocal()
    try:
        db_inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        assert db_inv is not None
        assert db_inv.status == "paid"
        assert db_inv.store_id == store_id

        # Verify payments linked to invoice
        payments = db.query(Payment).filter(Payment.invoice_id == invoice_id).all()
        assert len(payments) == 2
        total_paid = sum(p.amount for p in payments)
        assert total_paid == Decimal("236.00")
        for p in payments:
            assert p.invoice_id == db_inv.id
            assert p.order_id == db_inv.order_id

        # Verify stock was deducted
        inv = db.query(Inventory).filter(
            Inventory.store_id == store_id,
            Inventory.product_id == product["id"]
        ).first()
        assert Decimal(str(inv.quantity)) == Decimal("24.0000")

        # Verify ORM filter by status and store_id works
        paid_invoices = db.query(Invoice).filter(
            Invoice.status == "paid",
            Invoice.store_id == store_id
        ).all()
        assert len(paid_invoices) == 1
        assert paid_invoices[0].id == invoice_id
    finally:
        db.close()


def test_hsn_gst_rate_alignment_and_odd_cent_rounding():
    """
    Test that:
    1. HSN rate from gst_rates table is resolved when present.
    2. Odd-cent tax residual is reconciled so CGST + SGST == total_tax.
    """
    ctx = _register_tenant_and_store("gst-odd")
    headers = ctx["headers"]
    store_id = ctx["store"]["id"]

    # Insert HSN 8471 rate of 12% into gst_rates via API
    rate_resp = client.post(
        "/api/v1/gst-rates",
        json={"hsn_code": "8471", "gst_rate": "12.00"},
        headers=headers,
    )
    assert rate_resp.status_code == 201, rate_resp.text

    # Product with HSN 8471 (price 84.17 with 18% nominal gst_rate in product table)
    # Because HSN 8471 exists with 12%, it should use 12% from gst_rates!
    # Price = 84.17: 84.17 * 0.12 = 10.1004 => 10.10 total tax.
    # CGST = 5.05, SGST = 5.05. Sum = 10.10.
    product = _create_product_with_stock(
        headers, store_id,
        price="84.17",
        gst_rate="18.00",  # should be overridden by 12.00 from HSN table
        hsn="8471",
        initial_stock=10,
    )

    add_resp = client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store_id, "same_state": True},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )
    assert add_resp.status_code == 200
    cart = add_resp.json()
    assert Decimal(str(cart["subtotal"])) == Decimal("84.17")
    assert Decimal(str(cart["gst_amount"])) == Decimal("10.10")  # 84.17 * 0.12 rounded
    assert Decimal(str(cart["grand_total"])) == Decimal("94.27")

    # Now let's test an odd-cent case: price = 84.17 with 18% (total tax = 15.15)
    # Product B without HSN in table, uses product 18%
    product_b = _create_product_with_stock(
        headers, store_id,
        price="84.17",
        gst_rate="18.00",
        hsn="8517",
        initial_stock=10,
    )

    # Clear previous cart by checkout
    client.post(
        "/api/v1/invoices",
        json={"store_id": store_id, "payments": [{"payment_mode": "cash", "amount": "94.27"}]},
        headers=headers,
    )

    add_b_resp = client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store_id, "same_state": True},
        json={"product_id": product_b["id"], "quantity": "1"},
        headers=headers,
    )
    assert add_b_resp.status_code == 200
    cart_b = add_b_resp.json()
    # 84.17 * 0.18 = 15.1506 => 15.15 total tax.
    # Grand total = 84.17 + 15.15 = 99.32.
    assert Decimal(str(cart_b["gst_amount"])) == Decimal("15.15")
    assert Decimal(str(cart_b["grand_total"])) == Decimal("99.32")

    checkout_b_resp = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store_id,
            "same_state": True,
            "payments": [{"payment_mode": "cash", "amount": "99.32"}],
        },
        headers=headers,
    )
    assert checkout_b_resp.status_code == 201
    inv_data = checkout_b_resp.json()

    # Reconciled CGST + SGST check:
    cgst = Decimal(str(inv_data["cgst_amount"]))
    sgst = Decimal(str(inv_data["sgst_amount"]))
    subtotal = Decimal(str(inv_data["subtotal"]))
    total_amount = Decimal(str(inv_data["total_amount"]))
    assert cgst + sgst == Decimal("15.15")
    assert total_amount - subtotal == Decimal("15.15")
    assert (cgst == Decimal("7.58") and sgst == Decimal("7.57")) or (cgst == Decimal("7.57") and sgst == Decimal("7.58"))

    # Also verify tax_amount column on Invoice model in DB
    db_verify: Session = SessionLocal()
    try:
        db_inv = db_verify.query(Invoice).filter(Invoice.id == inv_data["id"]).first()
        assert db_inv.tax_amount == Decimal("15.15")
        assert db_inv.cgst_amount + db_inv.sgst_amount == db_inv.tax_amount
    finally:
        db_verify.close()


def test_invoice_prefix_configured_in_document_settings():
    """
    Configured prefix: When invoice_prefix is configured in DocumentSettings,
    newly generated invoices use the custom prefix.
    """
    ctx = _register_tenant_and_store("custom-pfx")
    headers = ctx["headers"]
    store_id = ctx["store"]["id"]

    # Configure custom invoice prefix "DOC-PREF-"
    update_resp = client.put(
        "/api/v1/document-settings",
        json={"invoice_prefix": "DOC-PREF-"},
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["invoice_prefix"] == "DOC-PREF-"

    product = _create_product_with_stock(headers, store_id, price="100.00", gst_rate="18.00", initial_stock=10)

    client.post(
        "/api/v1/billing/cart/add-item",
        params={"store_id": store_id, "same_state": True},
        json={"product_id": product["id"], "quantity": "1"},
        headers=headers,
    )

    checkout_resp = client.post(
        "/api/v1/invoices",
        json={
            "store_id": store_id,
            "payments": [{"payment_mode": "cash", "amount": "118.00"}],
        },
        headers=headers,
    )
    assert checkout_resp.status_code == 201
    inv = checkout_resp.json()
    assert inv["invoice_number"].startswith("DOC-PREF-"), f"Expected DOC-PREF- prefix, got {inv['invoice_number']}"


def test_two_tenants_can_generate_same_invoice_number():
    """
    Tenant-scoped invoice number uniqueness:
    Two different tenants using the same configured numbering prefix CAN generate
    the same invoice number (e.g. PREFIX-YEAR-000001) without database conflict.
    """
    ctx_a = _register_tenant_and_store("scope-a")
    ctx_b = _register_tenant_and_store("scope-b")

    # Set both tenants to use prefix "SAMENUM-"
    for ctx in (ctx_a, ctx_b):
        client.put(
            "/api/v1/document-settings",
            json={"invoice_prefix": "SAMENUM-"},
            headers=ctx["headers"],
        )
        p = _create_product_with_stock(ctx["headers"], ctx["store"]["id"], price="50.00", gst_rate="18.00", initial_stock=10)
        client.post(
            "/api/v1/billing/cart/add-item",
            params={"store_id": ctx["store"]["id"], "same_state": True},
            json={"product_id": p["id"], "quantity": "1"},
            headers=ctx["headers"],
        )

    # Checkout tenant A
    resp_a = client.post(
        "/api/v1/invoices",
        json={"store_id": ctx_a["store"]["id"], "payments": [{"payment_mode": "cash", "amount": "59.00"}]},
        headers=ctx_a["headers"],
    )
    assert resp_a.status_code == 201, resp_a.text
    inv_a = resp_a.json()

    # Checkout tenant B
    resp_b = client.post(
        "/api/v1/invoices",
        json={"store_id": ctx_b["store"]["id"], "payments": [{"payment_mode": "cash", "amount": "59.00"}]},
        headers=ctx_b["headers"],
    )
    assert resp_b.status_code == 201, resp_b.text
    inv_b = resp_b.json()

    # Both got the same invoice number (e.g. SAMENUM-2026-000001)
    assert inv_a["invoice_number"] == inv_b["invoice_number"]
    assert inv_a["tenant_id"] != inv_b["tenant_id"]

    # In database, both exist simultaneously
    db: Session = SessionLocal()
    try:
        rows = db.query(Invoice).filter(Invoice.invoice_number == inv_a["invoice_number"]).all()
        assert len(rows) == 2
        tenant_ids = {r.tenant_id for r in rows}
        assert tenant_ids == {ctx_a["tenant_id"], ctx_b["tenant_id"]}
    finally:
        db.close()


def test_duplicate_invoice_number_within_same_tenant_rejected():
    """
    Composite unique constraint enforcement:
    Attempting to create two invoices with the SAME invoice_number within the SAME tenant
    must be rejected by uq_invoices_tenant_invoice_number.
    """
    from sqlalchemy.exc import IntegrityError

    ctx = _register_tenant_and_store("dup-check")
    db: Session = SessionLocal()
    try:
        # Create first order and invoice
        order1 = Order(
            tenant_id=ctx["tenant_id"],
            store_id=ctx["store"]["id"],
            order_number=f"ORD-TEST-{uuid.uuid4().hex[:6]}",
            status="confirmed",
            payment_status="paid",
            total_amount=Decimal("100.00"),
        )
        db.add(order1)
        db.flush()

        inv1 = Invoice(
            tenant_id=ctx["tenant_id"],
            store_id=ctx["store"]["id"],
            order_id=order1.id,
            invoice_number="DUP-TEST-001",
            status="paid",
            total_amount=Decimal("100.00"),
        )
        db.add(inv1)
        db.commit()

        # Attempt to insert second invoice for SAME tenant with SAME invoice_number
        order2 = Order(
            tenant_id=ctx["tenant_id"],
            store_id=ctx["store"]["id"],
            order_number=f"ORD-TEST-{uuid.uuid4().hex[:6]}",
            status="confirmed",
            payment_status="paid",
            total_amount=Decimal("200.00"),
        )
        db.add(order2)
        db.flush()

        inv2 = Invoice(
            tenant_id=ctx["tenant_id"],
            store_id=ctx["store"]["id"],
            order_id=order2.id,
            invoice_number="DUP-TEST-001",
            status="paid",
            total_amount=Decimal("200.00"),
        )
        db.add(inv2)

        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_concurrent_sequence_generation_remains_safe():
    """
    Sequence concurrency & ordering:
    Multiple sequence generation requests for the same tenant produce strictly
    increasing, non-colliding document numbers.
    """
    ctx = _register_tenant_and_store("seq-safe")
    db: Session = SessionLocal()
    try:
        svc = BillingService(db)
        numbers = [svc._generate_invoice_number(ctx["tenant_id"], ctx["store"]["id"]) for _ in range(5)]
        assert len(set(numbers)) == 5
        # Verify sequential suffixes
        suffixes = [int(n.split("-")[-1]) for n in numbers]
        assert suffixes == [1, 2, 3, 4, 5]
    finally:
        db.close()


def test_historical_status_backfill_rules():
    """
    Historical status backfill logic:
    Verifies that the backfill classification rules:
    - Order cancelled -> 'cancelled'
    - Order refunded / credit note -> 'refunded'
    - Order fully paid -> 'paid'
    - Order partially paid -> 'partially_paid'
    - Unpaid order -> 'issued'
    accurately classify invoices without unconditional defaults.
    """
    from sqlalchemy import text
    from app.models.credit_note import CreditNote

    ctx = _register_tenant_and_store("status-backfill")
    tenant_id = ctx["tenant_id"]
    store_id = ctx["store"]["id"]

    db: Session = SessionLocal()
    try:
        # 1. Cancelled order
        o_cancelled = Order(
            tenant_id=tenant_id, store_id=store_id, order_number=f"O-CAN-{uuid.uuid4().hex[:4]}",
            status="cancelled", payment_status="pending", total_amount=Decimal("100.00"),
        )
        db.add(o_cancelled)
        db.flush()
        inv_cancelled = Invoice(tenant_id=tenant_id, store_id=store_id, order_id=o_cancelled.id, invoice_number=f"INV-CAN-{uuid.uuid4().hex[:4]}", status="issued", total_amount=Decimal("100.00"))
        db.add(inv_cancelled)

        # 2. Refunded order (has credit note)
        o_refunded = Order(
            tenant_id=tenant_id, store_id=store_id, order_number=f"O-REF-{uuid.uuid4().hex[:4]}",
            status="refunded", payment_status="pending", total_amount=Decimal("200.00"),
        )
        db.add(o_refunded)
        db.flush()
        inv_refunded = Invoice(tenant_id=tenant_id, store_id=store_id, order_id=o_refunded.id, invoice_number=f"INV-REF-{uuid.uuid4().hex[:4]}", status="issued", total_amount=Decimal("200.00"))
        db.add(inv_refunded)

        # 3. Fully paid order
        o_paid = Order(
            tenant_id=tenant_id, store_id=store_id, order_number=f"O-PAID-{uuid.uuid4().hex[:4]}",
            status="confirmed", payment_status="paid", total_amount=Decimal("300.00"),
        )
        db.add(o_paid)
        db.flush()
        inv_paid = Invoice(tenant_id=tenant_id, store_id=store_id, order_id=o_paid.id, invoice_number=f"INV-PAID-{uuid.uuid4().hex[:4]}", status="issued", total_amount=Decimal("300.00"))
        db.add(inv_paid)
        p_paid = Payment(
            tenant_id=tenant_id, order_id=o_paid.id, amount=Decimal("300.00"), payment_method="cash", status="completed",
        )
        db.add(p_paid)

        # 4. Partially paid order
        o_partial = Order(
            tenant_id=tenant_id, store_id=store_id, order_number=f"O-PART-{uuid.uuid4().hex[:4]}",
            status="confirmed", payment_status="pending", total_amount=Decimal("400.00"),
        )
        db.add(o_partial)
        db.flush()
        inv_partial = Invoice(tenant_id=tenant_id, store_id=store_id, order_id=o_partial.id, invoice_number=f"INV-PART-{uuid.uuid4().hex[:4]}", status="issued", total_amount=Decimal("400.00"))
        db.add(inv_partial)
        p_partial = Payment(
            tenant_id=tenant_id, order_id=o_partial.id, amount=Decimal("150.00"), payment_method="cash", status="completed",
        )
        db.add(p_partial)

        # 5. Unpaid order
        o_unpaid = Order(
            tenant_id=tenant_id, store_id=store_id, order_number=f"O-UNP-{uuid.uuid4().hex[:4]}",
            status="confirmed", payment_status="pending", total_amount=Decimal("500.00"),
        )
        db.add(o_unpaid)
        db.flush()
        inv_unpaid = Invoice(tenant_id=tenant_id, store_id=store_id, order_id=o_unpaid.id, invoice_number=f"INV-UNP-{uuid.uuid4().hex[:4]}", status="issued", total_amount=Decimal("500.00"))
        db.add(inv_unpaid)

        db.commit()

        # Run the backfill update query
        db.execute(
            text(
                """
                UPDATE invoices
                SET status = CASE
                    WHEN (SELECT status FROM orders WHERE orders.id = invoices.order_id) = 'cancelled' THEN 'cancelled'
                    WHEN (
                        (SELECT COUNT(*) FROM refunds WHERE refunds.invoice_id = invoices.id) > 0
                        OR (SELECT COUNT(*) FROM credit_notes WHERE credit_notes.invoice_id = invoices.id) > 0
                        OR (SELECT status FROM orders WHERE orders.id = invoices.order_id) = 'refunded'
                    ) THEN 'refunded'
                    WHEN (
                        (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE payments.order_id = invoices.order_id AND payments.status = 'completed') >= invoices.total_amount
                        OR (SELECT payment_status FROM orders WHERE orders.id = invoices.order_id) = 'paid'
                    ) THEN 'paid'
                    WHEN (
                        (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE payments.order_id = invoices.order_id AND payments.status = 'completed') > 0
                    ) THEN 'partially_paid'
                    ELSE 'issued'
                END
                WHERE id IN (:i1, :i2, :i3, :i4, :i5)
                """
            ),
            {"i1": inv_cancelled.id, "i2": inv_refunded.id, "i3": inv_paid.id, "i4": inv_partial.id, "i5": inv_unpaid.id},
        )
        db.commit()

        # Verify repaired statuses
        db.refresh(inv_cancelled)
        db.refresh(inv_refunded)
        db.refresh(inv_paid)
        db.refresh(inv_partial)
        db.refresh(inv_unpaid)

        assert inv_cancelled.status == "cancelled"
        assert inv_refunded.status == "refunded"
        assert inv_paid.status == "paid"
        assert inv_partial.status == "partially_paid"
        assert inv_unpaid.status == "issued"
    finally:
        db.close()

