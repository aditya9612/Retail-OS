from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.inventory import Inventory, StockMovement
from app.models.saas_plan_entitlement import EntitlementDimension
from app.models.store import Store
from app.repositories.store_repo import StoreRepository
from app.schemas.store import StoreCreate, StoreUpdate
from app.services.saas_entitlement_service import SaaSEntitlementService


class StoreService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = StoreRepository(db)

    def create_store(self, tenant_id: int, data: StoreCreate) -> Store:

        # Check duplicate store name
        if self.repo.get_by_name(data.name, tenant_id):
            raise ConflictException("Store name already exists")

        # Check duplicate store code
        if self.repo.get_by_code(data.code, tenant_id):
            raise ConflictException("Store code already exists")

        # Prevent multiple Main Stores for the same tenant
        if data.is_main is True:
            existing_main_store = (
                self.db.query(Store)
                .filter(
                    Store.tenant_id == tenant_id,
                    Store.is_main.is_(True),
                )
                .first()
            )

            if existing_main_store:
                raise ConflictException(
                    "A Main Store already exists for this tenant"
                )

        # Atomic tenant lock and store quota check
        entitlement_svc = SaaSEntitlementService(self.db)
        entitlement_svc.require_limit(
            tenant_id=tenant_id,
            dimension=EntitlementDimension.STORES,
            requested_amount=1,
            lock_tenant=True,
        )

        # Create store
        store = Store(
            tenant_id=tenant_id,
            **data.model_dump()
        )

        store = self.repo.create(store)
        self.db.commit()
        self.db.refresh(store)

        return store

    def get_store(
        self,
        tenant_id: int,
        store_id: int,
        include_inactive: bool = False
    ) -> Store:

        store = self.repo.get_by_id(
            store_id,
            tenant_id,
            include_inactive=include_inactive
        )

        if not store:
            raise NotFoundException("Store not found")

        return store

    def list_stores(
        self,
        tenant_id: int,
        store_id: int | None = None
    ) -> list[Store]:

        if store_id is not None:
            store = self.repo.get_by_id(store_id, tenant_id)
            return [store] if store else []

        return self.repo.list_stores(tenant_id)

    def update_store(
        self,
        tenant_id: int,
        store_id: int,
        data: StoreUpdate
    ) -> Store:

        store = self.get_store(
            tenant_id,
            store_id,
            include_inactive=True
        )

        update_data = data.model_dump(exclude_unset=True)

        # Quota check only when reactivating: False -> True
        if (
            "is_active" in update_data
            and not store.is_active
            and update_data["is_active"] is True
        ):
            entitlement_svc = SaaSEntitlementService(self.db)
            entitlement_svc.require_limit(
                tenant_id=tenant_id,
                dimension=EntitlementDimension.STORES,
                requested_amount=1,
                lock_tenant=True,
            )

        # Check duplicate store name
        if "name" in update_data:
            existing = self.repo.get_by_name(
                update_data["name"],
                tenant_id
            )

            if existing and existing.id != store_id:
                raise ConflictException("Store name already exists")

        # Check duplicate store code
        if "code" in update_data:
            existing = self.repo.get_by_code(
                update_data["code"],
                tenant_id
            )

            if existing and existing.id != store_id:
                raise ConflictException("Store code already exists")

        # Prevent multiple Main Stores for the same tenant
        if update_data.get("is_main") is True:
            existing_main_store = (
                self.db.query(Store)
                .filter(
                    Store.tenant_id == tenant_id,
                    Store.is_main.is_(True),
                    Store.id != store_id,
                )
                .first()
            )

            if existing_main_store:
                raise ConflictException(
                    "A Main Store already exists for this tenant"
                )

        # Apply updates
        for key, value in update_data.items():
            setattr(store, key, value)

        return self.repo.update(store)

    def delete_store(self, tenant_id: int, store_id: int) -> Store:

        store = self.get_store(tenant_id, store_id)

        # Prevent deletion when inventory exists
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

        # Prevent deletion when stock movements exist
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
