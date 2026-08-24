from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.models.inventory import Inventory, StockMovement
from app.models.product import Product
from app.models.store import Store
from app.schemas.inventory import (
    StockInRequest,
    StockOutRequest,
    StockTransferRequest,
    InventoryAdjustmentRequest,
)
from app.utils.constants import StockMovementType
from app.utils.helpers import cache_delete_pattern
from app.models.purchase_order import PurchaseOrder
from app.models.supplier import Supplier

class InventoryService:
    def __init__(self, db: Session):
        self.db = db

    def _get_product(self, tenant_id: int, product_id: int):
        product = (
            self.db.query(Product)
            .filter(
                Product.id == product_id,
                Product.tenant_id == tenant_id
            )
            .first()
        )

        if not product:
            raise NotFoundException("Product not found")

        return product

    def _get_store(self, tenant_id: int, store_id: int, message="Store not found"):
        store = (
            self.db.query(Store)
            .filter(
                Store.id == store_id,
                Store.tenant_id == tenant_id
            )
            .first()
        )

        if not store:
            raise NotFoundException(message)

        return store

    def _get_or_create_inventory(self, tenant_id: int, store_id: int, product_id: int):
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

        product = self._get_product(tenant_id, data.product_id)
        store = self._get_store(tenant_id, data.store_id)

        if data.quantity <= 0:
            raise AppException("Quantity must be greater than zero")

        if data.unit_cost is not None and data.unit_cost <= Decimal("0"):
            raise AppException("Unit cost must be greater than zero")

        if data.expiry_date and data.expiry_date <= date.today():
            raise AppException("Expiry date must be in future")

        inventory = self._get_or_create_inventory(
            tenant_id,
            data.store_id,
            data.product_id,
        )

        inventory.quantity += data.quantity

        if data.batch_number:
            inventory.batch_number = data.batch_number

        if data.expiry_date:
            inventory.expiry_date = data.expiry_date

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
                raise NotFoundException("Supplier not found")

        movement = StockMovement(
            tenant_id=tenant_id,
            store_id=data.store_id,
            product_id=data.product_id,
            movement_type=StockMovementType.STOCK_IN.value,
            quantity=data.quantity,
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

    def stock_out(self, tenant_id: int, data: StockOutRequest) -> StockMovement:

        self._get_product(tenant_id, data.product_id)
        self._get_store(tenant_id, data.store_id)

        if data.quantity <= 0:
            raise AppException("Quantity must be greater than zero")

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
            raise NotFoundException("Inventory not found")

        if inventory.quantity < data.quantity:
            raise AppException("Insufficient stock")

        inventory.quantity -= data.quantity

        movement = StockMovement(
            tenant_id=tenant_id,
            store_id=data.store_id,
            product_id=data.product_id,
            movement_type=StockMovementType.STOCK_OUT.value,
            quantity=data.quantity,
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

    def transfer_stock(self, tenant_id: int, data: StockTransferRequest) -> StockMovement:

        if data.quantity <= 0:
            raise AppException("Quantity must be greater than zero")

        if data.from_store_id == data.to_store_id:
            raise AppException("Source and destination stores cannot be the same")

        self._get_product(tenant_id, data.product_id)

        from_store = self._get_store(tenant_id, data.from_store_id, "Source store not found")
        to_store = self._get_store(tenant_id, data.to_store_id, "Destination store not found")

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
            raise NotFoundException("Source inventory not found")

        if from_inventory.quantity < data.quantity:
            raise AppException("Insufficient stock")

        to_inventory = self._get_or_create_inventory(
            tenant_id,
            data.to_store_id,
            data.product_id,
        )

        from_inventory.quantity -= data.quantity
        to_inventory.quantity += data.quantity

        movement = StockMovement(
            tenant_id=tenant_id,
            store_id=data.from_store_id,
            product_id=data.product_id,
            movement_type=StockMovementType.TRANSFER.value,
            quantity=data.quantity,
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
        store_id: int | None = None,
    ):

        if store_id is not None:

           self._get_store(
               tenant_id,
               store_id,
               "Store not found",
            )

        query = (
           self.db.query(Inventory)
           .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.quantity <= Inventory.low_stock_threshold,
            )
        )

        if store_id is not None:

           query = query.filter(
               Inventory.store_id == store_id
        )

        return query.all()

    def list_inventory(
        self,
        tenant_id: int,
        store_id: int | None = None,
    ):

        if store_id is not None:

            self._get_store(
                tenant_id,
                store_id,
                "Store not found",
            )

        query = (
            self.db.query(Inventory)
            .filter(
               Inventory.tenant_id == tenant_id
            )
        )

        if store_id is not None:

           query = query.filter(
              Inventory.store_id == store_id
            )

        return query.all()
    
    def get_inventory_by_product(
         self,
         tenant_id: int,
         product_id: int,
    ):
         inventory = (
             self.db.query(Inventory)
             .filter(
                  Inventory.tenant_id == tenant_id,
                  Inventory.product_id == product_id,
            )
            .first()
        )

         if not inventory:
            raise NotFoundException("Inventory not found")

         return inventory
     
    def inventory_valuation(
         self,
         tenant_id: int,
    ):
         inventories = (
             self.db.query(Inventory)
             .filter(
                 Inventory.tenant_id == tenant_id
            )
            .all()
        )

         total_value = Decimal("0.00")

         for inventory in inventories:
             total_value += (
                 inventory.quantity *
                 inventory.product.cost_price
            )

         return {
             "total_inventory_value": total_value
        }

    def expiry_inventory(
        self,
        tenant_id: int,
    ):
        return (
            self.db.query(Inventory)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.expiry_date.is_not(None),
            )
            .order_by(Inventory.expiry_date.asc())
            .all()
        )

    def list_movements(
        self,
        tenant_id: int,
        store_id: int | None = None,
    ):

        if store_id is not None:

           self._get_store(
              tenant_id,
              store_id,
              "Store not found",
            )

        query = (
            self.db.query(StockMovement)
            .filter(
                StockMovement.tenant_id == tenant_id
            )
        )

        if store_id is not None:

           query = query.filter(
               StockMovement.store_id == store_id
            )

        return (
            query
            .order_by(
                 StockMovement.created_at.desc()
            )
            .limit(100)
            .all()
        )
    
    def adjust_inventory(
        self,
        tenant_id: int,
        data: InventoryAdjustmentRequest,
    ):
        self._get_product(tenant_id, data.product_id)
        self._get_store(tenant_id, data.store_id)

        inventory = self._get_or_create_inventory(
            tenant_id,
            data.store_id,
            data.product_id,
        )

        if data.adjustment_type == "increase":
            inventory.quantity += data.quantity

        elif data.adjustment_type == "decrease":
            if inventory.quantity < data.quantity:
                raise AppException("Insufficient stock")
            inventory.quantity -= data.quantity

        else:
            raise AppException(
                "Adjustment type must be increase or decrease"
            )

        movement = StockMovement(
            tenant_id=tenant_id,
            store_id=data.store_id,
            product_id=data.product_id,
            movement_type="adjustment",
            quantity=data.quantity,
            notes=data.reason,
        )
             
        self.db.add(movement)     
        self.db.commit()
        self.db.refresh(movement)

        cache_delete_pattern(f"inventory:{tenant_id}:*")

        return movement
    

    def get_dashboard(
        self,
        tenant_id: int,
    ):

        inventories = (
            self.db.query(Inventory)
            .filter(Inventory.tenant_id == tenant_id)
            .all()
        )

        total_products = len(inventories)

        total_stock = sum(
            inventory.quantity
            for inventory in inventories
        )

        low_stock = sum(
            1
            for inventory in inventories
            if inventory.quantity <= inventory.low_stock_threshold
        )

        inventory_value = Decimal("0.00")

        for inventory in inventories:
            inventory_value += (
                inventory.quantity *
                inventory.product.cost_price
            )

        return {
           "total_products": total_products,
           "total_stock": total_stock,
           "total_stock_value": inventory_value,
           "low_stock_items": low_stock,
           "expired_products": 0,
           "pending_transfers": 0,
           "pending_purchase_orders": 0,
}