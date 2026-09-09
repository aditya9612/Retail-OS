from sqlalchemy.orm import Session

from app.models.store import Store
from app.models.store_target import StoreTarget
from app.repositories.store_target_repo import StoreTargetRepository
from app.schemas.store_target import (
    StoreTargetCreate,
    StoreTargetUpdate,
)


class StoreTargetService:

    @staticmethod
    def create_target(
        db: Session,
        tenant_id: int,
        data: StoreTargetCreate,
    ):
        store = (
            db.query(Store)
            .filter(
                Store.id == data.store_id,
                Store.tenant_id == tenant_id,
                Store.is_active.is_(True),
            )
            .first()
        )

        if not store:
            raise ValueError("Store not found")

        target = StoreTarget(
            store_id=data.store_id,
            target_type=data.target_type,
            target_value=data.target_value,
            period=data.period,
            start_date=data.start_date,
            end_date=data.end_date,
            status="active",
        )

        return StoreTargetRepository.create(
            db,
            target,
        )

    @staticmethod
    def get_targets(
        db: Session,
        tenant_id: int,
        store_id: int | None = None,
    ):
        query = (
            db.query(StoreTarget)
            .join(
                Store,
                Store.id == StoreTarget.store_id,
            )
            .filter(
                Store.tenant_id == tenant_id,
                Store.is_active.is_(True),
            )
        )

        if store_id is not None:
            query = query.filter(
                StoreTarget.store_id == store_id
            )

        return query.order_by(
            StoreTarget.id.desc()
        ).all()

    @staticmethod
    def update_target(
        db: Session,
        tenant_id: int,
        target_id: int,
        data: StoreTargetUpdate,
    ):
        target = (
            db.query(StoreTarget)
            .join(
                Store,
                Store.id == StoreTarget.store_id,
            )
            .filter(
                StoreTarget.id == target_id,
                Store.tenant_id == tenant_id,
            )
            .first()
        )

        if not target:
            raise ValueError("Store target not found")

        update_data = data.model_dump(
            exclude_unset=True
        )

        for key, value in update_data.items():
            setattr(target, key, value)

        return StoreTargetRepository.update(
            db,
            target,
        )