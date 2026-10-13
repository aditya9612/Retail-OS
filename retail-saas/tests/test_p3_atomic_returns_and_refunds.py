import threading
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.exceptions import AppException, ForbiddenException, NotFoundException
from app.models.credit_note import CreditNote
from app.models.inventory import Inventory, StockMovement
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.invoice_item_return import InvoiceItemReturn
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_item_batch_allocation import OrderItemBatchAllocation
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.refund import Refund
from app.models.role import Role
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User
from app.services.billing_service import BillingService
from app.utils.constants import OrderStatus, PaymentStatus, RefundStatus, StockMovementType


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def make_tenant(db, name="P3 Tenant"):
    tenant = Tenant(name=name, domain=f"p3-{uuid.uuid4().hex[:8]}.com")
    db.add(tenant)
    db.flush()
    return tenant


def make_store(db, tenant_id, name="P3 Store"):
    store = Store(tenant_id=tenant_id, name=name, code=f"P3S-{uuid.uuid4().hex[:6]}")
    db.add(store)
    db.flush()
    return store


def make_user(db, tenant_id, store_id=None, role_name="owner"):
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        role = Role(name=role_name, permissions=["*"] if role_name in ("owner", "admin") else ["billing:read", "billing:write", "billing:refund"])
        db.add(role)
        db.flush()

    user = User(
        tenant_id=tenant_id,
        store_id=store_id,
        role_id=role.id,
        full_name="Test User",
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="testpasshash",
        phone=f"98{uuid.uuid4().int % 100000000:08d}",
    )
    user.role = role
    db.add(user)
    db.flush()
    return user


def make_product(db, tenant_id, name="P3 Product", track_batch=True, price=Decimal("100.00")):
    prod = Product(
        tenant_id=tenant_id,
        name=name,
        sku=f"P3-{uuid.uuid4().hex[:8]}",
        selling_price=price,
        cost_price=Decimal("50.00"),
        gst_rate=Decimal("18.00"),
        hsn_code="1234",
    )
    prod.track_batch = track_batch
    db.add(prod)
    db.flush()
    return prod


def make_batch(db, tenant_id, store_id, product_id, batch_num, quantity=Decimal("100.0000"), expiry_date=None):
    b = ProductBatch(
        tenant_id=tenant_id,
        store_id=store_id,
        product_id=product_id,
        batch_number=batch_num,
        quantity=quantity,
        remaining_quantity=quantity,
        unit_cost=Decimal("50.0000"),
        expiry_date=expiry_date,
        is_active=True,
    )
    db.add(b)
    db.flush()

    inv = Inventory(
        tenant_id=tenant_id,
        store_id=store_id,
        product_id=product_id,
        batch_id=b.id,
        quantity=quantity,
    )
    db.add(inv)

    agg = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.store_id == store_id,
        Inventory.product_id == product_id,
        Inventory.batch_id.is_(None),
    ).first()
    if not agg:
        agg = Inventory(
            tenant_id=tenant_id,
            store_id=store_id,
            product_id=product_id,
            batch_id=None,
            quantity=quantity,
        )
        db.add(agg)
    else:
        agg.quantity += quantity
    db.flush()
    return b


def create_test_sale(db, tenant_id, store_id, product, qty=Decimal("10"), batch=None, batches=None):
    user = make_user(db, tenant_id, store_id=store_id)
    order = Order(
        tenant_id=tenant_id,
        store_id=store_id,
        user_id=user.id,
        order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        order_type="pos",
        status=OrderStatus.CONFIRMED.value,
    )
    db.add(order)
    db.flush()

    line_total = product.selling_price * qty
    line_gst = (line_total * Decimal("0.18")).quantize(Decimal("0.01"))
    order_item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        product_name=product.name,
        sku=product.sku,
        quantity=int(qty),
        unit_price=product.selling_price,
        discount_amount=Decimal("0.00"),
        tax_amount=line_gst,
        total_amount=line_total + line_gst,
        cgst_amount=(line_gst / 2).quantize(Decimal("0.01")),
        sgst_amount=(line_gst / 2).quantize(Decimal("0.01")),
    )
    db.add(order_item)
    db.flush()

    if batches:
        for b_obj, b_qty in batches:
            alloc = OrderItemBatchAllocation(
                order_item_id=order_item.id,
                batch_id=b_obj.id,
                quantity=b_qty,
                unit_cost=b_obj.unit_cost,
                returned_quantity=Decimal("0.0000"),
            )
            db.add(alloc)
            b_obj.remaining_quantity -= b_qty
            inv_row = db.query(Inventory).filter(Inventory.batch_id == b_obj.id).first()
            if inv_row:
                inv_row.quantity -= b_qty
            agg = db.query(Inventory).filter(
                Inventory.tenant_id == tenant_id,
                Inventory.store_id == store_id,
                Inventory.product_id == product.id,
                Inventory.batch_id.is_(None),
            ).first()
            if agg:
                agg.quantity -= b_qty
    elif batch:
        alloc = OrderItemBatchAllocation(
            order_item_id=order_item.id,
            batch_id=batch.id,
            quantity=qty,
            unit_cost=batch.unit_cost,
            returned_quantity=Decimal("0.0000"),
        )
        db.add(alloc)
        batch.remaining_quantity -= qty
        inv_row = db.query(Inventory).filter(Inventory.batch_id == batch.id).first()
        if inv_row:
            inv_row.quantity -= qty
        agg = db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.store_id == store_id,
            Inventory.product_id == product.id,
            Inventory.batch_id.is_(None),
        ).first()
        if agg:
            agg.quantity -= qty
    else:
        # non-batch
        agg = db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.store_id == store_id,
            Inventory.product_id == product.id,
            Inventory.batch_id.is_(None),
        ).first()
        if agg:
            agg.quantity -= qty

    invoice = Invoice(
        tenant_id=tenant_id,
        store_id=store_id,
        order_id=order.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:8].upper()}",
        status="paid",
        subtotal=line_total,
        discount_amount=Decimal("0.00"),
        tax_amount=line_gst,
        cgst_amount=(line_gst / 2).quantize(Decimal("0.01")),
        sgst_amount=(line_gst / 2).quantize(Decimal("0.01")),
        igst_amount=Decimal("0.00"),
        total_amount=line_total + line_gst,
    )
    db.add(invoice)
    db.flush()

    inv_item = InvoiceItem(
        invoice_id=invoice.id,
        product_id=product.id,
        quantity=qty,
        unit_price=product.selling_price,
        discount_amount=Decimal("0.00"),
        gst_rate=Decimal("18.00"),
        gst_amount=line_gst,
        total_amount=line_total + line_gst,
        returned_quantity=Decimal("0.00"),
    )
    db.add(inv_item)

    payment = Payment(
        tenant_id=tenant_id,
        order_id=order.id,
        invoice_id=invoice.id,
        payment_method="cash",
        amount=invoice.total_amount,
        status=PaymentStatus.COMPLETED.value,
        paid_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()

    return user, order, invoice, inv_item


# ==============================================================================
# TEST 1: Full Return Restores Inventory & Updates Status
# ==============================================================================
def test_full_return_restores_inventory_and_marks_invoice_refunded(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-001", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("10"), batch=batch)
    assert batch.remaining_quantity == Decimal("40")

    service = BillingService(db)
    result = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("10"),
        reason="Full return test",
        user=user,
        condition="sellable",
    )

    assert result["status"] == "return_processed"
    assert result["returned_quantity_total"] == Decimal("10")
    assert result["remaining_returnable_quantity"] == Decimal("0")

    db.refresh(invoice)
    db.refresh(order)
    db.refresh(batch)
    assert invoice.status == "refunded"
    assert order.status == OrderStatus.RETURNED.value
    assert batch.remaining_quantity == Decimal("50")


# ==============================================================================
# TEST 2: Partial Return Tracks Cumulative Quantity
# ==============================================================================
def test_partial_return_tracks_cumulative_quantity(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-002", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("10"), batch=batch)

    service = BillingService(db)
    # First return 4
    res1 = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("4"),
        user=user,
    )
    assert res1["returned_quantity_total"] == Decimal("4")
    assert res1["remaining_returnable_quantity"] == Decimal("6")

    # Second return 3
    res2 = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("3"),
        user=user,
    )
    assert res2["returned_quantity_total"] == Decimal("7")
    assert res2["remaining_returnable_quantity"] == Decimal("3")

    db.refresh(batch)
    assert batch.remaining_quantity == Decimal("47")  # 40 + 4 + 3


# ==============================================================================
# TEST 3: Repeated Duplicate Return Rejected
# ==============================================================================
def test_repeated_duplicate_return_rejected(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-003", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("5"), batch=batch)

    service = BillingService(db)
    service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("5"),
        user=user,
    )

    with pytest.raises(AppException) as exc:
        service.process_return(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            product_id=product.id,
            return_quantity=Decimal("1"),
            user=user,
        )
    assert "exceeds remaining returnable quantity" in str(exc.value).lower()


# ==============================================================================
# TEST 4: Return Quantity Exceeding Sold Quantity Rejected
# ==============================================================================
def test_return_quantity_exceeding_sold_quantity_rejected(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-004", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("5"), batch=batch)

    service = BillingService(db)
    with pytest.raises(AppException) as exc:
        service.process_return(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            product_id=product.id,
            return_quantity=Decimal("6"),
            user=user,
        )
    assert "exceeds remaining returnable quantity" in str(exc.value).lower()


# ==============================================================================
# TEST 5: Two Concurrent Returns Against the Same Sold Units
# ==============================================================================
def test_concurrent_returns_against_same_sold_units(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-005", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("4"), batch=batch)

    results = []
    errors = []

    def attempt_return(qty):
        s = SessionLocal()
        try:
            srv = BillingService(s)
            u = s.get(User, user.id)
            res = srv.process_return(
                tenant_id=tenant.id,
                invoice_id=invoice.id,
                product_id=product.id,
                return_quantity=Decimal(str(qty)),
                user=u,
            )
            results.append(res)
        except Exception as e:
            errors.append(e)
        finally:
            s.close()

    # Both threads try to return 3 units out of 4 sold
    t1 = threading.Thread(target=attempt_return, args=(3,))
    t2 = threading.Thread(target=attempt_return, args=(3,))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one must succeed, one must fail with remaining returnable exceeded
    assert len(results) == 1
    assert len(errors) == 1
    assert "exceeds remaining returnable quantity" in str(errors[0]).lower()

    verify_s = SessionLocal()
    try:
        final_item = verify_s.get(InvoiceItem, inv_item.id)
        assert final_item.returned_quantity == Decimal("3.00")
    finally:
        verify_s.close()


# ==============================================================================
# TEST 6: Batch-Managed Item Restoration (Invariants Preserved)
# ==============================================================================
def test_batch_managed_item_restoration(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-006", quantity=Decimal("100"))

    original_batch_qty = batch.quantity
    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("20"), batch=batch)

    service = BillingService(db)
    res = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("20"),
        user=user,
        condition="sellable",
    )

    db.refresh(batch)
    # INVARIANT: batch.quantity is NEVER changed
    assert batch.quantity == original_batch_qty
    # remaining_quantity restored exactly
    assert batch.remaining_quantity == original_batch_qty
    assert len(res["restored_batches"]) == 1
    assert res["restored_batches"][0]["batch_id"] == batch.id


# ==============================================================================
# TEST 7: Multiple Original Batch Allocations
# ==============================================================================
def test_multiple_original_batch_allocations(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    b1 = make_batch(db, tenant.id, store.id, product.id, "BAT-007A", quantity=Decimal("50"))
    b2 = make_batch(db, tenant.id, store.id, product.id, "BAT-007B", quantity=Decimal("50"))

    # Sale drew 5 from b1 and 5 from b2
    user, order, invoice, inv_item = create_test_sale(
        db,
        tenant.id,
        store.id,
        product,
        qty=Decimal("10"),
        batches=[(b1, Decimal("5")), (b2, Decimal("5"))],
    )

    assert b1.remaining_quantity == Decimal("45")
    assert b2.remaining_quantity == Decimal("45")

    service = BillingService(db)
    # Return 7 units: should restore 5 to b2 (most recent) and 2 to b1
    res = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("7"),
        user=user,
    )

    db.refresh(b1)
    db.refresh(b2)
    assert b2.remaining_quantity == Decimal("50")  # restored 5
    assert b1.remaining_quantity == Decimal("47")  # restored 2
    assert len(res["restored_batches"]) == 2


# ==============================================================================
# TEST 8: Damaged and Expired Returned Goods (Zero Saleable Stock)
# ==============================================================================
def test_damaged_and_expired_returned_goods(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-008", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("10"), batch=batch)
    assert batch.remaining_quantity == Decimal("40")

    service = BillingService(db)
    # Return 5 units as damaged
    res = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("5"),
        user=user,
        condition="damaged",
    )

    db.refresh(batch)
    # CRITICAL: damaged goods MUST NOT increase saleable stock!
    assert batch.remaining_quantity == Decimal("40")

    # Verify StockMovement record logged as ADJUSTMENT with 0 saleable quantity
    sm = (
        db.query(StockMovement)
        .filter(StockMovement.reference_id == invoice.id, StockMovement.movement_type == StockMovementType.ADJUSTMENT.value)
        .first()
    )
    assert sm is not None
    assert "damaged" in sm.notes.lower()


# ==============================================================================
# TEST 9: Non-Batch-Managed Item Return
# ==============================================================================
def test_non_batch_managed_item_return(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_batch=False)

    # Initial inventory 100
    inv = Inventory(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        batch_id=None,
        quantity=Decimal("100"),
    )
    db.add(inv)
    db.commit()

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("15"))
    assert inv.quantity == Decimal("85")

    service = BillingService(db)
    res = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("15"),
        user=user,
        condition="sellable",
    )

    db.refresh(inv)
    assert inv.quantity == Decimal("100")
    assert res["status"] == "return_processed"


# ==============================================================================
# TEST 10: Aggregate Inventory and Batch Balance Consistency
# ==============================================================================
def test_aggregate_inventory_and_batch_balance_consistency(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    b1 = make_batch(db, tenant.id, store.id, product.id, "BAT-010A", quantity=Decimal("30"))
    b2 = make_batch(db, tenant.id, store.id, product.id, "BAT-010B", quantity=Decimal("20"))

    user, order, invoice, inv_item = create_test_sale(
        db,
        tenant.id,
        store.id,
        product,
        qty=Decimal("10"),
        batches=[(b1, Decimal("6")), (b2, Decimal("4"))],
    )

    service = BillingService(db)
    service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("10"),
        user=user,
        condition="sellable",
    )

    db.refresh(b1)
    db.refresh(b2)
    total_batch_rem = b1.remaining_quantity + b2.remaining_quantity

    inv_batch_rows = db.query(func.sum(Inventory.quantity)).filter(
        Inventory.tenant_id == tenant.id,
        Inventory.store_id == store.id,
        Inventory.product_id == product.id,
        Inventory.batch_id.isnot(None),
    ).scalar()

    assert Decimal(str(inv_batch_rows)) == total_batch_rem == Decimal("50.0000")


# ==============================================================================
# TEST 11: Failure During Credit Note Creation Rolls Back Entirely
# ==============================================================================
def test_failure_during_credit_note_creation_rolls_back_entirely(db, monkeypatch):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-011", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("10"), batch=batch)
    assert batch.remaining_quantity == Decimal("40")

    service = BillingService(db)

    # Monkeypatch _generate_credit_note_number to simulate unexpected collision/crash
    def broken_generator(*args, **kwargs):
        raise RuntimeError("Simulated sequence crash during credit note generation")

    monkeypatch.setattr(service, "_generate_credit_note_number", broken_generator)

    with pytest.raises(RuntimeError):
        service.process_return(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            product_id=product.id,
            return_quantity=Decimal("10"),
            user=user,
            issue_credit_note=True,
        )

    # Verify complete rollback: inventory NOT incremented, returned_quantity still 0, status still paid
    db.refresh(batch)
    db.refresh(inv_item)
    db.refresh(invoice)
    assert batch.remaining_quantity == Decimal("40")
    assert inv_item.returned_quantity == Decimal("0.00")
    assert invoice.status == "paid"


# ==============================================================================
# TEST 12: Failure During Refund Record Creation Rolls Back
# ==============================================================================
def test_failure_during_refund_record_creation_rolls_back(db, monkeypatch):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-012", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("10"), batch=batch)

    service = BillingService(db)

    def broken_create_refund(*args, **kwargs):
        raise RuntimeError("Simulated refund gateway ledger crash")

    monkeypatch.setattr(service, "create_refund", broken_create_refund)

    with pytest.raises(RuntimeError):
        service.process_return(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            product_id=product.id,
            return_quantity=Decimal("10"),
            user=user,
            issue_credit_note=True,
        )

    db.refresh(batch)
    db.refresh(inv_item)
    assert batch.remaining_quantity == Decimal("40")
    assert inv_item.returned_quantity == Decimal("0.00")


# ==============================================================================
# TEST 13: Duplicate Refund / Idempotency Request
# ==============================================================================
def test_duplicate_refund_idempotency_request(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-013", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("10"), batch=batch)

    service = BillingService(db)
    idemp_key = f"IDEMP-{uuid.uuid4().hex[:12]}"

    res1 = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("4"),
        user=user,
        idempotency_key=idemp_key,
    )

    # Replay identical request
    res2 = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("4"),
        user=user,
        idempotency_key=idemp_key,
    )

    assert res1["return_id"] == res2["return_id"]
    db.refresh(batch)
    # Batch only restored once (4 units, not 8)
    assert batch.remaining_quantity == Decimal("44")


# ==============================================================================
# TEST 14: Concurrent Refund Limit Enforcement
# ==============================================================================
def test_concurrent_refund_limit_enforcement(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, price=Decimal("100.00"))  # Total 118 with GST
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-014", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("1"), batch=batch)
    total_invoice = invoice.total_amount  # 118.00

    results = []
    errors = []

    def attempt_refund(amt):
        s = SessionLocal()
        try:
            srv = BillingService(s)
            u = s.get(User, user.id)
            ref = srv.create_refund(
                tenant_id=tenant.id,
                invoice_id=invoice.id,
                refund_amount=Decimal(str(amt)),
                refund_method="cash",
                reason="Concurrent refund test",
                user=u,
            )
            results.append(ref)
        except Exception as e:
            errors.append(e)
        finally:
            s.close()

    # Total is 118. Both threads attempt 100.00 refund
    t1 = threading.Thread(target=attempt_refund, args=("100.00",))
    t2 = threading.Thread(target=attempt_refund, args=("100.00",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # One succeeds, other must fail because 100 + 100 > 118
    assert len(results) == 1
    assert len(errors) == 1
    assert "cannot exceed eligible paid amount" in str(errors[0]).lower()


# ==============================================================================
# TEST 15: Correct GST Reversal and Original Invoice Linkage
# ==============================================================================
def test_correct_gst_reversal_and_original_invoice_linkage(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, price=Decimal("100.00"))  # Subtotal 1000, GST 180 (CGST 90, SGST 90)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-015", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("10"), batch=batch)

    service = BillingService(db)
    # Return 5 units with credit note issued
    res = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("5"),
        user=user,
        issue_credit_note=True,
    )

    cn = db.get(CreditNote, res["credit_note_id"])
    assert cn is not None
    assert cn.invoice_id == invoice.id
    # Half return -> exactly half CGST and SGST
    assert cn.cgst_amount == (invoice.cgst_amount / 2).quantize(Decimal("0.01"))
    assert cn.sgst_amount == (invoice.sgst_amount / 2).quantize(Decimal("0.01"))
    assert cn.refund_amount == (invoice.total_amount / 2).quantize(Decimal("0.01"))


# ==============================================================================
# TEST 16: Cross-Store and Cross-Tenant Denial
# ==============================================================================
def test_cross_store_and_cross_tenant_denial(db):
    tenant_a = make_tenant(db, "Tenant A")
    tenant_b = make_tenant(db, "Tenant B")
    store_a1 = make_store(db, tenant_a.id, "Store A1")
    store_a2 = make_store(db, tenant_a.id, "Store A2")

    product_a = make_product(db, tenant_a.id)
    batch_a = make_batch(db, tenant_a.id, store_a1.id, product_a.id, "BAT-016", quantity=Decimal("50"))

    user_a1, order, invoice, inv_item = create_test_sale(db, tenant_a.id, store_a1.id, product_a, qty=Decimal("5"), batch=batch_a)

    user_a2 = make_user(db, tenant_a.id, store_id=store_a2.id, role_name="cashier")
    user_b = make_user(db, tenant_b.id, store_id=None, role_name="owner")

    service = BillingService(db)

    # Cross-store denial within same tenant
    with pytest.raises(ForbiddenException):
        service.process_return(
            tenant_id=tenant_a.id,
            invoice_id=invoice.id,
            product_id=product_a.id,
            return_quantity=Decimal("1"),
            user=user_a2,
        )

    # Cross-tenant denial
    with pytest.raises(NotFoundException):
        service.process_return(
            tenant_id=tenant_b.id,
            invoice_id=invoice.id,
            product_id=product_a.id,
            return_quantity=Decimal("1"),
            user=user_b,
        )


# ==============================================================================
# TEST 17: Historical Records Without Reliable Batch Provenance
# ==============================================================================
def test_historical_records_without_reliable_batch_provenance(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_batch=True)  # Product marked track_batch

    # Create sale WITHOUT batch allocations (simulates legacy historical order)
    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("5"), batch=None)

    inv = Inventory(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        batch_id=None,
        quantity=Decimal("20"),
    )
    db.add(inv)
    db.commit()

    service = BillingService(db)
    # Must safely restore aggregate inventory without guessing or crashing
    res = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("5"),
        user=user,
        condition="sellable",
    )

    db.refresh(inv)
    assert inv.quantity == Decimal("25")
    assert res["status"] == "return_processed"
    assert res["restored_batches"] == []


# ==============================================================================
# TEST 18: Idempotency Payload Mismatch Consistently Rejected
# ==============================================================================
def test_idempotency_payload_mismatch_rejected(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-018", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("10"), batch=batch)
    service = BillingService(db)

    # First return with key "KEY-ALPHA"
    res1 = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("2"),
        user=user,
        condition="sellable",
        idempotency_key="KEY-ALPHA",
    )
    assert res1["return_quantity"] == Decimal("2.0000")

    # Replay with IDENTICAL payload -> succeeds with same return record
    res1_replay = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("2"),
        user=user,
        condition="sellable",
        idempotency_key="KEY-ALPHA",
    )
    assert res1_replay["return_id"] == res1["return_id"]

    # Replay with DIFFERENT return_quantity -> must be rejected
    with pytest.raises(AppException) as exc_qty:
        service.process_return(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            product_id=product.id,
            return_quantity=Decimal("4"),  # Mismatched quantity
            user=user,
            condition="sellable",
            idempotency_key="KEY-ALPHA",
        )
    assert "idempotency key collision" in str(exc_qty.value).lower()

    # Replay with DIFFERENT condition -> must be rejected
    with pytest.raises(AppException) as exc_cond:
        service.process_return(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            product_id=product.id,
            return_quantity=Decimal("2"),
            user=user,
            condition="damaged",  # Mismatched condition
            idempotency_key="KEY-ALPHA",
        )
    assert "idempotency key collision" in str(exc_cond.value).lower()


# ==============================================================================
# TEST 19: Multi-Tenant Idempotency Key Isolation
# ==============================================================================
def test_idempotency_tenant_isolation(db):
    tenant_a = make_tenant(db, "Tenant A")
    store_a = make_store(db, tenant_a.id, "Store A")
    prod_a = make_product(db, tenant_a.id, "Prod A")
    batch_a = make_batch(db, tenant_a.id, store_a.id, prod_a.id, "BAT-A", quantity=Decimal("50"))
    user_a, _, inv_a, _ = create_test_sale(db, tenant_a.id, store_a.id, prod_a, qty=Decimal("5"), batch=batch_a)

    tenant_b = make_tenant(db, "Tenant B")
    store_b = make_store(db, tenant_b.id, "Store B")
    prod_b = make_product(db, tenant_b.id, "Prod B")
    batch_b = make_batch(db, tenant_b.id, store_b.id, prod_b.id, "BAT-B", quantity=Decimal("50"))
    user_b, _, inv_b, _ = create_test_sale(db, tenant_b.id, store_b.id, prod_b, qty=Decimal("5"), batch=batch_b)

    service = BillingService(db)
    shared_key = f"SHARED-IDEMP-{uuid.uuid4().hex[:6]}"

    # Tenant A uses the shared key
    res_a = service.process_return(
        tenant_id=tenant_a.id,
        invoice_id=inv_a.id,
        product_id=prod_a.id,
        return_quantity=Decimal("2"),
        user=user_a,
        idempotency_key=shared_key,
    )
    assert res_a["return_quantity"] == Decimal("2.0000")

    # Tenant B uses the same shared key -> must succeed independently without conflict
    res_b = service.process_return(
        tenant_id=tenant_b.id,
        invoice_id=inv_b.id,
        product_id=prod_b.id,
        return_quantity=Decimal("3"),
        user=user_b,
        idempotency_key=shared_key,
    )
    assert res_b["return_quantity"] == Decimal("3.0000")
    assert res_a["return_id"] != res_b["return_id"]


# ==============================================================================
# TEST 20: Batch Capacity Overflow Rejection (Zero Ledger Drift)
# ==============================================================================
def test_batch_capacity_overflow_rejected_without_ledger_drift(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-CAP-1", quantity=Decimal("20.0000"))

    # Sell 10 units: batch remaining becomes 10
    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("10"), batch=batch)
    assert batch.remaining_quantity == Decimal("10.0000")

    # Simulate external modification of batch remaining_quantity to 18 (e.g. manual restock)
    batch.remaining_quantity = Decimal("18.0000")
    agg_inv = db.query(Inventory).filter(
        Inventory.tenant_id == tenant.id,
        Inventory.store_id == store.id,
        Inventory.product_id == product.id,
        Inventory.batch_id.is_(None),
    ).first()
    agg_inv.quantity = Decimal("18.0000")
    db.commit()

    service = BillingService(db)

    # Attempting to return 5 units: 18 + 5 = 23 > 20 (lot capacity)
    # System MUST REJECT rather than silently capping, and rollback without altering aggregate inventory
    with pytest.raises(AppException) as exc:
        service.process_return(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            product_id=product.id,
            return_quantity=Decimal("5"),
            user=user,
            condition="sellable",
        )
    assert "exceeds lot capacity" in str(exc.value).lower()

    # Verify zero ledger drift: both batch and aggregate inventory remain at 18
    db.refresh(batch)
    db.refresh(agg_inv)
    assert batch.remaining_quantity == Decimal("18.0000")
    assert agg_inv.quantity == Decimal("18.0000")


# ==============================================================================
# TEST 21: Fractional Quantities and Repeated Partial Returns (Numeric 12, 4)
# ==============================================================================
def test_fractional_quantities_and_repeated_partial_returns(db):
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, price=Decimal("100.00"))
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-FRAC-1", quantity=Decimal("50.0000"))

    # Sell 4 units
    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("4"), batch=batch)
    assert batch.remaining_quantity == Decimal("46.0000")

    service = BillingService(db)

    # Partial return 1: 1.2500 units
    res1 = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("1.2500"),
        user=user,
    )
    db.refresh(batch)
    db.refresh(inv_item)
    assert batch.remaining_quantity == Decimal("47.2500")
    assert inv_item.returned_quantity == Decimal("1.2500")
    assert res1["remaining_returnable_quantity"] == Decimal("2.7500")

    # Partial return 2: 0.5000 units
    res2 = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("0.5000"),
        user=user,
    )
    db.refresh(batch)
    db.refresh(inv_item)
    assert batch.remaining_quantity == Decimal("47.7500")
    assert inv_item.returned_quantity == Decimal("1.7500")
    assert res2["remaining_returnable_quantity"] == Decimal("2.2500")

    # Final partial return 3: remaining 2.2500 units
    res3 = service.process_return(
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        product_id=product.id,
        return_quantity=Decimal("2.2500"),
        user=user,
    )
    db.refresh(batch)
    db.refresh(inv_item)
    db.refresh(invoice)
    assert batch.remaining_quantity == Decimal("50.0000")
    assert inv_item.returned_quantity == Decimal("4.0000")
    assert invoice.status == "refunded"
    assert res3["remaining_returnable_quantity"] == Decimal("0.0000")


# ==============================================================================
# TEST 22: MySQL Multi-Connection Concurrent Refund Limit Enforcement
# ==============================================================================
def test_mysql_multi_connection_refund_concurrency(db):
    """
    Verifies that multi-connection concurrent refund requests are strictly
    capped at the eligible paid amount on MySQL 8.
    """
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, price=Decimal("100.00"))  # Total 118 with GST
    batch = make_batch(db, tenant.id, store.id, product.id, "BAT-CONCUR-22", quantity=Decimal("50"))

    user, order, invoice, inv_item = create_test_sale(db, tenant.id, store.id, product, qty=Decimal("1"), batch=batch)

    results = []
    errors = []

    def make_concurrent_refund(amount):
        session = SessionLocal()
        try:
            srv = BillingService(session)
            u = session.get(User, user.id)
            ref = srv.create_refund(
                tenant_id=tenant.id,
                invoice_id=invoice.id,
                refund_amount=Decimal(str(amount)),
                refund_method="cash",
                reason="Multi-connection concurrent test",
                user=u,
            )
            results.append(ref)
        except Exception as e:
            errors.append(e)
        finally:
            session.close()

    t1 = threading.Thread(target=make_concurrent_refund, args=("100.00",))
    t2 = threading.Thread(target=make_concurrent_refund, args=("100.00",))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Total is 118. Both attempted 100. Exactly 1 must succeed, exactly 1 must fail
    assert len(results) == 1
    assert len(errors) == 1
    assert "cannot exceed eligible paid amount" in str(errors[0]).lower()


