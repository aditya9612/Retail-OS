from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.inventory import Inventory
from app.models.store import Store
from app.models.inventory import StockMovement
from app.repositories.store_repo import StoreRepository
from app.schemas.store import StoreCreate, StoreUpdate


class StoreService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = StoreRepository(db)

    def create_store(self, tenant_id: int, data: StoreCreate) -> Store:

        # Business Rule 1: Unique store name per tenant
        if self.repo.get_by_name(data.name, tenant_id):
            raise ConflictException("Store name already exists")

        # Business Rule 2: Unique store code per tenant
        if self.repo.get_by_code(data.code, tenant_id):
            raise ConflictException("Store code already exists")

        store = Store(
            tenant_id=tenant_id,
            **data.model_dump()
        )

        return self.repo.soft_delete(store, tenant_id)

    def get_store(self, tenant_id: int, store_id: int) -> Store:

        store = self.repo.get_by_id(store_id, tenant_id)

        if not store:
            raise NotFoundException("Store not found")

        return store

    def list_stores(self, tenant_id: int) -> list[Store]:

        return self.repo.list_stores(tenant_id)

    def update_store(
        self,
        tenant_id: int,
        store_id: int,
        data: StoreUpdate
    ) -> Store:

        store = self.get_store(tenant_id, store_id)

        update_data = data.model_dump(exclude_unset=True)

        # Business Rule: Name uniqueness check
        if "name" in update_data:
            existing = self.repo.get_by_name(update_data["name"], tenant_id)
            if existing and existing.id != store_id:
                raise ConflictException("Store name already exists")

        # Business Rule: Code uniqueness check
        if "code" in update_data:
            existing = self.repo.get_by_code(update_data["code"], tenant_id)
            if existing and existing.id != store_id:
                raise ConflictException("Store code already exists")

        # Apply updates
        for key, value in update_data.items():
            setattr(store, key, value)

        return self.repo.update(store)

    def delete_store(self, tenant_id: int, store_id: int) -> Store:

        store = self.get_store(tenant_id, store_id)

        # Business Rule 1: Cannot delete if inventory exists
        inventory_exists = (
            self.db.query(Inventory)
            .filter(
                Inventory.store_id == store_id,
                Inventory.tenant_id == tenant_id
            )
            .first()
        )

        if inventory_exists:
            raise ConflictException(
                "Cannot delete store because inventory exists"
            )

        # Business Rule 2: Cannot delete if stock movement exists
        movement_exists = (
            self.db.query(StockMovement)
            .filter(
                StockMovement.store_id == store_id,
                StockMovement.tenant_id == tenant_id
            )
            .first()
        )

        if movement_exists:
            raise ConflictException(
                "Cannot delete store because stock movements exist"
            )

        # Soft delete
        return self.repo.soft_delete(store)