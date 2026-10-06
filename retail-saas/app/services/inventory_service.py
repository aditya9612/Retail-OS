from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.models.document_sequence import DocumentSequence
from app.models.inventory import Inventory, StockMovement
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.store import Store
from app.models.store_transfer import StoreTransfer
from app.models.supplier import Supplier
from app.schemas.inventory import (
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
            inventory = Inventory(
                tenant_id=tenant_id,
                store_id=store_id,
                product_id=product_id,
                quantity=0,
            )
            self.db.add(inventory)
            self.db.flush()

        return inventory

    def stock_in(self, tenant_id: int, data: StockInRequest) -> StockMovement:
        self._get_product(tenant_id, data.product_id)
        self._get_store(tenant_id, data.store_id)

        if data.quantity <= 0:
            raise AppException("quantity must be greater than 0")

        if data.unit_cost is not None and data.unit_cost <= Decimal("0"):
            raise AppException("unit_cost must be greater than 0")

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

        if data.batch_number:
            inventory.batch_number = data.batch_number

        if data.expiry_date:
            inventory.expiry_date = data.expiry_date

        ref_id, ref_str = self._generate_movement_reference(tenant_id, "IN")

        movement = StockMovement(
            tenant_id=tenant_id,
            store_id=data.store_id,
            product_id=data.product_id,
            movement_type=StockMovementType.STOCK_IN.value,
            quantity=data.quantity,
            previous_stock=previous_stock,
            new_stock=new_stock,
            reference_id=ref_id,
            reference_type=ref_str,
            supplier_id=data.supplier_id if supplier else None,
            unit_cost=data.unit_cost,
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

        ref_id, ref_str = self._generate_movement_reference(tenant_id, "TR")

        movement = StockMovement(
            tenant_id=tenant_id,
            store_id=data.from_store_id,
            product_id=data.product_id,
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
    ):
        if store_id is not None:
            self._get_store(
                tenant_id,
                store_id,
                f"Store with ID {store_id} not found",
            )

        query = self.db.query(Inventory).filter(Inventory.tenant_id == tenant_id)

        if store_id is not None:
            query = query.filter(Inventory.store_id == store_id)

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
    ):
        self._get_product(tenant_id, product_id)

        inventory = (
            self.db.query(Inventory)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.product_id == product_id,
            )
            .first()
        )

        if not inventory:
            raise NotFoundException(
                f"Inventory record for product with ID {product_id} not found"
            )

        return inventory

    def inventory_valuation(
        self,
        tenant_id: int,
    ):
        inventories = (
            self.db.query(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .filter(Inventory.tenant_id == tenant_id)
            .all()
        )

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
        expired = [
            inv
            for inv in inventories
            if inv.expiry_date is not None and inv.expiry_date < today
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

        movements = (
            query.order_by(StockMovement.created_at.desc())
            .limit(100)
            .all()
        )
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
    ):
        inventories = (
            self.db.query(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .filter(Inventory.tenant_id == tenant_id)
            .all()
        )

        total_products = (
            self.db.query(func.count(distinct(Inventory.product_id)))
            .filter(Inventory.tenant_id == tenant_id)
            .scalar()
            or 0
        )

        total_stock = (
            self.db.query(func.coalesce(func.sum(Inventory.quantity), 0))
            .filter(Inventory.tenant_id == tenant_id)
            .scalar()
            or 0
        )

        low_stock = (
            self.db.query(func.count(Inventory.id))
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.quantity <= Inventory.min_stock_level,
            )
            .scalar()
            or 0
        )

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
            if inv.expiry_date is not None and inv.expiry_date < today:
                expired_products += 1

        pending_transfers = (
            self.db.query(func.count(StoreTransfer.id))
            .join(Store, StoreTransfer.source_store_id == Store.id)
            .filter(
                Store.tenant_id == tenant_id,
                StoreTransfer.status.in_(["pending", "Pending", "draft", "Draft"]),
            )
            .scalar()
            or 0
        )

        pending_purchase_orders = (
            self.db.query(func.count(PurchaseOrder.id))
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.status.in_(["pending", "draft", "ordered"]),
            )
            .scalar()
            or 0
        )

        return {
            "total_products": total_products,
            "total_stock": total_stock,
            "total_stock_value": inventory_value,
            "low_stock_items": low_stock,
            "expired_products": expired_products,
            "pending_transfers": pending_transfers,
            "pending_purchase_orders": pending_purchase_orders,
        }
