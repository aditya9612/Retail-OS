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
)
from app.utils.constants import StockMovementType
from app.utils.helpers import cache_delete_pattern


class InventoryService:
    def __init__(self, db: Session):
        self.db = db

    def _get_or_create_inventory(
        self,
        tenant_id: int,
        store_id: int,
        product_id: int,
    ) -> Inventory:

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

    def stock_in(
        self,
        tenant_id: int,
        data: StockInRequest,
    ) -> StockMovement:

        product = (
            self.db.query(Product)
            .filter(
                Product.id == data.product_id,
                Product.tenant_id == tenant_id,
            )
            .first()
        )

        if not product:
            raise NotFoundException("Product not found")

        store = (
            self.db.query(Store)
            .filter(
                Store.id == data.store_id,
                Store.tenant_id == tenant_id,
            )
            .first()
        )

        if not store:
            raise NotFoundException("Store not found")

        if data.quantity <= 0:
            raise AppException("Quantity must be greater than zero")

        if data.unit_cost is not None and data.unit_cost <= Decimal("0"):
            raise AppException("Unit cost must be greater than zero")

        inventory = self._get_or_create_inventory(
            tenant_id,
            data.store_id,
            data.product_id,
        )

        if data.expiry_date:
            if data.expiry_date <= date.today():
                raise AppException("Expiry date must be in future")

        inventory.quantity += data.quantity

        if data.batch_number:
            inventory.batch_number = data.batch_number

        if data.expiry_date:
            inventory.expiry_date = data.expiry_date

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

    def stock_out(
        self,
        tenant_id: int,
        data: StockOutRequest,
    ) -> StockMovement:

        product = (
            self.db.query(Product)
            .filter(
                Product.id == data.product_id,
                Product.tenant_id == tenant_id,
            )
            .first()
        )

        if not product:
            raise NotFoundException("Product not found")

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

        self.db.add(movement)

        self.db.commit()

        self.db.refresh(movement)

        cache_delete_pattern(f"inventory:{tenant_id}:*")

        return movement
    def transfer_stock(
        self,
        tenant_id: int,
        data: StockTransferRequest,
    ) -> StockMovement:

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

        self.db.add(movement)

        self.db.commit()

        self.db.refresh(movement)

        cache_delete_pattern(f"inventory:{tenant_id}:*")

        return movement
    def get_low_stock(
        self,
        tenant_id: int,
        store_id: int | None = None,
    ):

        query = self.db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.quantity <= Inventory.low_stock_threshold,
        )

        if store_id:
            query = query.filter(
                Inventory.store_id == store_id
            )

        return query.all()
    def list_inventory(
        self,
        tenant_id: int,
        store_id: int | None = None,
    ):

        query = self.db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id
        )

        if store_id:
            query = query.filter(
                Inventory.store_id == store_id
            )

        return query.all()
    def create_supplier(
        self,
        tenant_id: int,
        data: SupplierCreate,
    ) -> Supplier:

        supplier = Supplier(
            tenant_id=tenant_id,
            **data.model_dump()
        )

        self.db.add(supplier)
        self.db.commit()
        self.db.refresh(supplier)

        return supplier

    def list_suppliers(self, tenant_id: int):

        return (
            self.db.query(Supplier)
            .filter(
                Supplier.tenant_id == tenant_id
            )
            .all()
        )

    def list_movements(
        self,
        tenant_id: int,
        store_id: int | None = None,
    ):

        query = self.db.query(StockMovement).filter(
            StockMovement.tenant_id == tenant_id
        )

        if store_id:
            query = query.filter(
                StockMovement.store_id == store_id
            )

        return (
            query.order_by(
                StockMovement.created_at.desc()
            )
            .limit(100)
            .all()
        )