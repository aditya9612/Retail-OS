from datetime import date, datetime, timedelta
from decimal import Decimal
import threading
import uuid
import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.exceptions import AppException, NotFoundException
from app.models.inventory import Inventory, StockMovement
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_item_batch_allocation import OrderItemBatchAllocation
from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.product_variant import ProductVariant
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.order_item_batch_allocation_repo import OrderItemBatchAllocationRepository
from app.schemas.order import OrderCreate, OrderItemCreate
from app.services.batch_allocation_service import InsufficientStockException
from app.services.order_service import OrderService
from app.utils.constants import OrderStatus, StockMovementType


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def make_tenant(db, name="Order Batch Tenant"):
    tenant = Tenant(name=name, domain=f"t-{uuid.uuid4().hex[:8]}.com")
    db.add(tenant)
    db.flush()
    return tenant


def make_store(db, tenant_id, name="Order Store"):
    store = Store(tenant_id=tenant_id, name=name, code=f"STR-{uuid.uuid4().hex[:6]}")
    db.add(store)
    db.flush()
    return store


def make_product(db, tenant_id, name="Order Product", track_batch=True, track_expiry=False):
    prod = Product(
        tenant_id=tenant_id,
        name=name,
        sku=f"SKU-{uuid.uuid4().hex[:8]}",
        selling_price=Decimal("200.00"),
        cost_price=Decimal("100.00"),
    )
    prod.track_batch = track_batch
    prod.track_expiry = track_expiry
    db.add(prod)
    db.flush()
    return prod


def make_variant(db, tenant_id, product_id, name="Order Variant"):
    var = ProductVariant(
        tenant_id=tenant_id,
        product_id=product_id,
        variant_name=name,
        sku=f"VAR-{uuid.uuid4().hex[:8]}",
    )
    db.add(var)
    db.flush()
    return var


def make_batch(
    db,
    tenant_id,
    store_id,
    product_id,
    batch_number,
    quantity,
    variant_id=None,
    expiry_date=None,
    unit_cost=Decimal("60.0000"),
    created_at=None,
    is_active=True,
):
    b = ProductBatch(
        tenant_id=tenant_id,
        store_id=store_id,
        product_id=product_id,
        variant_id=variant_id,
        batch_number=batch_number,
        quantity=Decimal(str(quantity)),
        remaining_quantity=Decimal(str(quantity)),
        unit_cost=Decimal(str(unit_cost)),
        expiry_date=expiry_date,
        is_active=is_active,
    )
    if created_at:
        b.created_at = created_at
    db.add(b)
    db.flush()

    inv = Inventory(
        tenant_id=tenant_id,
        store_id=store_id,
        product_id=product_id,
        batch_id=b.id,
        quantity=Decimal(str(quantity)),
    )
    db.add(inv)
    db.flush()
    return b


def make_order(db, tenant_id, store_id, items, status=OrderStatus.DRAFT.value, user_id=None):
    if user_id is None:
        user = db.query(User).first()
        user_id = user.id if user else 1
    order = Order(
        tenant_id=tenant_id,
        store_id=store_id,
        user_id=user_id,
        order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        order_type="pos",
        status=status,
    )
    for prod, qty, var_id in items:
        order_item = OrderItem(
            product_id=prod.id,
            product_name=prod.name,
            sku=prod.sku,
            quantity=qty,
            unit_price=prod.selling_price,
            discount=Decimal("0.00"),
            tax_rate=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total=prod.selling_price * qty,
            variant_id=var_id,
        )
        order.items.append(order_item)
    db.add(order)
    db.flush()
    return order


# =============================================================================
# 1. Basic Allocation & Single Batch Tests
# =============================================================================
def test_order_confirm_allocates_from_single_batch(db):
    """Confirming a draft order allocates stock from batch and creates OrderItemBatchAllocation."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_batch=True)
    batch = make_batch(db, tenant.id, store.id, product.id, "B-SINGLE-1", quantity=Decimal("20.0000"), unit_cost=Decimal("45.0000"))
    db.commit()

    order = make_order(db, tenant.id, store.id, items=[(product, 5, None)])
    db.commit()
    item_id = order.items[0].id

    service = OrderService(db)
    confirmed_order = service.confirm_order(tenant.id, order.id)

    assert confirmed_order.status == OrderStatus.CONFIRMED.value

    # Verify batch mutation: quantity unmodified, remaining_quantity decremented
    db.refresh(batch)
    assert batch.quantity == Decimal("20.0000")
    assert batch.remaining_quantity == Decimal("15.0000")

    # Verify Inventory mirror
    inv = db.execute(
        select(Inventory).where(Inventory.batch_id == batch.id)
    ).scalar_one()
    assert inv.quantity == Decimal("15.0000")

    # Verify OrderItemBatchAllocation row
    alloc_repo = OrderItemBatchAllocationRepository(db)
    allocs = alloc_repo.get_by_order_item_id(item_id)
    assert len(allocs) == 1
    assert allocs[0].batch_id == batch.id
    assert allocs[0].quantity == Decimal("5.0000")
    assert allocs[0].unit_cost == Decimal("45.0000")

    # Verify StockMovement ALLOCATION
    movement = db.execute(
        select(StockMovement).where(
            StockMovement.reference_id == order.id,
            StockMovement.movement_type == StockMovementType.ALLOCATION.value,
        )
    ).scalar_one()
    assert movement.quantity == Decimal("5.0000")
    assert movement.previous_stock == Decimal("20.0000")
    assert movement.new_stock == Decimal("15.0000")


# =============================================================================
# 2. Multi-Batch Spanning Tests
# =============================================================================
def test_order_confirm_multi_batch_spanning(db):
    """One order item spanning multiple batches creates multiple OrderItemBatchAllocation rows summing to item qty."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_batch=True)

    b1 = make_batch(
        db, tenant.id, store.id, product.id, "B-MULTI-1",
        quantity=Decimal("5.0000"), unit_cost=Decimal("40.0000"),
        created_at=datetime.utcnow() - timedelta(days=2),
    )
    b2 = make_batch(
        db, tenant.id, store.id, product.id, "B-MULTI-2",
        quantity=Decimal("10.0000"), unit_cost=Decimal("50.0000"),
        created_at=datetime.utcnow() - timedelta(days=1),
    )
    db.commit()

    order = make_order(db, tenant.id, store.id, items=[(product, 12, None)])
    db.commit()
    item_id = order.items[0].id

    service = OrderService(db)
    service.confirm_order(tenant.id, order.id)

    db.refresh(b1)
    db.refresh(b2)
    assert b1.remaining_quantity == Decimal("0.0000")
    assert b2.remaining_quantity == Decimal("3.0000")

    alloc_repo = OrderItemBatchAllocationRepository(db)
    allocs = alloc_repo.get_by_order_item_id(item_id)
    assert len(allocs) == 2

    # FIFO: b1 allocated first (5), then b2 (7)
    assert allocs[0].batch_id == b1.id
    assert allocs[0].quantity == Decimal("5.0000")
    assert allocs[0].unit_cost == Decimal("40.0000")

    assert allocs[1].batch_id == b2.id
    assert allocs[1].quantity == Decimal("7.0000")
    assert allocs[1].unit_cost == Decimal("50.0000")

    total_allocated = sum((a.quantity for a in allocs), Decimal("0"))
    assert total_allocated == Decimal("12.0000")


# =============================================================================
# 3. FIFO Ordering Tests
# =============================================================================
def test_order_confirm_fifo_ordering(db):
    """Order confirmation strictly consumes oldest batch first."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_batch=True, track_expiry=False)

    b_old = make_batch(
        db, tenant.id, store.id, product.id, "B-FIFO-OLD",
        quantity=Decimal("10.0000"), created_at=datetime.utcnow() - timedelta(days=5),
    )
    b_new = make_batch(
        db, tenant.id, store.id, product.id, "B-FIFO-NEW",
        quantity=Decimal("10.0000"), created_at=datetime.utcnow(),
    )
    db.commit()

    order = make_order(db, tenant.id, store.id, items=[(product, 6, None)])
    db.commit()

    service = OrderService(db)
    service.confirm_order(tenant.id, order.id)

    db.refresh(b_old)
    db.refresh(b_new)
    assert b_old.remaining_quantity == Decimal("4.0000")
    assert b_new.remaining_quantity == Decimal("10.0000")


# =============================================================================
# 4. FEFO Ordering and Expiry Tests
# =============================================================================
def test_order_confirm_fefo_ordering_and_expiry_exclusion(db):
    """Perishable product confirmation orders by earliest expiry and excludes expired batches."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_batch=True, track_expiry=True)

    today = date.today()
    b_expired = make_batch(
        db, tenant.id, store.id, product.id, "B-EXP",
        quantity=Decimal("20.0000"), expiry_date=today - timedelta(days=1),
    )
    b_early = make_batch(
        db, tenant.id, store.id, product.id, "B-EARLY",
        quantity=Decimal("5.0000"), expiry_date=today + timedelta(days=5),
    )
    b_late = make_batch(
        db, tenant.id, store.id, product.id, "B-LATE",
        quantity=Decimal("10.0000"), expiry_date=today + timedelta(days=30),
    )
    db.commit()

    order = make_order(db, tenant.id, store.id, items=[(product, 4, None)])
    db.commit()

    service = OrderService(db)
    service.confirm_order(tenant.id, order.id)

    db.refresh(b_expired)
    db.refresh(b_early)
    db.refresh(b_late)

    # Expired batch untouched
    assert b_expired.remaining_quantity == Decimal("20.0000")
    # Early batch allocated
    assert b_early.remaining_quantity == Decimal("1.0000")
    assert b_late.remaining_quantity == Decimal("10.0000")


# =============================================================================
# 5. Quantity Semantics Tests
# =============================================================================
def test_order_confirm_quantity_semantics_total_quantity_unmodified(db):
    """ProductBatch.quantity remains unchanged while remaining_quantity is decremented."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_batch=True)
    batch = make_batch(
        db, tenant.id, store.id, product.id, "B-SEMANTICS",
        quantity=Decimal("100.0000"),
    )
    db.commit()

    order = make_order(db, tenant.id, store.id, items=[(product, 35, None)])
    db.commit()

    service = OrderService(db)
    service.confirm_order(tenant.id, order.id)

    db.refresh(batch)
    assert batch.quantity == Decimal("100.0000")
    assert batch.remaining_quantity == Decimal("65.0000")


# =============================================================================
# 6. Insufficient Stock Atomic Rollback Tests
# =============================================================================
def test_order_confirm_insufficient_stock_atomic_rollback(db):
    """If stock across batches is insufficient, entire order confirmation rolls back."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_batch=True)

    b1 = make_batch(db, tenant.id, store.id, product.id, "B-ROLL-1", quantity=Decimal("4.0000"))
    b2 = make_batch(db, tenant.id, store.id, product.id, "B-ROLL-2", quantity=Decimal("3.0000"))
    db.commit()

    order = make_order(db, tenant.id, store.id, items=[(product, 10, None)])
    db.commit()

    service = OrderService(db)
    with pytest.raises(InsufficientStockException):
        service.confirm_order(tenant.id, order.id)

    # Verify order status remained draft
    db.refresh(order)
    assert order.status == OrderStatus.DRAFT.value

    # Verify batches remained untouched
    db.refresh(b1)
    db.refresh(b2)
    assert b1.remaining_quantity == Decimal("4.0000")
    assert b2.remaining_quantity == Decimal("3.0000")

    # Verify zero allocation records created
    alloc_repo = OrderItemBatchAllocationRepository(db)
    allocs = alloc_repo.get_by_order_item_id(order.items[0].id)
    assert len(allocs) == 0

    # Verify zero stock movements created
    movements = db.execute(
        select(StockMovement).where(StockMovement.reference_id == order.id)
    ).scalars().all()
    assert len(movements) == 0


# =============================================================================
# 7. Non-Batch Product Tests
# =============================================================================
def test_order_confirm_non_batch_product_uses_standard_stock_out(db):
    """Non-batch product uses existing stock_out without creating OrderItemBatchAllocation."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_batch=False)

    # Setup non-batch Inventory row
    inv = Inventory(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        batch_id=None,
        quantity=Decimal("50.0000"),
    )
    db.add(inv)
    db.commit()

    order = make_order(db, tenant.id, store.id, items=[(product, 10, None)])
    db.commit()
    item_id = order.items[0].id

    service = OrderService(db)
    service.confirm_order(tenant.id, order.id)

    db.refresh(inv)
    assert inv.quantity == Decimal("40.0000")

    # Zero batch allocations created
    alloc_repo = OrderItemBatchAllocationRepository(db)
    allocs = alloc_repo.get_by_order_item_id(item_id)
    assert len(allocs) == 0

    # StockMovement of type stock_out
    movement = db.execute(
        select(StockMovement).where(
            StockMovement.store_id == store.id,
            StockMovement.product_id == product.id,
            StockMovement.movement_type == StockMovementType.STOCK_OUT.value,
        )
    ).scalar_one()
    assert movement.quantity == Decimal("10.0000")


# =============================================================================
# 8. Strict Variant Isolation Tests
# =============================================================================
def test_order_confirm_strict_variant_isolation(db):
    """Variant-specific order item only consumes matching variant batches and fails if exhausted."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_batch=True)
    var_red = make_variant(db, tenant.id, product.id, name="Red")
    var_blue = make_variant(db, tenant.id, product.id, name="Blue")

    b_red = make_batch(db, tenant.id, store.id, product.id, "B-RED", quantity=Decimal("5.0000"), variant_id=var_red.id)
    b_blue = make_batch(db, tenant.id, store.id, product.id, "B-BLUE", quantity=Decimal("20.0000"), variant_id=var_blue.id)
    db.commit()

    # Request 8 units of Red (only 5 available). Must NOT borrow from Blue!
    order = make_order(db, tenant.id, store.id, items=[(product, 8, var_red.id)])
    db.commit()

    service = OrderService(db)
    with pytest.raises(InsufficientStockException):
        service.confirm_order(tenant.id, order.id)

    db.refresh(b_red)
    db.refresh(b_blue)
    assert b_red.remaining_quantity == Decimal("5.0000")
    assert b_blue.remaining_quantity == Decimal("20.0000")


# =============================================================================
# 9. Tenant & Store Isolation Tests
# =============================================================================
def test_order_confirm_tenant_and_store_isolation(db):
    """Order confirmation cannot allocate batches from different store or tenant."""
    t1 = make_tenant(db, "Tenant 1")
    t2 = make_tenant(db, "Tenant 2")
    s1 = make_store(db, t1.id, "Store 1")
    s2 = make_store(db, t1.id, "Store 2")

    p1 = make_product(db, t1.id, track_batch=True)
    # Batch belongs to Store 2
    b_store2 = make_batch(db, t1.id, s2.id, p1.id, "B-S2", quantity=Decimal("20.0000"))
    db.commit()

    # Order in Store 1
    order = make_order(db, t1.id, s1.id, items=[(p1, 5, None)])
    db.commit()

    service = OrderService(db)
    # Should fail because Store 1 has no batches
    with pytest.raises(InsufficientStockException):
        service.confirm_order(t1.id, order.id)

    db.refresh(b_store2)
    assert b_store2.remaining_quantity == Decimal("20.0000")


# =============================================================================
# 10. Concurrency Protection Tests
# =============================================================================
def test_order_confirm_concurrency_no_oversell():
    """Concurrent order confirmations for competing orders prevent overselling."""
    setup_db = SessionLocal()
    tenant = make_tenant(setup_db)
    store = make_store(setup_db, tenant.id)
    product = make_product(setup_db, tenant.id, track_batch=True)
    batch = make_batch(
        setup_db, tenant.id, store.id, product.id, "B-ORDER-CONCUR",
        quantity=Decimal("10.0000"),
    )
    order1 = make_order(setup_db, tenant.id, store.id, items=[(product, 7, None)])
    order2 = make_order(setup_db, tenant.id, store.id, items=[(product, 7, None)])
    setup_db.commit()

    batch_id = batch.id
    order1_id = order1.id
    order2_id = order2.id
    tenant_id = tenant.id
    setup_db.close()

    results = {"success": 0, "blocked": 0}
    errors = []

    def confirm_worker(order_id):
        worker_db = SessionLocal()
        try:
            worker_svc = OrderService(worker_db)
            worker_svc.confirm_order(tenant_id, order_id)
            results["success"] += 1
        except (InsufficientStockException, AppException):
            results["blocked"] += 1
        except Exception as e:
            errors.append(e)
        finally:
            worker_db.close()

    t1 = threading.Thread(target=confirm_worker, args=(order1_id,))
    t2 = threading.Thread(target=confirm_worker, args=(order2_id,))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(errors) == 0, f"Unexpected errors: {errors}"
    assert results["success"] == 1
    assert results["blocked"] == 1

    verify_db = SessionLocal()
    final_batch = verify_db.get(ProductBatch, batch_id)
    assert final_batch.quantity == Decimal("10.0000")
    assert final_batch.remaining_quantity == Decimal("3.0000")

    alloc_repo = OrderItemBatchAllocationRepository(verify_db)
    allocs1 = alloc_repo.get_by_order_id(order1_id)
    allocs2 = alloc_repo.get_by_order_id(order2_id)
    # Exactly one order has allocations
    assert (len(allocs1) == 1 and len(allocs2) == 0) or (len(allocs1) == 0 and len(allocs2) == 1)
    verify_db.close()


# =============================================================================
# 11. Order Cancellation Tests
# =============================================================================
def test_order_cancel_does_not_double_deduct(db):
    """Cancelling a confirmed order updates status without triggering further batch deduction."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_batch=True)
    batch = make_batch(db, tenant.id, store.id, product.id, "B-CANCEL", quantity=Decimal("20.0000"))
    db.commit()

    order = make_order(db, tenant.id, store.id, items=[(product, 5, None)])
    db.commit()

    service = OrderService(db)
    service.confirm_order(tenant.id, order.id)

    db.refresh(batch)
    assert batch.remaining_quantity == Decimal("15.0000")

    # Cancel the confirmed order
    cancelled_order = service.cancel_order(tenant.id, order.id)
    assert cancelled_order.status == OrderStatus.CANCELLED.value

    # Remaining quantity is NOT decremented again
    db.refresh(batch)
    assert batch.remaining_quantity == Decimal("15.0000")


# =============================================================================
# 12. Unit Cost Historical Snapshot Tests
# =============================================================================
def test_order_unit_cost_historical_persistence(db):
    """OrderItemBatchAllocation captures batch.unit_cost at allocation time and does not alter when batch updates."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_batch=True)
    batch = make_batch(
        db, tenant.id, store.id, product.id, "B-COST",
        quantity=Decimal("10.0000"), unit_cost=Decimal("42.5000"),
    )
    db.commit()

    order = make_order(db, tenant.id, store.id, items=[(product, 4, None)])
    db.commit()

    service = OrderService(db)
    service.confirm_order(tenant.id, order.id)

    alloc_repo = OrderItemBatchAllocationRepository(db)
    allocs = alloc_repo.get_by_order_item_id(order.items[0].id)
    assert len(allocs) == 1
    assert allocs[0].unit_cost == Decimal("42.5000")

    # Later batch cost changes in DB (e.g. recalculation or correction)
    batch.unit_cost = Decimal("88.0000")
    db.commit()

    # The historical allocation record unit_cost MUST remain 42.5000
    db.refresh(allocs[0])
    assert allocs[0].unit_cost == Decimal("42.5000")


# =============================================================================
# 13. Persistent variant_id Cross-Session Tests
# =============================================================================
def test_order_item_variant_id_cross_session_persistence():
    """OrderItem.variant_id is persisted to DB and survives a fresh SQLAlchemy session."""
    db1 = SessionLocal()
    tenant = make_tenant(db1)
    store = make_store(db1, tenant.id)
    user = db1.query(User).first()
    user_id = user.id if user else 1
    product = make_product(db1, tenant.id)
    variant = make_variant(db1, tenant.id, product.id, name="Size-M")
    db1.commit()

    service = OrderService(db1)
    create_dto = OrderCreate(
        store_id=store.id,
        order_type="pos",
        items=[
            OrderItemCreate(
                product_id=product.id,
                variant_id=variant.id,
                quantity=3,
                unit_price=Decimal("150.00"),
            )
        ],
    )
    created_order = service.create_order(tenant.id, user_id, create_dto)
    order_id = created_order.id
    order_item_id = created_order.items[0].id
    variant_id = variant.id
    db1.close()

    # Verify reload in genuinely fresh SQLAlchemy session
    db2 = SessionLocal()
    try:
        reloaded_item = db2.query(OrderItem).filter(OrderItem.id == order_item_id).first()
        assert reloaded_item is not None
        assert reloaded_item.variant_id == variant_id
        assert reloaded_item.order_id == order_id
    finally:
        db2.close()


def test_order_create_validates_variant_belongs_to_product(db):
    """Creating an order with variant belonging to a different product raises AppException."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    user = db.query(User).first()
    user_id = user.id if user else 1
    p1 = make_product(db, tenant.id, name="Product 1")
    p2 = make_product(db, tenant.id, name="Product 2")
    var2 = make_variant(db, tenant.id, p2.id, name="Var of P2")
    db.commit()

    service = OrderService(db)
    create_dto = OrderCreate(
        store_id=store.id,
        order_type="pos",
        items=[
            OrderItemCreate(
                product_id=p1.id,
                variant_id=var2.id,
                quantity=1,
                unit_price=Decimal("100.00"),
            )
        ],
    )
    with pytest.raises(AppException) as exc_info:
        service.create_order(tenant.id, user_id, create_dto)
    assert "does not belong to product" in str(exc_info.value.detail)


def test_order_create_validates_variant_tenant_isolation(db):
    """Creating an order referencing a variant from a different tenant raises NotFoundException."""
    t1 = make_tenant(db, "Tenant 1")
    t2 = make_tenant(db, "Tenant 2")
    s1 = make_store(db, t1.id, "Store 1")
    user = db.query(User).first()
    user_id = user.id if user else 1

    p1 = make_product(db, t1.id, name="P1")
    p2 = make_product(db, t2.id, name="P2")
    var_t2 = make_variant(db, t2.id, p2.id, name="Var Tenant 2")
    db.commit()

    service = OrderService(db)
    create_dto = OrderCreate(
        store_id=s1.id,
        order_type="pos",
        items=[
            OrderItemCreate(
                product_id=p1.id,
                variant_id=var_t2.id,
                quantity=1,
                unit_price=Decimal("100.00"),
            )
        ],
    )
    with pytest.raises(NotFoundException):
        service.create_order(t1.id, user_id, create_dto)


# =============================================================================
# 14. Critical End-to-End Variant Allocation with Fresh Session
# =============================================================================
def test_order_confirm_end_to_end_variant_allocation_fresh_session():
    """End-to-end order confirmation across separate DB sessions respects variant allocation."""
    setup_db = SessionLocal()
    tenant = make_tenant(setup_db)
    store = make_store(setup_db, tenant.id)
    product = make_product(setup_db, tenant.id, track_batch=True)
    var_a = make_variant(setup_db, tenant.id, product.id, name="Variant A")
    var_b = make_variant(setup_db, tenant.id, product.id, name="Variant B")

    # Batch A1: 5 units of Variant A
    batch_a1 = make_batch(
        setup_db, tenant.id, store.id, product.id, "B-E2E-A1",
        quantity=Decimal("5.0000"), variant_id=var_a.id,
    )
    # Batch B1: 20 units of Variant B
    batch_b1 = make_batch(
        setup_db, tenant.id, store.id, product.id, "B-E2E-B1",
        quantity=Decimal("20.0000"), variant_id=var_b.id,
    )
    setup_db.commit()

    tenant_id = tenant.id
    order_svc = OrderService(setup_db)
    user = setup_db.query(User).first()
    user_id = user.id if user else 1

    create_dto = OrderCreate(
        store_id=store.id,
        order_type="pos",
        items=[
            OrderItemCreate(
                product_id=product.id,
                variant_id=var_a.id,
                quantity=5,
                unit_price=Decimal("200.00"),
            )
        ],
    )
    order = order_svc.create_order(tenant_id, user_id, create_dto)
    order_id = order.id
    item_id = order.items[0].id
    batch_a1_id = batch_a1.id
    batch_b1_id = batch_b1.id
    var_a_id = var_a.id

    setup_db.commit()
    setup_db.close()

    # Confirm order in a fresh session
    confirm_db = SessionLocal()
    try:
        service = OrderService(confirm_db)
        confirmed = service.confirm_order(tenant_id, order_id)
        assert confirmed.status == OrderStatus.CONFIRMED.value

        reloaded_b_a1 = confirm_db.get(ProductBatch, batch_a1_id)
        reloaded_b_b1 = confirm_db.get(ProductBatch, batch_b1_id)
        assert reloaded_b_a1.remaining_quantity == Decimal("0.0000")
        assert reloaded_b_b1.remaining_quantity == Decimal("20.0000")

        reloaded_item = confirm_db.get(OrderItem, item_id)
        assert reloaded_item.variant_id == var_a_id

        alloc_repo = OrderItemBatchAllocationRepository(confirm_db)
        allocs = alloc_repo.get_by_order_item_id(item_id)
        assert len(allocs) == 1
        assert allocs[0].batch_id == batch_a1_id
        assert allocs[0].quantity == Decimal("5.0000")
    finally:
        confirm_db.close()


def test_order_confirm_strict_variant_isolation_fresh_session():
    """Strict variant isolation in fresh session: insufficient variant stock fails without fallback."""
    setup_db = SessionLocal()
    tenant = make_tenant(setup_db)
    store = make_store(setup_db, tenant.id)
    product = make_product(setup_db, tenant.id, track_batch=True)
    var_a = make_variant(setup_db, tenant.id, product.id, name="Variant A")
    var_b = make_variant(setup_db, tenant.id, product.id, name="Variant B")

    batch_a1 = make_batch(
        setup_db, tenant.id, store.id, product.id, "B-ISO-A1",
        quantity=Decimal("5.0000"), variant_id=var_a.id,
    )
    batch_b1 = make_batch(
        setup_db, tenant.id, store.id, product.id, "B-ISO-B1",
        quantity=Decimal("20.0000"), variant_id=var_b.id,
    )
    setup_db.commit()

    tenant_id = tenant.id
    order_svc = OrderService(setup_db)
    user = setup_db.query(User).first()
    user_id = user.id if user else 1

    create_dto = OrderCreate(
        store_id=store.id,
        order_type="pos",
        items=[
            OrderItemCreate(
                product_id=product.id,
                variant_id=var_a.id,
                quantity=6,  # 6 requested, only 5 available in A, 20 in B
                unit_price=Decimal("200.00"),
            )
        ],
    )
    order = order_svc.create_order(tenant_id, user_id, create_dto)
    order_id = order.id
    batch_a1_id = batch_a1.id
    batch_b1_id = batch_b1.id

    setup_db.commit()
    setup_db.close()

    # Fresh session confirmation
    confirm_db = SessionLocal()
    try:
        service = OrderService(confirm_db)
        with pytest.raises(InsufficientStockException):
            service.confirm_order(tenant_id, order_id)

        # Verify neither batch was mutated
        reloaded_a = confirm_db.get(ProductBatch, batch_a1_id)
        reloaded_b = confirm_db.get(ProductBatch, batch_b1_id)
        assert reloaded_a.remaining_quantity == Decimal("5.0000")
        assert reloaded_b.remaining_quantity == Decimal("20.0000")
    finally:
        confirm_db.close()


def test_order_confirm_non_variant_product_level_batch_allocation_fresh_session():
    """Non-variant order (variant_id=None) allocates from product-level batch (variant_id=None)."""
    setup_db = SessionLocal()
    tenant = make_tenant(setup_db)
    store = make_store(setup_db, tenant.id)
    product = make_product(setup_db, tenant.id, track_batch=True)

    batch_null = make_batch(
        setup_db, tenant.id, store.id, product.id, "B-PROD-NULL",
        quantity=Decimal("15.0000"), variant_id=None,
    )
    setup_db.commit()

    tenant_id = tenant.id
    order_svc = OrderService(setup_db)
    user = setup_db.query(User).first()
    user_id = user.id if user else 1

    create_dto = OrderCreate(
        store_id=store.id,
        order_type="pos",
        items=[
            OrderItemCreate(
                product_id=product.id,
                variant_id=None,
                quantity=5,
                unit_price=Decimal("200.00"),
            )
        ],
    )
    order = order_svc.create_order(tenant_id, user_id, create_dto)
    order_id = order.id
    batch_id = batch_null.id

    setup_db.commit()
    setup_db.close()

    # Fresh session confirmation
    confirm_db = SessionLocal()
    try:
        service = OrderService(confirm_db)
        confirmed = service.confirm_order(tenant_id, order_id)
        assert confirmed.status == OrderStatus.CONFIRMED.value

        reloaded_batch = confirm_db.get(ProductBatch, batch_id)
        assert reloaded_batch.remaining_quantity == Decimal("10.0000")
    finally:
        confirm_db.close()


