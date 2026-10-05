import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.product_batch import ProductBatch
from app.repositories.product_batch_repo import ProductBatchRepository
from app.core.security import require_permission
from app.constants import permissions


class ProductBatchService:
    def __init__(self, db: Session, user):
        self.db = db
        self.user = user
        self.repo = ProductBatchRepository(db)

    # ---------------------------------------------------------------------
    # Helper validation
    # ---------------------------------------------------------------------
    def _ensure_product(self, product_id: int) -> Product:
        product = self.db.get(Product, product_id)
        if not product or product.tenant_id != self.user.tenant_id:
            raise ValueError("Product not found or tenant mismatch")
        return product

    def _ensure_variant(self, variant_id: Optional[int], product_id: int) -> Optional[ProductVariant]:
        if variant_id is None:
            return None
        variant = self.db.get(ProductVariant, variant_id)
        if not variant or variant.product_id != product_id or variant.tenant_id != self.user.tenant_id:
            raise ValueError("Variant does not belong to product/tenant")
        return variant

    # ---------------------------------------------------------------------
    # CRUD API operations
    # ---------------------------------------------------------------------
    @require_permission(permissions.BATCHES_WRITE)
    def create(
        self,
        *,
        tenant_id: int,
        store_id: int,
        product_id: int,
        variant_id: Optional[int] = None,
        batch_number: str,
        manufacturing_date: Optional[datetime.date] = None,
        expiry_date: Optional[datetime.date] = None,
        unit_cost: Decimal,
        quantity: Decimal,
    ) -> ProductBatch:
        # Isolation checks
        if tenant_id != self.user.tenant_id:
            raise PermissionError("Tenant mismatch")
        product = self._ensure_product(product_id)
        self._ensure_variant(variant_id, product_id)

        if quantity < 0 or unit_cost < 0:
            raise ValueError("quantity and unit_cost must be non‑negative")
        if expiry_date and manufacturing_date and expiry_date < manufacturing_date:
            raise ValueError("expiry_date cannot be earlier than manufacturing_date")

        batch = ProductBatch(
            tenant_id=tenant_id,
            store_id=store_id,
            product_id=product_id,
            variant_id=variant_id,
            batch_number=batch_number,
            manufacturing_date=manufacturing_date,
            expiry_date=expiry_date,
            unit_cost=unit_cost,
            quantity=quantity,
            remaining_quantity=quantity,
            is_active=True,
        )
        try:
            self.repo.create(batch)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError("Batch with same unique key already exists") from exc
        return batch

    @require_permission(permissions.BATCHES_READ)
    def get(self, batch_id: int) -> ProductBatch:
        batch = self.repo.get_by_id(batch_id)
        if not batch or batch.tenant_id != self.user.tenant_id:
            raise ValueError("Batch not found")
        return batch

    @require_permission(permissions.BATCHES_READ)
    def list(
        self,
        *,
        tenant_id: int,
        store_id: int,
        product_id: Optional[int] = None,
        variant_id: Optional[int] = None,
        batch_number: Optional[str] = None,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[ProductBatch]:
        batches = self.repo.list(
            tenant_id=tenant_id,
            store_id=store_id,
            product_id=product_id,
            variant_id=variant_id,
            batch_number=batch_number,
            offset=offset,
            limit=limit,
        )
        if status:
            batches = [b for b in batches if b.status == status.upper()]
        return batches

    @require_permission(permissions.BATCHES_WRITE)
    def update(self, batch_id: int, update_data: dict) -> ProductBatch:
        batch = self.get(batch_id)
        # Immutable fields protection
        immutable = {"tenant_id", "store_id", "product_id", "variant_id", "quantity", "remaining_quantity"}
        if any(k in immutable for k in update_data):
            raise ValueError("Attempt to modify immutable fields")
        if "expiry_date" in update_data and "manufacturing_date" in update_data:
            md = update_data.get("manufacturing_date")
            ed = update_data.get("expiry_date")
            if md and ed and ed < md:
                raise ValueError("expiry_date cannot be earlier than manufacturing_date")
        if "unit_cost" in update_data and update_data["unit_cost"] < 0:
            raise ValueError("unit_cost must be non‑negative")
        self.repo.update(batch, update_data)
        self.db.commit()
        return batch

    @require_permission(permissions.BATCHES_WRITE)
    def deactivate(self, batch_id: int) -> None:
        batch = self.get(batch_id)
        if batch.remaining_quantity > 0:
            raise ValueError("Cannot deactivate batch with remaining stock")
        batch.is_active = False
        self.db.commit()

    # ---------------------------------------------------------------------
    # get_or_create_by_number – concurrency‑safe
    # ---------------------------------------------------------------------
    @require_permission(permissions.BATCHES_WRITE)
    def get_or_create_by_number(
        self,
        *,
        tenant_id: int,
        store_id: int,
        product_id: int,
        variant_id: Optional[int] = None,
        batch_number: str,
        manufacturing_date: Optional[datetime.date] = None,
        expiry_date: Optional[datetime.date] = None,
        unit_cost: Optional[Decimal] = None,
        quantity: Decimal,
    ) -> ProductBatch:
        with self.db.begin():
            # SELECT … FOR UPDATE
            stmt = select(ProductBatch).where(
                ProductBatch.tenant_id == tenant_id,
                ProductBatch.store_id == store_id,
                ProductBatch.product_id == product_id,
                ProductBatch.batch_number == batch_number,
            )
            if variant_id is None:
                stmt = stmt.where(ProductBatch.variant_id.is_(None))
            else:
                stmt = stmt.where(ProductBatch.variant_id == variant_id)
            existing = self.db.execute(stmt.with_for_update()).scalar_one_or_none()

            if existing:
                # Validate immutable meta‑data – reject if conflict
                if (
                    existing.manufacturing_date
                    and manufacturing_date
                    and existing.manufacturing_date != manufacturing_date
                ) or (
                    existing.expiry_date and expiry_date and existing.expiry_date != expiry_date
                ):
                    raise ValueError("Conflicting manufacturing/expiry dates for existing batch")
                if unit_cost is not None and existing.unit_cost != unit_cost:
                    raise ValueError("Conflicting unit_cost for existing batch")
                # Update quantities atomically
                existing.quantity += quantity
                existing.remaining_quantity += quantity
                self.db.flush()
                return existing

            # No row – attempt insert
            batch = ProductBatch(
                tenant_id=tenant_id,
                store_id=store_id,
                product_id=product_id,
                variant_id=variant_id,
                batch_number=batch_number,
                manufacturing_date=manufacturing_date,
                expiry_date=expiry_date,
                unit_cost=unit_cost or Decimal("0"),
                quantity=quantity,
                remaining_quantity=quantity,
                is_active=True,
            )
            self.db.add(batch)
            try:
                self.db.flush()
            except IntegrityError:
                # Another concurrent transaction inserted the same batch – fetch it and add quantity
                self.db.rollback()
                existing = self.repo.get_by_number(
                    tenant_id, store_id, product_id, batch_number, variant_id
                )
                if not existing:
                    raise RuntimeError("Race condition handling failed")
                existing.quantity += quantity
                existing.remaining_quantity += quantity
                self.db.flush()
                return existing
            return batch

    # ---------------------------------------------------------------------
    # Convenience queries
    # ---------------------------------------------------------------------
    @require_permission(permissions.BATCHES_READ)
    def expired(self, *, tenant_id: int, store_id: int) -> List[ProductBatch]:
        today = datetime.date.today()
        stmt = select(ProductBatch).where(
            ProductBatch.tenant_id == tenant_id,
            ProductBatch.store_id == store_id,
            ProductBatch.expiry_date != None,
            ProductBatch.expiry_date < today,
            ProductBatch.is_active == True,
        )
        return self.db.execute(stmt).scalars().all()

    @require_permission(permissions.BATCHES_READ)
    def near_expiry(self, *, tenant_id: int, store_id: int, days: int = 30) -> List[ProductBatch]:
        today = datetime.date.today()
        horizon = today + datetime.timedelta(days=days)
        stmt = select(ProductBatch).where(
            ProductBatch.tenant_id == tenant_id,
            ProductBatch.store_id == store_id,
            ProductBatch.expiry_date != None,
            ProductBatch.expiry_date >= today,
            ProductBatch.expiry_date <= horizon,
            ProductBatch.is_active == True,
        )
        return self.db.execute(stmt).scalars().all()
