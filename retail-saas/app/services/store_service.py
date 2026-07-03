from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.inventory import Inventory, StockMovement
from app.models.store import Store
from app.repositories.store_repo import StoreRepository
from app.schemas.store import StoreCreate, StoreUpdate


class StoreService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = StoreRepository(db)

    # ---------------- CREATE STORE ----------------
    def create_store(self, tenant_id: int, data: StoreCreate) -> Store:

        if self.repo.get_by_name(data.name, tenant_id):
            raise ConflictException("Store name already exists")

        if self.repo.get_by_code(data.code, tenant_id):
            raise ConflictException("Store code already exists")

        store = Store(
            tenant_id=tenant_id,
            **data.model_dump()
        )

        return self.repo.create(store)

    # ---------------- GET STORE ----------------
    def get_store(self, tenant_id: int, store_id: int) -> Store:

        store = self.repo.get_by_id(store_id, tenant_id)

        if not store:
            raise NotFoundException("Store not found")

        return store

    # ---------------- LIST STORES ----------------
    def list_stores(self, tenant_id: int) -> list[Store]:

        return self.repo.list_stores(tenant_id)

    # ---------------- UPDATE STORE ----------------
    def update_store(self, tenant_id: int, store_id: int, data: StoreUpdate) -> Store:

        store = self.get_store(tenant_id, store_id)

        update_data = data.model_dump(exclude_unset=True)

        if "name" in update_data:
            existing = self.repo.get_by_name(update_data["name"], tenant_id)
            if existing and existing.id != store_id:
                raise ConflictException("Store name already exists")

        if "code" in update_data:
            existing = self.repo.get_by_code(update_data["code"], tenant_id)
            if existing and existing.id != store_id:
                raise ConflictException("Store code already exists")

        for key, value in update_data.items():
            setattr(store, key, value)

        return self.repo.update(store)

    # ---------------- DELETE STORE ----------------
    def delete_store(self, tenant_id: int, store_id: int) -> Store:

        store = self.get_store(tenant_id, store_id)

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

        return self.repo.soft_delete(store)