from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.models.inventory import Inventory, StockMovement, Supplier
from app.models.product import Product
from app.models.store import Store
from app.schemas.inventory import (
    StockInRequest,
    StockOutRequest,
    StockTransferRequest,
    SupplierCreate,
    SupplierUpdate,
)
from app.utils.constants import StockMovementType
from app.utils.helpers import cache_delete_pattern

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

    def get_low_stock(self, tenant_id: int, store_id: int | None = None):
        query = self.db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.quantity <= Inventory.low_stock_threshold,
        )

        if store_id:
            query = query.filter(Inventory.store_id == store_id)

        return query.all()

    def list_inventory(self, tenant_id: int, store_id: int | None = None):
        query = self.db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id
        )

        if store_id:
            query = query.filter(Inventory.store_id == store_id)

        return query.all()

    def create_supplier(self, tenant_id: int, data: SupplierCreate):

        supplier = Supplier(
            tenant_id=tenant_id,
            **data.model_dump()
        )

        try:
            self.db.add(supplier)
            self.db.commit()
            self.db.refresh(supplier)
        except Exception:
            self.db.rollback()
            raise

        return supplier

    def list_suppliers(self, tenant_id: int):
        return (
            self.db.query(Supplier)
            .filter(Supplier.tenant_id == tenant_id)
            .all()
        )

    def get_supplier(self, tenant_id: int, supplier_id: int) -> Supplier:
        supplier = (
            self.db.query(Supplier)
             .filter(
                Supplier.tenant_id == tenant_id,
                Supplier.id == supplier_id,
             )
             .first()
        )

        if not supplier:
           raise NotFoundException("Supplier not found")
        
        return supplier


    def update_supplier(
        self,
        tenant_id: int,
        supplier_id: int,
        data: SupplierUpdate,
    ) -> Supplier:

         supplier = self.get_supplier(tenant_id, supplier_id)

         update_data = data.model_dump(exclude_unset=True)

         for key, value in update_data.items():
             setattr(supplier, key, value)

         self.db.commit()
         self.db.refresh(supplier)

         return supplier


    def update_supplier_status(
         self,
         tenant_id: int,
         supplier_id: int,
         is_active: bool,
    ):    

         supplier = self.get_supplier(
         tenant_id,
         supplier_id,
        )

         supplier.is_active = is_active

         self.db.commit()
         self.db.refresh(supplier)

         return supplier

    
    def search_suppliers(
         self,
         tenant_id: int,
         search: str,
    ):

         return (
             self.db.query(Supplier)
             .filter(
                 Supplier.tenant_id == tenant_id,
                 Supplier.name.ilike(f"%{search}%"),
            )
            .all()
    )
         
    def supplier_stats(
         self,
         tenant_id: int,
    ):

         suppliers = (
            self.db.query(Supplier)
            .filter(
                Supplier.tenant_id == tenant_id
            )
            .all()
    )

         return {
            "total_suppliers": len(suppliers),
            "active_suppliers": sum(
                1 for supplier in suppliers
                if supplier.is_active
            ),
            "inactive_suppliers": sum(
                1 for supplier in suppliers
                if not supplier.is_active
            ),
        }
    
        
    def list_movements(self, tenant_id: int, store_id: int | None = None):

        query = self.db.query(StockMovement).filter(
            StockMovement.tenant_id == tenant_id
        )

        if store_id:
            query = query.filter(StockMovement.store_id == store_id)

        return (
            query.order_by(StockMovement.created_at.desc())
            .limit(100)
            .all()
        )