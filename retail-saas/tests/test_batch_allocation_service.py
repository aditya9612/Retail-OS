from datetime import date, datetime, timedelta
from decimal import Decimal
import threading
import uuid
import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.exceptions import AppException, ForbiddenException, NotFoundException
from app.models.inventory import Inventory, StockMovement
from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.product_variant import ProductVariant
from app.models.store import Store
from app.models.tenant import Tenant
from app.services.batch_allocation_service import (
    BatchAllocationService,
    ConcurrencyException,
    InsufficientStockException,
)
from app.utils.constants import StockMovementType


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def make_tenant(db, name="Alloc Tenant"):
    tenant = Tenant(name=name, domain=f"t-{uuid.uuid4().hex[:8]}.com")
    db.add(tenant)
    db.flush()
    return tenant


def make_store(db, tenant_id, name="Alloc Store"):
    store = Store(tenant_id=tenant_id, name=name, code=f"STR-{uuid.uuid4().hex[:6]}")
    db.add(store)
    db.flush()
    return store


def make_product(db, tenant_id, name="Alloc Product", track_batch=True, track_expiry=False):
    prod = Product(
        tenant_id=tenant_id,
        name=name,
        sku=f"SKU-{uuid.uuid4().hex[:8]}",
        selling_price=Decimal("150.00"),
        cost_price=Decimal("90.00"),
    )
    prod.track_batch = track_batch
    prod.track_expiry = track_expiry
    db.add(prod)
    db.flush()
    return prod


def make_variant(db, tenant_id, product_id, name="Variant Red"):
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
    unit_cost=Decimal("50.0000"),
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
    return b


# =============================================================================
# 1. Quantity Semantics Tests
# =============================================================================
def test_quantity_semantics_allocation_does_not_mutate_quantity(db):
    """ProductBatch.quantity remains unchanged while remaining_quantity decrements."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    batch = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        batch_number="BATCH-SEM-01",
        quantity=Decimal("100.0000"),
    )
    db.commit()

    service = BatchAllocationService(db)
    result = service.allocate(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        requested_quantity=Decimal("35.0000"),
        commit=True,
    )

    db.refresh(batch)
    # Quantity must remain exactly the total received
    assert batch.quantity == Decimal("100.0000")
    # remaining_quantity must decrease by allocated quantity
    assert batch.remaining_quantity == Decimal("65.0000")
    assert result.allocated_quantity == Decimal("35.0000")
    assert len(result.allocations) == 1
    assert result.allocations[0].remaining_quantity_after == Decimal("65.0000")


# =============================================================================
# 2. FIFO Ordering Tests
# =============================================================================
def test_fifo_ordering_oldest_first_and_deterministic_id_tiebreaker(db):
    """Oldest batch by created_at selected first; id used as tie-breaker."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_expiry=False)

    base_time = datetime(2026, 1, 1, 10, 0, 0)
    # Batch 1: Created at base_time
    b1 = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-FIFO-1",
        quantity=Decimal("10.0000"),
        created_at=base_time,
    )
    # Batch 2: Created at base_time + 1 day
    b2 = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-FIFO-2",
        quantity=Decimal("20.0000"),
        created_at=base_time + timedelta(days=1),
    )
    # Batch 3: Created at base_time (same as B1, but higher id)
    b3 = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-FIFO-3",
        quantity=Decimal("15.0000"),
        created_at=base_time,
    )
    db.commit()

    service = BatchAllocationService(db)
    # Request 22 units: Should take 10 from B1, then 12 from B3 (same time, but B1.id < B3.id), then 0 from B2
    result = service.allocate(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        requested_quantity=Decimal("22.0000"),
        strategy="FIFO",
        commit=True,
    )

    assert result.allocated_quantity == Decimal("22.0000")
    assert len(result.allocations) == 2
    assert result.allocations[0].batch_id == b1.id
    assert result.allocations[0].allocated_quantity == Decimal("10.0000")
    assert result.allocations[1].batch_id == b3.id
    assert result.allocations[1].allocated_quantity == Decimal("12.0000")

    db.refresh(b1)
    db.refresh(b2)
    db.refresh(b3)
    assert b1.remaining_quantity == Decimal("0.0000")
    assert b3.remaining_quantity == Decimal("3.0000")
    assert b2.remaining_quantity == Decimal("20.0000")


# =============================================================================
# 3. FEFO Ordering Tests
# =============================================================================
def test_fefo_ordering_earliest_expiry_first_and_excludes_expired(db):
    """FEFO selects earliest expiry, excludes expired batches, and places no-expiry last."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_expiry=True)

    today = date.today()
    # Expired batch: yesterday (MUST BE EXCLUDED)
    b_expired = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-EXP",
        quantity=Decimal("50.0000"),
        expiry_date=today - timedelta(days=1),
    )
    # Batch with early expiry: today + 10 days
    b_early = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-EARLY",
        quantity=Decimal("15.0000"),
        expiry_date=today + timedelta(days=10),
    )
    # Batch with later expiry: today + 30 days
    b_late = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-LATE",
        quantity=Decimal("20.0000"),
        expiry_date=today + timedelta(days=30),
    )
    # Batch with no expiry date (should come after dated batches)
    b_no_exp = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-NOEXP",
        quantity=Decimal("30.0000"),
        expiry_date=None,
    )
    db.commit()

    service = BatchAllocationService(db)
    # Request 25 units: Should take 15 from B-EARLY, then 10 from B-LATE. B-EXP must be untouched!
    result = service.allocate(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        requested_quantity=Decimal("25.0000"),
        commit=True,
    )

    assert result.strategy_used == "FEFO"
    assert len(result.allocations) == 2
    assert result.allocations[0].batch_id == b_early.id
    assert result.allocations[0].allocated_quantity == Decimal("15.0000")
    assert result.allocations[1].batch_id == b_late.id
    assert result.allocations[1].allocated_quantity == Decimal("10.0000")

    db.refresh(b_expired)
    db.refresh(b_early)
    db.refresh(b_late)
    db.refresh(b_no_exp)

    # Expired batch was not consumed
    assert b_expired.remaining_quantity == Decimal("50.0000")
    assert b_early.remaining_quantity == Decimal("0.0000")
    assert b_late.remaining_quantity == Decimal("10.0000")
    assert b_no_exp.remaining_quantity == Decimal("30.0000")


def test_fefo_no_expiry_batches_allocated_after_dated_batches(db):
    """When dated batches are depleted, FEFO allocates from no-expiry batches."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id, track_expiry=True)
    today = date.today()

    b_dated = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-DATED",
        quantity=Decimal("5.0000"),
        expiry_date=today + timedelta(days=5),
    )
    b_undated = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-UNDATED",
        quantity=Decimal("10.0000"),
        expiry_date=None,
    )
    db.commit()

    service = BatchAllocationService(db)
    result = service.allocate(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        requested_quantity=Decimal("8.0000"),
        commit=True,
    )

    assert len(result.allocations) == 2
    assert result.allocations[0].batch_id == b_dated.id
    assert result.allocations[0].allocated_quantity == Decimal("5.0000")
    assert result.allocations[1].batch_id == b_undated.id
    assert result.allocations[1].allocated_quantity == Decimal("3.0000")


# =============================================================================
# 4. Variant Isolation Tests
# =============================================================================
def test_variant_isolation_strictly_allocates_variant_batches(db):
    """Variant-specific allocation uses only variant batches; product fallback is rejected."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    var_red = make_variant(db, tenant.id, product.id, name="Red")
    var_blue = make_variant(db, tenant.id, product.id, name="Blue")

    # Product-level batch
    b_prod = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-PROD",
        quantity=Decimal("100.0000"),
        variant_id=None,
    )
    # Red variant batch
    b_red = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-RED",
        quantity=Decimal("10.0000"),
        variant_id=var_red.id,
    )
    # Blue variant batch
    b_blue = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-BLUE",
        quantity=Decimal("20.0000"),
        variant_id=var_blue.id,
    )
    db.commit()

    service = BatchAllocationService(db)
    # Allocating for Red: Should take from B-RED only
    res = service.allocate(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        variant_id=var_red.id,
        requested_quantity=Decimal("5.0000"),
        commit=True,
    )
    assert len(res.allocations) == 1
    assert res.allocations[0].batch_id == b_red.id

    db.refresh(b_red)
    db.refresh(b_blue)
    db.refresh(b_prod)
    assert b_red.remaining_quantity == Decimal("5.0000")
    assert b_blue.remaining_quantity == Decimal("20.0000")
    assert b_prod.remaining_quantity == Decimal("100.0000")

    # Requesting more than B-RED has: Must FAIL, no silent fallback to B-PROD!
    with pytest.raises(InsufficientStockException):
        service.allocate(
            tenant_id=tenant.id,
            store_id=store.id,
            product_id=product.id,
            variant_id=var_red.id,
            requested_quantity=Decimal("10.0000"),  # Only 5 left
            commit=True,
        )


def test_product_level_batches_allocated_only_when_variant_is_none(db):
    """When variant_id=None, only product-level batches (variant_id=None) are allocated."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)
    variant = make_variant(db, tenant.id, product.id)

    b_var = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-VAR-ONLY",
        quantity=Decimal("50.0000"),
        variant_id=variant.id,
    )
    b_prod = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-PROD-ONLY",
        quantity=Decimal("15.0000"),
        variant_id=None,
    )
    db.commit()

    service = BatchAllocationService(db)
    # Allocating with variant_id=None: Should only consume B-PROD-ONLY
    res = service.allocate(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        variant_id=None,
        requested_quantity=Decimal("10.0000"),
        commit=True,
    )
    assert len(res.allocations) == 1
    assert res.allocations[0].batch_id == b_prod.id

    # Trying to allocate 10 more with variant_id=None must fail because only 5 left in product batch
    with pytest.raises(InsufficientStockException):
        service.allocate(
            tenant_id=tenant.id,
            store_id=store.id,
            product_id=product.id,
            variant_id=None,
            requested_quantity=Decimal("10.0000"),
            commit=True,
        )


# =============================================================================
# 5. Tenant and Store Isolation Tests
# =============================================================================
def test_cross_tenant_allocation_blocked(db):
    """Attempting to allocate stock from another tenant is blocked."""
    t1 = make_tenant(db, "Tenant 1")
    t2 = make_tenant(db, "Tenant 2")
    s1 = make_store(db, t1.id)
    s2 = make_store(db, t2.id)
    p1 = make_product(db, t1.id)
    b1 = make_batch(db, t1.id, s1.id, p1.id, "B-T1", quantity=Decimal("50.0000"))
    db.commit()

    service = BatchAllocationService(db)
    # T2 trying to allocate T1's product -> 404 / NotFoundException
    with pytest.raises(NotFoundException):
        service.allocate(
            tenant_id=t2.id,
            store_id=s2.id,
            product_id=p1.id,
            requested_quantity=Decimal("10.0000"),
        )


def test_cross_store_allocation_blocked(db):
    """Stock in Store 1 cannot be allocated when requesting from Store 2."""
    tenant = make_tenant(db)
    s1 = make_store(db, tenant.id, "Store Alpha")
    s2 = make_store(db, tenant.id, "Store Beta")
    product = make_product(db, tenant.id)
    # Batch exists only in Store 1
    b1 = make_batch(db, tenant.id, s1.id, product.id, "B-S1", quantity=Decimal("50.0000"))
    db.commit()

    service = BatchAllocationService(db)
    # Request from Store 2 must raise InsufficientStockException
    with pytest.raises(InsufficientStockException):
        service.allocate(
            tenant_id=tenant.id,
            store_id=s2.id,
            product_id=product.id,
            requested_quantity=Decimal("10.0000"),
        )


# =============================================================================
# 6. Decimal Precision Tests
# =============================================================================
def test_decimal_precision_preserves_4_decimals(db):
    """Fractional Decimal quantities are handled without rounding or float conversion."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)

    b1 = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-DEC",
        quantity=Decimal("12.5555"),
    )
    db.commit()

    service = BatchAllocationService(db)
    result = service.allocate(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        requested_quantity=Decimal("5.1234"),
        commit=True,
    )

    assert result.allocated_quantity == Decimal("5.1234")
    db.refresh(b1)
    assert b1.remaining_quantity == Decimal("7.4321")
    assert b1.quantity == Decimal("12.5555")


# =============================================================================
# 7. Lock-Free Preview Tests
# =============================================================================
def test_preview_is_read_only_and_causes_no_side_effects(db):
    """Preview simulates allocation without changing DB rows or adding movements."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)

    b1 = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-PREV",
        quantity=Decimal("20.0000"),
    )
    db.commit()

    movements_before = db.query(StockMovement).count()
    service = BatchAllocationService(db)
    preview = service.preview_allocation(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        requested_quantity=Decimal("8.0000"),
    )

    assert preview.allocated_quantity == Decimal("8.0000")
    assert len(preview.allocations) == 1
    assert preview.allocations[0].remaining_quantity_after == Decimal("12.0000")

    db.refresh(b1)
    # Database batch remaining quantity MUST NOT change
    assert b1.remaining_quantity == Decimal("20.0000")
    # No StockMovement created
    assert db.query(StockMovement).count() == movements_before
    # No Inventory record created
    inv = db.execute(
        select(Inventory).where(
            Inventory.tenant_id == tenant.id,
            Inventory.batch_id == b1.id,
        )
    ).scalar_one_or_none()
    assert inv is None


# =============================================================================
# 8. Inventory Synchronization Tests
# =============================================================================
def test_inventory_mirror_synchronized_on_allocation(db):
    """Inventory row with batch_id mirrors ProductBatch.remaining_quantity."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)

    b1 = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-SYNC",
        quantity=Decimal("40.0000"),
    )
    db.commit()

    service = BatchAllocationService(db)
    service.allocate(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        requested_quantity=Decimal("15.0000"),
        commit=True,
    )

    inv = db.execute(
        select(Inventory).where(
            Inventory.tenant_id == tenant.id,
            Inventory.store_id == store.id,
            Inventory.product_id == product.id,
            Inventory.batch_id == b1.id,
        )
    ).scalar_one_or_none()

    assert inv is not None
    assert inv.quantity == Decimal("25.0000")


# =============================================================================
# 9. Stock Movement Creation Tests
# =============================================================================
def test_stock_movement_created_with_allocation_type(db):
    """Stock movement record is created with movement_type=allocation and exact metadata."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)

    b1 = make_batch(
        db,
        tenant.id,
        store.id,
        product.id,
        "B-MOV",
        quantity=Decimal("50.0000"),
    )
    db.commit()

    service = BatchAllocationService(db)
    service.allocate(
        tenant_id=tenant.id,
        store_id=store.id,
        product_id=product.id,
        requested_quantity=Decimal("18.0000"),
        notes="Order-123 reservation",
        reference_id=123,
        reference_type="ORDER",
        commit=True,
    )

    movement = db.execute(
        select(StockMovement).where(
            StockMovement.tenant_id == tenant.id,
            StockMovement.batch_id == b1.id,
        )
    ).scalar_one_or_none()

    assert movement is not None
    assert movement.movement_type == StockMovementType.ALLOCATION.value
    assert movement.quantity == Decimal("18.0000")
    assert movement.product_id == product.id
    assert movement.store_id == store.id
    assert movement.reference_id == 123
    assert movement.reference_type == "ORDER"
    assert movement.notes == "Order-123 reservation"


# =============================================================================
# 10. Insufficient Stock Rollback Tests
# =============================================================================
def test_insufficient_stock_raises_and_rolls_back_atomically(db):
    """If stock is insufficient across batches, entire transaction rolls back."""
    tenant = make_tenant(db)
    store = make_store(db, tenant.id)
    product = make_product(db, tenant.id)

    b1 = make_batch(db, tenant.id, store.id, product.id, "B-ROLL-1", quantity=Decimal("4.0000"))
    b2 = make_batch(db, tenant.id, store.id, product.id, "B-ROLL-2", quantity=Decimal("3.0000"))
    db.commit()

    service = BatchAllocationService(db)
    # Requested 10, total available 7 -> must raise and leave both at initial values
    with pytest.raises(InsufficientStockException):
        service.allocate(
            tenant_id=tenant.id,
            store_id=store.id,
            product_id=product.id,
            requested_quantity=Decimal("10.0000"),
            commit=True,
        )

    db.refresh(b1)
    db.refresh(b2)
    assert b1.remaining_quantity == Decimal("4.0000")
    assert b2.remaining_quantity == Decimal("3.0000")

    # No movements created
    movements = db.execute(
        select(StockMovement).where(StockMovement.tenant_id == tenant.id)
    ).scalars().all()
    assert len(movements) == 0


# =============================================================================
# 11. Concurrency Safety Tests
# =============================================================================
def test_concurrency_no_oversell_using_independent_sessions():
    """Concurrent allocations using independent database sessions prevent overselling."""
    setup_db = SessionLocal()
    tenant = make_tenant(setup_db)
    store = make_store(setup_db, tenant.id)
    product = make_product(setup_db, tenant.id)
    batch = make_batch(
        setup_db,
        tenant.id,
        store.id,
        product.id,
        "B-CONCUR",
        quantity=Decimal("10.0000"),
    )
    setup_db.commit()
    batch_id = batch.id
    tenant_id = tenant.id
    store_id = store.id
    product_id = product.id
    setup_db.close()

    results = {"success": 0, "blocked": 0}
    errors = []

    def allocate_worker():
        worker_session = SessionLocal()
        try:
            worker_service = BatchAllocationService(worker_session)
            worker_service.allocate(
                tenant_id=tenant_id,
                store_id=store_id,
                product_id=product_id,
                requested_quantity=Decimal("7.0000"),
                commit=True,
            )
            results["success"] += 1
        except (InsufficientStockException, ConcurrencyException):
            results["blocked"] += 1
        except Exception as e:
            errors.append(e)
        finally:
            worker_session.close()

    # Launch two concurrent threads attempting to allocate 7 units each from a 10-unit batch
    t1 = threading.Thread(target=allocate_worker)
    t2 = threading.Thread(target=allocate_worker)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(errors) == 0, f"Unexpected errors during concurrent allocation: {errors}"
    # Exactly one thread succeeds, and the other is safely blocked (no overselling)
    assert results["success"] == 1
    assert results["blocked"] == 1

    verify_db = SessionLocal()
    final_batch = verify_db.get(ProductBatch, batch_id)
    assert final_batch.quantity == Decimal("10.0000")
    assert final_batch.remaining_quantity == Decimal("3.0000")
    verify_db.close()
