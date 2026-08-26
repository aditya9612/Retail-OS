from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.warehouse import Warehouse


class WarehouseRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        warehouse: Warehouse,
    ) -> Warehouse:

        try:
            self.db.add(warehouse)
            self.db.commit()
            self.db.refresh(warehouse)

            return warehouse

        except IntegrityError:
            self.db.rollback()
            raise

    def list(
        self,
        tenant_id: int,
    ) -> list[Warehouse]:

        return (
            self.db.query(Warehouse)
            .filter(
                Warehouse.tenant_id == tenant_id,
            )
            .order_by(
                Warehouse.created_at.desc()
            )
            .all()
        )

    def get_by_id(
        self,
        warehouse_id: int,
        tenant_id: int,
    ) -> Warehouse | None:

        return (
            self.db.query(Warehouse)
            .filter(
                Warehouse.id == warehouse_id,
                Warehouse.tenant_id == tenant_id,
            )
            .first()
        )

    def update(
        self,
        warehouse: Warehouse,
    ) -> Warehouse:

        try:
            self.db.commit()
            self.db.refresh(warehouse)

            return warehouse

        except IntegrityError:
            self.db.rollback()
            raise

    def delete(
        self,
        warehouse: Warehouse,
    ) -> None:

        try:
            self.db.delete(warehouse)
            self.db.commit()

        except IntegrityError:
            self.db.rollback()
            raise

    def count(
        self,
        tenant_id: int,
    ) -> int:

        return (
            self.db.query(Warehouse)
            .filter(
                Warehouse.tenant_id == tenant_id,
            )
            .count()
        )

    def active_count(
        self,
        tenant_id: int,
    ) -> int:

        return (
            self.db.query(Warehouse)
            .filter(
                Warehouse.tenant_id == tenant_id,
                Warehouse.is_active.is_(True),
            )
            .count()
        )