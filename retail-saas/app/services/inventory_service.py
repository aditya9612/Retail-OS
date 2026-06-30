from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.inventory import Inventory, StockMovement, Supplier
from app.models.product import Product
from app.schemas.inventory import StockInRequest, StockOutRequest, StockTransferRequest, SupplierCreate
from app.utils.constants import StockMovementType
from app.utils.helpers import cache_delete_pattern


class InventoryService:
    def __init__(self, db: Session):
        self.db = db

    def _get_or_create_inventory(self, tenant_id: int, store_id: int, product_id: int) -> Inventory:
        inv = (
            self.db.query(Inventory)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.store_id == store_id,
                Inventory.product_id == product_id,
            )
            .first()
        )
        if not inv:
            inv = Inventory(tenant_id=tenant_id, store_id=store_id, product_id=product_id, quantity=0)
            self.db.add(inv)
            self.db.flush()
        return inv

    def stock_in(self, tenant_id: int, data: StockInRequest) -> StockMovement:
        product = self.db.query(Product).filter(Product.id == data.product_id, Product.tenant_id == tenant_id).first()
        if not product:
            raise NotFoundException("Product not found")
        inv = self._get_or_create_inventory(tenant_id, data.store_id, data.product_id)
        inv.quantity += data.quantity
        if data.batch_number:
            inv.batch_number = data.batch_number
        if data.expiry_date:
            inv.expiry_date = data.expiry_date
        movement = StockMovement(
            tenant_id=tenant_id,
            store_id=data.store_id,
            product_id=data.product_id,
            movement_type=StockMovementType.STOCK_IN.value,
            quantity=data.quantity,
            supplier_id=data.supplier_id,
            unit_cost=data.unit_cost,
            notes=data.notes,
        )
        self.db.add(movement)
        self.db.commit()
        self.db.refresh(movement)
        cache_delete_pattern(f"inventory:{tenant_id}:*")
        return movement

    def stock_out(self, tenant_id: int, data: StockOutRequest) -> StockMovement:
        inv = self._get_or_create_inventory(tenant_id, data.store_id, data.product_id)
        if inv.quantity < data.quantity:
            from app.core.exceptions import AppException
            raise AppException("Insufficient stock")
        inv.quantity -= data.quantity
        movement = StockMovement(
            tenant_id=tenant_id,
            store_id=data.store_id,
            product_id=data.product_id,
            movement_type=StockMovementType.STOCK_OUT.value,
            quantity=data.quantity,
            notes=data.notes,
        )
        self.db.add(movement)
        self.db.commit()
        self.db.refresh(movement)
        cache_delete_pattern(f"inventory:{tenant_id}:*")
        return movement

    def transfer_stock(self, tenant_id: int, data: StockTransferRequest) -> StockMovement:
        from_inv = self._get_or_create_inventory(tenant_id, data.from_store_id, data.product_id)
        if from_inv.quantity < data.quantity:
            from app.core.exceptions import AppException
            raise AppException("Insufficient stock for transfer")
        from_inv.quantity -= data.quantity
        to_inv = self._get_or_create_inventory(tenant_id, data.to_store_id, data.product_id)
        to_inv.quantity += data.quantity
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
        self.db.add(movement)
        self.db.commit()
        self.db.refresh(movement)
        cache_delete_pattern(f"inventory:{tenant_id}:*")
        return movement

    def get_low_stock(self, tenant_id: int, store_id: int | None = None) -> list[Inventory]:
        query = self.db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.quantity <= Inventory.low_stock_threshold,
        )
        if store_id:
            query = query.filter(Inventory.store_id == store_id)
        return query.all()

    def list_inventory(self, tenant_id: int, store_id: int | None = None) -> list[Inventory]:
        query = self.db.query(Inventory).filter(Inventory.tenant_id == tenant_id)
        if store_id:
            query = query.filter(Inventory.store_id == store_id)
        return query.all()

    def create_supplier(self, tenant_id: int, data: SupplierCreate) -> Supplier:
        supplier = Supplier(tenant_id=tenant_id, **data.model_dump())
        self.db.add(supplier)
        self.db.commit()
        self.db.refresh(supplier)
        return supplier

    def list_suppliers(self, tenant_id: int) -> list[Supplier]:
        return self.db.query(Supplier).filter(Supplier.tenant_id == tenant_id).all()
    
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

    def list_movements(self, tenant_id: int, store_id: int | None = None) -> list[StockMovement]:
        query = self.db.query(StockMovement).filter(StockMovement.tenant_id == tenant_id)
        if store_id:
            query = query.filter(StockMovement.store_id == store_id)
        return query.order_by(StockMovement.created_at.desc()).limit(100).all()
