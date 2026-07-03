from sqlalchemy.orm import Session

from app.repositories.store_repo import StoreRepository
from app.core.exceptions import NotFoundException, ConflictException
from app.models.store import Store
from app.models.inventory import Inventory, StockMovement
from app.schemas.store import StoreCreate, StoreUpdate


class StoreService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = StoreRepository(db)
    
    def create_store(self, tenant_id: int, data: StoreCreate) -> Store:
    

        existing = self.repo.get_by_name(data.name, tenant_id)
        if existing:
            raise ConflictException("Store name already exists")

        store = Store(
            tenant_id=tenant_id,
            **data.model_dump()
        )

        return self.repo.create(store)
    
    def get_store(self, tenant_id: int, store_id: int) -> Store:
    
        store = self.repo.get_by_id(store_id, tenant_id)

        if not store:
            raise NotFoundException("Store not found")

        return store
    
    def list_stores(self, tenant_id: int) -> list[Store]:
    
        return self.repo.list_stores(tenant_id)
    
    def update_store(self, tenant_id: int, store_id: int, data: StoreUpdate) -> Store:
    
        store = self.get_store(tenant_id, store_id)

        if data.name:
            existing = self.repo.get_by_name(data.name, tenant_id)
            if existing and existing.id != store_id:
                raise ConflictException("Store name already exists")

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(store, key, value)

        return self.repo.update(store)
    
    def delete_store(self, tenant_id: int, store_id: int) -> Store:
    
        store = self.get_store(tenant_id, store_id)

        inventory_exists = (
            self.db.query(Inventory)
            .filter(Inventory.store_id == store_id)
            .first()
        )

        if inventory_exists:
            raise ConflictException("Cannot delete store with inventory")
        stock_exists = (
            self.db.query(StockMovement)
            .filter(StockMovement.store_id == store_id)
            .first()
        )

        if stock_exists:
            raise ConflictException("Cannot delete store with stock movements")

        return self.repo.soft_delete(store)