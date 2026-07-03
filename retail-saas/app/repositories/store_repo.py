from sqlalchemy.orm import Session

from app.models.store import Store


class StoreRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, store: Store) -> Store:
        self.db.add(store)
        self.db.commit()
        self.db.refresh(store)
        return store

    def get_by_id(self, store_id: int, tenant_id: int):

        return (
            self.db.query(Store)
            .filter(
                Store.id == store_id,
                Store.tenant_id == tenant_id,
                Store.is_active == True
            )
            .first()
        )

    def list_stores(self, tenant_id: int):

        return (
            self.db.query(Store)
            .filter(
                Store.tenant_id == tenant_id,
                Store.is_active == True
            )
            .all()
        )

    def update(self, store: Store) -> Store:
        self.db.commit()
        self.db.refresh(store)
        return store

    def soft_delete(self, store: Store) -> Store:

        store.is_active = False
        self.db.commit()
        self.db.refresh(store)
        return store

    def get_by_name(self, name: str, tenant_id: int):
        return (
            self.db.query(Store)
            .filter(Store.name == name, Store.tenant_id == tenant_id)
            .first()
        )

    def get_by_code(self, code: str, tenant_id: int):
        return (
            self.db.query(Store)
            .filter(Store.code == code, Store.tenant_id == tenant_id)
            .first()
        )