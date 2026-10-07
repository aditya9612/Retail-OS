from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from sqlalchemy.exc import DatabaseError, OperationalError

from app.constants import permissions
from app.core.exceptions import AppException, ForbiddenException, NotFoundException
from app.models.inventory import Inventory, StockMovement
from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.product_variant import ProductVariant
from app.utils.constants import StockMovementType


class InsufficientStockException(AppException):
    def __init__(self, detail: str = "Insufficient stock available for allocation"):
        super().__init__(detail=detail, status_code=400)


class ConcurrencyException(AppException):
    def __init__(self, detail: str = "Concurrency conflict: resource is locked or under concurrent modification"):
        super().__init__(detail=detail, status_code=409)


@dataclass
class BatchAllocationItem:
    batch_id: int
    batch_number: str
    allocated_quantity: Decimal
    unit_cost: Decimal
    expiry_date: Optional[date] = None
    remaining_quantity_after: Optional[Decimal] = None

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "batch_number": self.batch_number,
            "allocated_quantity": str(self.allocated_quantity),
            "unit_cost": str(self.unit_cost),
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "remaining_quantity_after": str(self.remaining_quantity_after)
            if self.remaining_quantity_after is not None
            else None,
        }


@dataclass
class BatchAllocationResult:
    tenant_id: int
    store_id: int
    product_id: int
    variant_id: Optional[int]
    requested_quantity: Decimal
    allocated_quantity: Decimal
    allocations: List[BatchAllocationItem] = field(default_factory=list)
    strategy_used: str = "FIFO"

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "store_id": self.store_id,
            "product_id": self.product_id,
            "variant_id": self.variant_id,
            "requested_quantity": str(self.requested_quantity),
            "allocated_quantity": str(self.allocated_quantity),
            "strategy_used": self.strategy_used,
            "allocations": [a.to_dict() for a in self.allocations],
        }


class BatchAllocationService:
    def __init__(self, db: Session, user: Optional[Any] = None):
        self.db = db
        self.user = user

    # -------------------------------------------------------------------------
    # Isolation and Security Helpers
    # -------------------------------------------------------------------------
    def _check_permission(self, permission: str) -> None:
        if not self.user:
            return
        perms = getattr(self.user.role, "permissions", []) if getattr(self.user, "role", None) else []
        if "*" in perms or permission in perms:
            return
        raise ForbiddenException(f"Missing permission: {permission}")

    def _validate_tenant(self, tenant_id: int) -> None:
        if self.user and getattr(self.user, "tenant_id", None) is not None:
            if self.user.tenant_id != tenant_id:
                raise ForbiddenException("Tenant mismatch")

    def _ensure_product(self, product_id: int, tenant_id: int) -> Product:
        product = self.db.get(Product, product_id)
        if not product or product.tenant_id != tenant_id:
            raise NotFoundException("Product not found or tenant mismatch")
        return product

    def _ensure_variant(
        self, variant_id: Optional[int], product_id: int, tenant_id: int
    ) -> Optional[ProductVariant]:
        if variant_id is None:
            return None
        variant = self.db.get(ProductVariant, variant_id)
        if not variant or variant.product_id != product_id or variant.tenant_id != tenant_id:
            raise NotFoundException("Variant not found or does not belong to product/tenant")
        return variant

    def _determine_strategy(
        self, product: Product, requested_strategy: Optional[str] = "AUTO"
    ) -> str:
        strat = (requested_strategy or "AUTO").upper()
        if strat == "AUTO":
            if getattr(product, "track_expiry", False):
                return "FEFO"
            return "FIFO"
        if strat in ("FIFO", "FEFO"):
            return strat
        raise AppException(f"Unsupported allocation strategy: {requested_strategy}")

    # -------------------------------------------------------------------------
    # Batch Query Builder
    # -------------------------------------------------------------------------
    def _get_eligible_batches_query(
        self,
        *,
        tenant_id: int,
        store_id: int,
        product_id: int,
        variant_id: Optional[int],
        strategy: str,
        for_update: bool = False,
    ):
        today = date.today()
        conditions = [
            ProductBatch.tenant_id == tenant_id,
            ProductBatch.store_id == store_id,
            ProductBatch.product_id == product_id,
            ProductBatch.is_active.is_(True),
            ProductBatch.remaining_quantity > 0,
            # Expired batches MUST NOT be allocated under any strategy
            or_(ProductBatch.expiry_date.is_(None), ProductBatch.expiry_date >= today),
        ]

        # Strict variant isolation: no silent fallback to product-level batches
        if variant_id is not None:
            conditions.append(ProductBatch.variant_id == variant_id)
        else:
            conditions.append(ProductBatch.variant_id.is_(None))

        stmt = select(ProductBatch).where(*conditions)

        if strategy == "FEFO":
            # 1. Earliest valid expiry date
            # 2. No-expiry batches after dated batches
            # 3. created_at ASC
            # 4. id ASC
            stmt = stmt.order_by(
                case((ProductBatch.expiry_date.is_(None), 1), else_=0).asc(),
                ProductBatch.expiry_date.asc(),
                ProductBatch.created_at.asc(),
                ProductBatch.id.asc(),
            )
        else:  # FIFO
            # 1. created_at ASC
            # 2. id ASC
            stmt = stmt.order_by(
                ProductBatch.created_at.asc(),
                ProductBatch.id.asc(),
            )

        if for_update:
            stmt = stmt.with_for_update()

        return stmt

    # -------------------------------------------------------------------------
    # Inventory Mirror Synchronization
    # -------------------------------------------------------------------------
    def _sync_inventory_batch_mirror(
        self,
        *,
        tenant_id: int,
        store_id: int,
        product_id: int,
        batch: ProductBatch,
        for_update: bool = True,
    ) -> Inventory:
        stmt = select(Inventory).where(
            Inventory.tenant_id == tenant_id,
            Inventory.store_id == store_id,
            Inventory.product_id == product_id,
            Inventory.batch_id == batch.id,
        )
        if for_update:
            stmt = stmt.with_for_update()

        inv = self.db.execute(stmt).scalar_one_or_none()
        if inv:
            inv.quantity = batch.remaining_quantity
        else:
            inv = Inventory(
                tenant_id=tenant_id,
                store_id=store_id,
                product_id=product_id,
                batch_id=batch.id,
                quantity=batch.remaining_quantity,
            )
            self.db.add(inv)
        self.db.flush()
        return inv

    # -------------------------------------------------------------------------
    # Public Core API
    # -------------------------------------------------------------------------
    def preview_allocation(
        self,
        *,
        tenant_id: int,
        store_id: int,
        product_id: int,
        requested_quantity: Decimal,
        variant_id: Optional[int] = None,
        strategy: Optional[str] = "AUTO",
    ) -> BatchAllocationResult:
        """Lock-free, read-only preview of batch allocation."""
        self._check_permission(permissions.BATCHES_READ)
        self._validate_tenant(tenant_id)

        if not isinstance(requested_quantity, Decimal):
            requested_quantity = Decimal(str(requested_quantity))
        if requested_quantity <= Decimal("0"):
            raise AppException("Requested quantity must be greater than zero")

        product = self._ensure_product(product_id, tenant_id)
        self._ensure_variant(variant_id, product_id, tenant_id)

        active_strategy = self._determine_strategy(product, strategy)

        # Lock-free query
        stmt = self._get_eligible_batches_query(
            tenant_id=tenant_id,
            store_id=store_id,
            product_id=product_id,
            variant_id=variant_id,
            strategy=active_strategy,
            for_update=False,
        )
        batches = self.db.execute(stmt).scalars().all()

        allocations: List[BatchAllocationItem] = []
        remaining_needed = requested_quantity
        total_allocated = Decimal("0")

        for batch in batches:
            if remaining_needed <= Decimal("0"):
                break
            to_alloc = min(batch.remaining_quantity, remaining_needed)
            allocations.append(
                BatchAllocationItem(
                    batch_id=batch.id,
                    batch_number=batch.batch_number,
                    allocated_quantity=to_alloc,
                    unit_cost=batch.unit_cost,
                    expiry_date=batch.expiry_date,
                    remaining_quantity_after=batch.remaining_quantity - to_alloc,
                )
            )
            remaining_needed -= to_alloc
            total_allocated += to_alloc

        if remaining_needed > Decimal("0"):
            raise InsufficientStockException(
                f"Insufficient stock for product {product_id}. "
                f"Requested: {requested_quantity}, Available: {total_allocated}"
            )

        return BatchAllocationResult(
            tenant_id=tenant_id,
            store_id=store_id,
            product_id=product_id,
            variant_id=variant_id,
            requested_quantity=requested_quantity,
            allocated_quantity=total_allocated,
            allocations=allocations,
            strategy_used=active_strategy,
        )

    def allocate(
        self,
        *,
        tenant_id: int,
        store_id: int,
        product_id: int,
        requested_quantity: Decimal,
        variant_id: Optional[int] = None,
        strategy: Optional[str] = "AUTO",
        notes: Optional[str] = None,
        reference_id: Optional[int] = None,
        reference_type: Optional[str] = None,
        commit: bool = False,
    ) -> BatchAllocationResult:
        """Atomically allocate stock from product batches using row locks."""
        self._check_permission(permissions.BATCHES_WRITE)
        self._validate_tenant(tenant_id)

        if not isinstance(requested_quantity, Decimal):
            requested_quantity = Decimal(str(requested_quantity))
        if requested_quantity <= Decimal("0"):
            raise AppException("Requested quantity must be greater than zero")

        product = self._ensure_product(product_id, tenant_id)
        self._ensure_variant(variant_id, product_id, tenant_id)

        active_strategy = self._determine_strategy(product, strategy)

        # Atomic execution protected by savepoint
        try:
            with self.db.begin_nested():
                stmt = self._get_eligible_batches_query(
                    tenant_id=tenant_id,
                    store_id=store_id,
                    product_id=product_id,
                    variant_id=variant_id,
                    strategy=active_strategy,
                    for_update=True,
                )
                batches = self.db.execute(stmt).scalars().all()

                total_available = sum((b.remaining_quantity for b in batches), Decimal("0"))
                if total_available < requested_quantity:
                    raise InsufficientStockException(
                        f"Insufficient stock for product {product_id}. "
                        f"Requested: {requested_quantity}, Available: {total_available}"
                    )

                allocations: List[BatchAllocationItem] = []
                remaining_needed = requested_quantity

                for batch in batches:
                    if remaining_needed <= Decimal("0"):
                        break

                    to_alloc = min(batch.remaining_quantity, remaining_needed)
                    # CRITICAL: Mutate only remaining_quantity; never touch batch.quantity!
                    batch.remaining_quantity -= to_alloc
                    remaining_needed -= to_alloc

                    # Synchronize Inventory batch mirror
                    self._sync_inventory_batch_mirror(
                        tenant_id=tenant_id,
                        store_id=store_id,
                        product_id=product_id,
                        batch=batch,
                        for_update=True,
                    )

                    # Record StockMovement
                    movement = StockMovement(
                        tenant_id=tenant_id,
                        store_id=store_id,
                        product_id=product_id,
                        batch_id=batch.id,
                        movement_type=StockMovementType.ALLOCATION.value,
                        quantity=to_alloc,
                        previous_stock=batch.remaining_quantity + to_alloc,
                        new_stock=batch.remaining_quantity,
                        reference_id=reference_id,
                        reference_type=reference_type or "ALLOCATION",
                        notes=notes or f"Batch allocation for batch {batch.batch_number}",
                        created_by=getattr(self.user, "id", None) if self.user else None,
                    )
                    self.db.add(movement)

                    allocations.append(
                        BatchAllocationItem(
                            batch_id=batch.id,
                            batch_number=batch.batch_number,
                            allocated_quantity=to_alloc,
                            unit_cost=batch.unit_cost,
                            expiry_date=batch.expiry_date,
                            remaining_quantity_after=batch.remaining_quantity,
                        )
                    )

                if remaining_needed > Decimal("0"):
                    raise InsufficientStockException(
                        f"Could not satisfy requested allocation quantity. Remaining needed: {remaining_needed}"
                    )

                self.db.flush()

            if commit:
                self.db.commit()

            return BatchAllocationResult(
                tenant_id=tenant_id,
                store_id=store_id,
                product_id=product_id,
                variant_id=variant_id,
                requested_quantity=requested_quantity,
                allocated_quantity=requested_quantity,
                allocations=allocations,
                strategy_used=active_strategy,
            )
        except AppException:
            raise
        except (OperationalError, DatabaseError) as e:
            err_msg = str(e).lower()
            if "locked" in err_msg or "deadlock" in err_msg or "lock" in err_msg:
                raise ConcurrencyException("Resource is locked by another transaction. Please retry.") from e
            raise AppException(f"Database error during allocation: {str(e)}") from e
        except Exception as e:
            raise AppException(f"Unexpected error during allocation: {str(e)}") from e
