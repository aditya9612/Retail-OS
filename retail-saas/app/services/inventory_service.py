from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import distinct, func, text
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import AppException, NotFoundException
from app.models.category import Category
from app.models.document_sequence import DocumentSequence
from app.models.inventory import Inventory, StockMovement
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.store import Store
from app.models.store_transfer import StoreTransfer
from app.models.supplier import Supplier
from app.schemas.inventory import (
    BulkInventoryAdjustmentRequest,
    InventoryAdjustmentRequest,
    StockInRequest,
    StockOutRequest,
    StockTransferRequest,
)
from app.utils.constants import StockMovementType
from app.utils.helpers import cache_delete_pattern


class InventoryService:
    def __init__(self, db: Session):
        self.db = db

    def _generate_movement_reference(self, tenant_id: int, prefix: str) -> tuple[int, str]:
        year = datetime.utcnow().year
        doc_type = f"stock_{prefix.lower()}"
        bind = self.db.get_bind()
        if bind.dialect.name == "mysql":
            self.db.execute(
                text(
                    "INSERT INTO document_sequences (tenant_id, doc_type, year, last_number, created_at, updated_at) "
                    "VALUES (:tenant_id, :doc_type, :year, 0, NOW(), NOW()) "
                    "ON DUPLICATE KEY UPDATE id=id"
                ),
                {"tenant_id": tenant_id, "doc_type": doc_type, "year": year},
            )
            self.db.flush()
        else:
            self.db.execute(
                text(
                    "INSERT OR IGNORE INTO document_sequences (tenant_id, doc_type, year, last_number, created_at, updated_at) "
                    "VALUES (:tenant_id, :doc_type, :year, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"tenant_id": tenant_id, "doc_type": doc_type, "year": year},
            )
            self.db.flush()

        row = (
            self.db.query(DocumentSequence)
            .filter(
                DocumentSequence.tenant_id == tenant_id,
                DocumentSequence.doc_type == doc_type,
                DocumentSequence.year == year,
            )
            .with_for_update()
            .first()
        )
        if not row:
            row = DocumentSequence(
                tenant_id=tenant_id,
                doc_type=doc_type,
                year=year,
                last_number=0,
            )
            self.db.add(row)
            self.db.flush()

        row.last_number += 1
        self.db.flush()
        return row.last_number, f"{prefix}-{year}-{row.last_number:06d}"

    def _get_product(self, tenant_id: int, product_id: int) -> Product:
        product = (
            self.db.query(Product)
            .filter(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
            )
            .first()
        )

        if not product:
            raise NotFoundException(f"Product with ID {product_id} not found")

        return product

    def _get_store(self, tenant_id: int, store_id: int, message: Optional[str] = None) -> Store:
        store = (
            self.db.query(Store)
            .filter(
                Store.id == store_id,
                Store.tenant_id == tenant_id,
            )
            .first()
        )

        if not store:
            raise NotFoundException(message or f"Store with ID {store_id} not found")

        return store

    def _get_or_create_inventory(self, tenant_id: int, store_id: int, product_id: int) -> Inventory:
        inventory = (
            self.db.query(Inventory)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.store_id == store_id,
                Inventory.product_id == product_id,
            )
            .first()
        )

        if not inventory:
            product = (
                self.db.query(Product)
                .filter(
                    Product.id == product_id,
                    Product.tenant_id == tenant_id,
                )
                .first()
            )
            min_alert = getattr(product, "min_stock_alert", None) or 5
            inventory = Inventory(
                tenant_id=tenant_id,
                store_id=store_id,
                product_id=product_id,
                quantity=0,
                min_stock_level=min_alert,
                reorder_point=min_alert,
                max_stock_level=max(min_alert * 20, 100),
            )
            self.db.add(inventory)
            self.db.flush()

        return inventory

    def stock_in(
        self,
        tenant_id: int,
        data: StockInRequest,
        commit: bool = True,
        movement_type: Optional[str] = None,
        reference_id: Optional[int] = None,
        reference_type: Optional[str] = None,
    ) -> StockMovement:
        product = self._get_product(tenant_id, data.product_id)
        self._get_store(tenant_id, data.store_id)

        if data.quantity <= 0:
            raise AppException("quantity must be greater than 0")

        if data.unit_cost is not None and data.unit_cost < Decimal("1.00"):
            raise AppException("unit_cost must be at least 1.00")

        if data.expiry_date and data.expiry_date < date.today():
            raise AppException("Expiry date cannot be in the past")

        supplier = None
        if data.supplier_id:
            supplier = (
                self.db.query(Supplier)
                .filter(
                    Supplier.id == data.supplier_id,
                    Supplier.tenant_id == tenant_id,
                )
                .first()
            )
            if not supplier:
                raise NotFoundException(f"Supplier with ID {data.supplier_id} not found")

        inventory = self._get_or_create_inventory(
            tenant_id,
            data.store_id,
            data.product_id,
        )

        previous_stock = inventory.quantity
        inventory.quantity += data.quantity
        new_stock = inventory.quantity

        if data.unit_cost is not None and data.unit_cost > Decimal("0.00"):
            product.cost_price = data.unit_cost

        batch = None
        if data.batch_number:
            from app.models.product_batch import ProductBatch
            batch = (
                self.db.query(ProductBatch)
                .filter(
                    ProductBatch.tenant_id == tenant_id,
                    ProductBatch.store_id == data.store_id,
                    ProductBatch.product_id == data.product_id,
                    ProductBatch.batch_number == data.batch_number,
                )
                .first()
            )
            if not batch:
                batch = ProductBatch(
                    tenant_id=tenant_id,
                    store_id=data.store_id,
                    product_id=data.product_id,
                    batch_number=data.batch_number,
                    expiry_date=data.expiry_date,
                    unit_cost=data.unit_cost or Decimal("0.00"),
                    quantity=data.quantity,
                    remaining_quantity=data.quantity,
                    is_active=True,
                )
                self.db.add(batch)
                self.db.flush()
            else:
                batch.quantity += data.quantity
                batch.remaining_quantity += data.quantity
                if data.expiry_date:
                    batch.expiry_date = data.expiry_date
                self.db.flush()

            inventory.batch_id = batch.id
            inventory.batch_number = data.batch_number

        if data.expiry_date:
            inventory.expiry_date = data.expiry_date

        if reference_id is not None or reference_type is not None:
            ref_id = reference_id
            ref_str = reference_type
        else:
            ref_id, ref_str = self._generate_movement_reference(tenant_id, "IN")

        movement = StockMovement(
            tenant_id=tenant_id,
            store_id=data.store_id,
            product_id=data.product_id,
            batch_id=batch.id if batch else None,
            movement_type=movement_type or StockMovementType.STOCK_IN.value,
            quantity=data.quantity,
            previous_stock=previous_stock,
            new_stock=new_stock,
            reference_id=ref_id,
            reference_type=ref_str,
            supplier_id=data.supplier_id if supplier else None,
            unit_cost=data.unit_cost,
            notes=data.notes,
        )

        if commit:
            try:
                self.db.add(movement)
                self.db.commit()
                self.db.refresh(movement)
            except Exception:
                self.db.rollback()
                raise
        else:
            self.db.add(movement)
            self.db.flush()

        movement.batch_number = data.batch_number
        movement.expiry_date = data.expiry_date
        movement.unit_cost = data.unit_cost

        cache_delete_pattern(f"inventory:{tenant_id}:*")

        return movement

    def stock_out(self, tenant_id: int, data: StockOutRequest, commit: bool = True) -> StockMovement:
        self._get_product(tenant_id, data.product_id)
        self._get_store(tenant_id, data.store_id)

        if data.quantity <= 0:
            raise AppException("quantity must be greater than 0")

        inventory = (
            self.db.query(Inventory)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.store_id == data.store_id,
                Inventory.product_id == data.product_id,
            )
            .first()
        )

        if not inventory:
            raise NotFoundException(
                f"Inventory record for product with ID {data.product_id} in store with ID {data.store_id} not found"
            )

        if inventory.quantity < data.quantity:
            raise AppException(
                f"Insufficient stock. Available: {inventory.quantity}, requested: {data.quantity}"
            )

        previous_stock = inventory.quantity
        inventory.quantity -= data.quantity
        new_stock = inventory.quantity

        ref_id, ref_str = self._generate_movement_reference(tenant_id, "OUT")

        movement = StockMovement(
            tenant_id=tenant_id,
            store_id=data.store_id,
            product_id=data.product_id,
            movement_type=StockMovementType.STOCK_OUT.value,
            quantity=data.quantity,
            previous_stock=previous_stock,
            new_stock=new_stock,
            reference_id=ref_id,
            reference_type=ref_str,
            notes=data.notes,
        )

        if commit:
            try:
                self.db.add(movement)
                self.db.commit()
                self.db.refresh(movement)
            except Exception:
                self.db.rollback()
                raise
        else:
            self.db.add(movement)
            self.db.flush()

        cache_delete_pattern(f"inventory:{tenant_id}:*")

        return movement

    def transfer_stock(self, tenant_id: int, data: StockTransferRequest) -> StockMovement:
        if data.from_store_id == data.to_store_id:
            raise AppException("from_store_id and to_store_id must be different")

        if data.quantity <= 0:
            raise AppException("quantity must be greater than 0")

        self._get_product(tenant_id, data.product_id)

        self._get_store(
            tenant_id, data.from_store_id, f"Source store with ID {data.from_store_id} not found"
        )
        self._get_store(
            tenant_id, data.to_store_id, f"Destination store with ID {data.to_store_id} not found"
        )

        from_inventory = (
            self.db.query(Inventory)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.store_id == data.from_store_id,
                Inventory.product_id == data.product_id,
            )
            .first()
        )

        if not from_inventory:
            raise NotFoundException(
                f"Source inventory not found for product with ID {data.product_id} in store with ID {data.from_store_id}"
            )

        if from_inventory.quantity < data.quantity:
            raise AppException(
                f"Insufficient stock in source store. Available: {from_inventory.quantity}, requested: {data.quantity}"
            )

        to_inventory = self._get_or_create_inventory(
            tenant_id,
            data.to_store_id,
            data.product_id,
        )

        previous_stock = from_inventory.quantity
        from_inventory.quantity -= data.quantity
        new_stock = from_inventory.quantity
        to_inventory.quantity += data.quantity

        if from_inventory.expiry_date and not to_inventory.expiry_date:
            to_inventory.expiry_date = from_inventory.expiry_date
        if from_inventory.batch_id and not to_inventory.batch_id:
            to_inventory.batch_id = from_inventory.batch_id

        ref_id, ref_str = self._generate_movement_reference(tenant_id, "TR")

        movement = StockMovement(
            tenant_id=tenant_id,
            store_id=data.from_store_id,
            product_id=data.product_id,
            batch_id=from_inventory.batch_id,
            movement_type=StockMovementType.TRANSFER.value,
            quantity=data.quantity,
            previous_stock=previous_stock,
            new_stock=new_stock,
            reference_id=ref_id,
            reference_type=ref_str,
            from_store_id=data.from_store_id,
            to_store_id=data.to_store_id,
            notes=data.notes,
        )

        try:
            self.db.add(movement)
            self.db.commit()
            self.db.refresh(movement)
        except Exception:
            self.db.rollback()
            raise

        cache_delete_pattern(f"inventory:{tenant_id}:*")

        return movement

    def get_low_stock(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ):
        if store_id is not None:
            self._get_store(
                tenant_id,
                store_id,
                f"Store with ID {store_id} not found",
            )

        query = self.db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.quantity <= Inventory.min_stock_level,
        )

        if store_id is not None:
            query = query.filter(Inventory.store_id == store_id)

        inventories = query.all()

        if not inventories:
            return {
                "success": True,
                "message": "No low-stock items found",
                "count": 0,
                "data": [],
            }

        return {
            "success": True,
            "message": "Low-stock items fetched successfully",
            "count": len(inventories),
            "data": inventories,
        }

    def list_inventory(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        product_id: Optional[int] = None,
        category_id: Optional[int] = None,
        search: Optional[str] = None,
        low_stock_only: bool = False,
    ):
        if store_id is not None:
            self._get_store(
                tenant_id,
                store_id,
                f"Store with ID {store_id} not found",
            )

        query = (
            self.db.query(Inventory)
            .options(joinedload(Inventory.product), joinedload(Inventory.store))
            .filter(Inventory.tenant_id == tenant_id)
        )

        if store_id is not None:
            query = query.filter(Inventory.store_id == store_id)

        if product_id is not None:
            query = query.filter(Inventory.product_id == product_id)

        if low_stock_only:
            query = query.filter(Inventory.quantity <= Inventory.min_stock_level)

        if category_id is not None or search:
            query = query.join(Product, Inventory.product_id == Product.id)
            if category_id is not None:
                query = query.filter(Product.category_id == category_id)
            if search:
                s = f"%{search.strip()}%"
                query = query.filter(
                    Product.name.ilike(s) | Product.sku.ilike(s)
                )

        items = query.all()
        if not items:
            return {
                "success": True,
                "message": "No inventory found",
                "data": [],
            }
        return items

    def get_inventory_by_product(
        self,
        tenant_id: int,
        product_id: int,
        store_id: Optional[int] = None,
    ):
        product = self._get_product(tenant_id, product_id)

        query = self.db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.product_id == product_id,
        )
        if store_id is not None:
            self._get_store(tenant_id, store_id, f"Store with ID {store_id} not found")
            query = query.filter(Inventory.store_id == store_id)

        inventory = query.first()

        if not inventory:
            raise NotFoundException(
                f"Inventory record for product with ID {product_id} not found"
            )

        updated = False
        default_min = getattr(product, "min_stock_alert", None) or 5
        if not inventory.min_stock_level:
            inventory.min_stock_level = default_min
            updated = True
        if not inventory.reorder_point:
            inventory.reorder_point = default_min
            updated = True
        if not inventory.max_stock_level:
            inventory.max_stock_level = max(default_min * 20, 100)
            updated = True

        if updated:
            try:
                self.db.commit()
                self.db.refresh(inventory)
            except Exception:
                self.db.rollback()

        return inventory

    def inventory_valuation(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ):
        if store_id is not None:
            self._get_store(tenant_id, store_id, f"Store with ID {store_id} not found")

        query = (
            self.db.query(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .filter(Inventory.tenant_id == tenant_id)
        )
        if store_id is not None:
            query = query.filter(Inventory.store_id == store_id)

        inventories = query.all()

        total_value = Decimal("0.00")

        for inventory in inventories:
            unit_val = (
                inventory.product.cost_price
                if inventory.product.cost_price > Decimal("0.00")
                else (
                    inventory.product.mrp
                    if inventory.product.mrp > Decimal("0.00")
                    else inventory.product.selling_price
                )
            )
            total_value += inventory.quantity * unit_val

        return {"total_inventory_value": total_value}

    def expiry_inventory(
        self,
        tenant_id: int,
    ):
        inventories = (
            self.db.query(Inventory)
            .filter(Inventory.tenant_id == tenant_id)
            .all()
        )
        today = date.today()
        def _is_expired(inv):
            exp = inv.expiry_date
            if isinstance(exp, str):
                try:
                    exp = date.fromisoformat(exp)
                except (ValueError, TypeError):
                    return False
            return exp is not None and exp < today

        expired = [
            inv
            for inv in inventories
            if _is_expired(inv)
        ]
        if not expired:
            return {
                "success": True,
                "message": "No expired inventory found",
                "data": [],
            }
        return expired

    def list_movements(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        product_id: Optional[int] = None,
        movement_type: Optional[str] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ):
        if store_id is not None:
            self._get_store(
                tenant_id,
                store_id,
                f"Store with ID {store_id} not found",
            )

        query = self.db.query(StockMovement).filter(StockMovement.tenant_id == tenant_id)

        if store_id is not None:
            query = query.filter(StockMovement.store_id == store_id)

        if product_id is not None:
            self._get_product(tenant_id, product_id)
            query = query.filter(StockMovement.product_id == product_id)

        if movement_type:
            query = query.filter(func.lower(StockMovement.movement_type) == movement_type.lower().strip())

        query = query.order_by(StockMovement.created_at.desc())

        if page is not None and page_size is not None:
            offset = (page - 1) * page_size
            movements = query.offset(offset).limit(page_size).all()
        else:
            movements = query.limit(100).all()

        if not movements:
            return {
                "success": True,
                "message": "No inventory movements found",
                "data": [],
            }
        return movements

    def adjust_inventory(
        self,
        tenant_id: int,
        data: InventoryAdjustmentRequest,
    ):
        self._get_product(tenant_id, data.product_id)
        self._get_store(tenant_id, data.store_id)

        if data.quantity <= 0:
            raise AppException("quantity must be greater than 0")

        inventory = self._get_or_create_inventory(
            tenant_id,
            data.store_id,
            data.product_id,
        )

        previous_stock = inventory.quantity

        if data.adjustment_type == "increase":
            inventory.quantity += data.quantity
            new_stock = inventory.quantity
        elif data.adjustment_type == "decrease":
            if inventory.quantity < data.quantity:
                raise AppException(
                    f"Insufficient stock for adjustment decrease. Available: {inventory.quantity}, requested: {data.quantity}"
                )
            inventory.quantity -= data.quantity
            new_stock = inventory.quantity
        else:
            raise AppException("Adjustment type must be increase or decrease")

        ref_id, ref_str = self._generate_movement_reference(tenant_id, "ADJ")

        movement = StockMovement(
            tenant_id=tenant_id,
            store_id=data.store_id,
            product_id=data.product_id,
            movement_type=StockMovementType.ADJUSTMENT.value,
            quantity=data.quantity,
            previous_stock=previous_stock,
            new_stock=new_stock,
            reference_id=ref_id,
            reference_type=ref_str,
            notes=data.reason,
        )

        try:
            self.db.add(movement)
            self.db.commit()
            self.db.refresh(movement)
        except Exception:
            self.db.rollback()
            raise

        cache_delete_pattern(f"inventory:{tenant_id}:*")

        return movement

    def get_dashboard(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ):
        if store_id is not None:
            self._get_store(tenant_id, store_id, f"Store with ID {store_id} not found")

        inv_query = (
            self.db.query(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .filter(Inventory.tenant_id == tenant_id)
        )
        if store_id is not None:
            inv_query = inv_query.filter(Inventory.store_id == store_id)

        inventories = inv_query.all()

        prod_query = self.db.query(func.count(distinct(Inventory.product_id))).filter(Inventory.tenant_id == tenant_id)
        if store_id is not None:
            prod_query = prod_query.filter(Inventory.store_id == store_id)
        total_products = prod_query.scalar() or 0

        stock_query = self.db.query(func.coalesce(func.sum(Inventory.quantity), 0)).filter(Inventory.tenant_id == tenant_id)
        if store_id is not None:
            stock_query = stock_query.filter(Inventory.store_id == store_id)
        total_stock = stock_query.scalar() or 0

        low_stock_query = self.db.query(func.count(Inventory.id)).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.quantity <= Inventory.min_stock_level,
        )
        if store_id is not None:
            low_stock_query = low_stock_query.filter(Inventory.store_id == store_id)
        low_stock = low_stock_query.scalar() or 0

        inventory_value = Decimal("0.00")
        today = date.today()
        expired_products = 0

        for inv in inventories:
            unit_val = (
                inv.product.cost_price
                if inv.product.cost_price > Decimal("0.00")
                else (
                    inv.product.mrp
                    if inv.product.mrp > Decimal("0.00")
                    else inv.product.selling_price
                )
            )
            inventory_value += inv.quantity * unit_val
            exp_date = inv.expiry_date
            if isinstance(exp_date, str):
                try:
                    exp_date = date.fromisoformat(exp_date)
                except (ValueError, TypeError):
                    exp_date = None
            if exp_date is not None and exp_date < today:
                expired_products += 1

        transfer_query = (
            self.db.query(func.count(StoreTransfer.id))
            .join(Store, StoreTransfer.source_store_id == Store.id)
            .filter(
                Store.tenant_id == tenant_id,
                StoreTransfer.status.in_(["pending", "Pending", "draft", "Draft"]),
            )
        )
        if store_id is not None:
            transfer_query = transfer_query.filter(
                (StoreTransfer.source_store_id == store_id) | (StoreTransfer.destination_store_id == store_id)
            )
        pending_transfers = transfer_query.scalar() or 0

        po_query = (
            self.db.query(func.count(PurchaseOrder.id))
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.status.in_(["pending", "draft", "ordered"]),
            )
        )
        if store_id is not None:
            po_query = po_query.filter(PurchaseOrder.store_id == store_id)
        pending_purchase_orders = po_query.scalar() or 0

        return {
            "total_products": total_products,
            "total_stock": total_stock,
            "total_stock_value": inventory_value,
            "low_stock_items": low_stock,
            "expired_products": expired_products,
            "pending_transfers": pending_transfers,
            "pending_purchase_orders": pending_purchase_orders,
        }

    def get_near_expiry_inventory(
        self,
        tenant_id: int,
        days: int = 30,
        store_id: Optional[int] = None,
    ) -> dict:
        if store_id is not None:
            self._get_store(tenant_id, store_id, f"Store with ID {store_id} not found")

        today = date.today()
        target_date = today + timedelta(days=days)

        query = (
            self.db.query(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .join(Store, Inventory.store_id == Store.id)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.expiry_date.isnot(None),
                Inventory.expiry_date >= today,
                Inventory.expiry_date <= target_date,
                Inventory.quantity > 0,
            )
        )
        if store_id is not None:
            query = query.filter(Inventory.store_id == store_id)

        query = query.order_by(Inventory.expiry_date.asc())
        items = query.all()

        data = []
        for inv in items:
            exp = inv.expiry_date
            if isinstance(exp, str):
                try:
                    exp = date.fromisoformat(exp)
                except (ValueError, TypeError):
                    continue
            days_left = (exp - today).days if exp else 0
            data.append({
                "inventory_id": inv.id,
                "store_id": inv.store_id,
                "store_name": inv.store.name if inv.store else None,
                "product_id": inv.product_id,
                "product_name": inv.product.name if inv.product else None,
                "product_sku": inv.product.sku if inv.product else None,
                "batch_number": inv.batch_number,
                "expiry_date": exp,
                "days_until_expiry": days_left,
                "quantity": int(inv.quantity),
                "min_stock_level": inv.min_stock_level,
            })

        return {
            "success": True,
            "message": (
                "Near-expiry inventory retrieved successfully"
                if data
                else "No near-expiry inventory found"
            ),
            "count": len(data),
            "threshold_days": days,
            "data": data,
        }

    def get_product_availability_across_stores(
        self,
        tenant_id: int,
        product_id: int,
    ) -> dict:
        product = self._get_product(tenant_id, product_id)

        stores = (
            self.db.query(Store)
            .filter(Store.tenant_id == tenant_id)
            .order_by(Store.name.asc())
            .all()
        )

        inventories = (
            self.db.query(Inventory)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.product_id == product_id,
            )
            .all()
        )
        inv_map = {inv.store_id: inv for inv in inventories}

        store_positions = []
        total_stock = 0

        for st in stores:
            inv = inv_map.get(st.id)
            qty = int(inv.quantity) if inv else 0
            min_stock = inv.min_stock_level if inv else 0
            max_stock = inv.max_stock_level if inv else 0
            reorder = inv.reorder_point if inv else 0
            is_low = (qty <= min_stock) if min_stock > 0 else False
            total_stock += qty

            store_positions.append({
                "store_id": st.id,
                "store_name": st.name,
                "store_code": getattr(st, "code", None),
                "quantity": qty,
                "min_stock_level": min_stock,
                "max_stock_level": max_stock,
                "reorder_point": reorder,
                "is_low_stock": is_low,
            })

        return {
            "success": True,
            "message": "Product stock availability across stores retrieved successfully",
            "product_id": product.id,
            "product_name": product.name,
            "product_sku": product.sku,
            "total_stock": total_stock,
            "stores_count": len(stores),
            "data": store_positions,
        }

    def get_valuation_breakdown(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> dict:
        if store_id is not None:
            self._get_store(tenant_id, store_id, f"Store with ID {store_id} not found")

        query = (
            self.db.query(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .join(Store, Inventory.store_id == Store.id)
            .filter(Inventory.tenant_id == tenant_id)
        )
        if store_id is not None:
            query = query.filter(Inventory.store_id == store_id)

        inventories = query.all()

        total_items = len(inventories)
        total_quantity = 0
        total_cost_val = Decimal("0.00")
        total_retail_val = Decimal("0.00")

        store_stats = {}
        cat_stats = {}

        categories = {c.id: c.name for c in self.db.query(Category).filter(Category.tenant_id == tenant_id).all()}

        for inv in inventories:
            prod = inv.product
            qty = int(inv.quantity)
            total_quantity += qty

            cost = prod.cost_price if prod.cost_price and prod.cost_price > Decimal("0.00") else Decimal("0.00")
            retail = prod.mrp if prod.mrp and prod.mrp > Decimal("0.00") else (prod.selling_price if prod.selling_price and prod.selling_price > Decimal("0.00") else cost)

            item_cost = qty * cost
            item_retail = qty * retail

            total_cost_val += item_cost
            total_retail_val += item_retail

            # Store stats
            s_id = inv.store_id
            s_name = inv.store.name
            if s_id not in store_stats:
                store_stats[s_id] = {
                    "store_id": s_id,
                    "store_name": s_name,
                    "item_count": 0,
                    "total_quantity": 0,
                    "total_cost_value": Decimal("0.00"),
                    "total_retail_value": Decimal("0.00"),
                }
            store_stats[s_id]["item_count"] += 1
            store_stats[s_id]["total_quantity"] += qty
            store_stats[s_id]["total_cost_value"] += item_cost
            store_stats[s_id]["total_retail_value"] += item_retail

            # Category stats
            c_id = prod.category_id
            c_name = categories.get(c_id, "Uncategorized") if c_id else "Uncategorized"
            if c_id not in cat_stats:
                cat_stats[c_id] = {
                    "category_id": c_id,
                    "category_name": c_name,
                    "item_count": 0,
                    "total_quantity": 0,
                    "total_cost_value": Decimal("0.00"),
                    "total_retail_value": Decimal("0.00"),
                }
            cat_stats[c_id]["item_count"] += 1
            cat_stats[c_id]["total_quantity"] += qty
            cat_stats[c_id]["total_cost_value"] += item_cost
            cat_stats[c_id]["total_retail_value"] += item_retail

        potential_profit = total_retail_val - total_cost_val
        margin_pct = float(round((potential_profit / total_retail_val) * 100, 2)) if total_retail_val > 0 else 0.0

        stores_breakdown = []
        for s in store_stats.values():
            profit = s["total_retail_value"] - s["total_cost_value"]
            margin = float(round((profit / s["total_retail_value"]) * 100, 2)) if s["total_retail_value"] > 0 else 0.0
            stores_breakdown.append({
                **s,
                "potential_gross_profit": profit,
                "potential_margin_percentage": margin,
            })

        categories_breakdown = list(cat_stats.values())

        return {
            "success": True,
            "message": "Inventory valuation breakdown retrieved successfully",
            "summary": {
                "total_items": total_items,
                "total_quantity": total_quantity,
                "total_cost_value": total_cost_val,
                "total_retail_value": total_retail_val,
                "potential_gross_profit": potential_profit,
                "potential_margin_percentage": margin_pct,
            },
            "stores_breakdown": stores_breakdown,
            "categories_breakdown": categories_breakdown,
        }

    def bulk_adjust_inventory(
        self,
        tenant_id: int,
        data: BulkInventoryAdjustmentRequest,
    ) -> dict:
        store = self._get_store(tenant_id, data.store_id)

        processed_items = []
        adjusted_count = 0
        unchanged_count = 0
        net_quantity_change = 0

        for item in data.items:
            product = self._get_product(tenant_id, item.product_id)
            inventory = self._get_or_create_inventory(tenant_id, data.store_id, item.product_id)

            prev_stock = int(inventory.quantity)
            counted = item.counted_quantity
            diff = counted - prev_stock

            if diff == 0:
                unchanged_count += 1
                processed_items.append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "product_sku": product.sku,
                    "previous_stock": prev_stock,
                    "counted_stock": counted,
                    "difference": 0,
                    "movement_type": None,
                    "movement_reference": None,
                })
                continue

            adjusted_count += 1
            net_quantity_change += diff
            inventory.quantity = Decimal(str(counted))

            ref_id, ref_str = self._generate_movement_reference(tenant_id, "ADJ")
            m_type = "increase" if diff > 0 else "decrease"
            reason_str = item.reason or f"Bulk stocktaking adjustment ({m_type})"
            if data.audit_reference:
                reason_str = f"[{data.audit_reference}] {reason_str}"

            movement = StockMovement(
                tenant_id=tenant_id,
                store_id=data.store_id,
                product_id=product.id,
                movement_type=StockMovementType.ADJUSTMENT.value,
                quantity=abs(diff),
                previous_stock=prev_stock,
                new_stock=counted,
                reference_id=ref_id,
                reference_type=ref_str,
                notes=reason_str[:255],
            )
            self.db.add(movement)

            processed_items.append({
                "product_id": product.id,
                "product_name": product.name,
                "product_sku": product.sku,
                "previous_stock": prev_stock,
                "counted_stock": counted,
                "difference": diff,
                "movement_type": m_type,
                "movement_reference": ref_str,
            })

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        cache_delete_pattern(f"inventory:{tenant_id}:*")

        return {
            "success": True,
            "message": "Bulk inventory adjustment completed successfully",
            "store_id": store.id,
            "store_name": store.name,
            "total_items_processed": len(data.items),
            "adjusted_items_count": adjusted_count,
            "unchanged_items_count": unchanged_count,
            "net_quantity_change": net_quantity_change,
            "audit_reference": data.audit_reference,
            "adjustments": processed_items,
        }

