from datetime import datetime
from typing import Optional
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.store import Store
from app.models.store_target import StoreTarget


class StoreTargetRepository:

    @staticmethod
    def create(
        db: Session,
        target: StoreTarget,
    ) -> StoreTarget:
        db.add(target)
        db.commit()
        db.refresh(target)
        return target

    @staticmethod
    def get_by_id(
        db: Session,
        target_id: int,
    ) -> StoreTarget | None:
        return (
            db.query(StoreTarget)
            .filter(StoreTarget.id == target_id)
            .first()
        )

    @staticmethod
    def get_by_id_and_tenant(
        db: Session,
        target_id: int,
        tenant_id: int,
    ) -> StoreTarget | None:
        return (
            db.query(StoreTarget)
            .join(Store, Store.id == StoreTarget.store_id)
            .filter(
                StoreTarget.id == target_id,
                Store.tenant_id == tenant_id,
            )
            .first()
        )

    @staticmethod
    def get_all(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
        status: Optional[str] = None,
        period: Optional[str] = None,
        target_type: Optional[str] = None,
    ) -> list[StoreTarget]:
        query = (
            db.query(StoreTarget)
            .join(Store, Store.id == StoreTarget.store_id)
            .filter(
                Store.tenant_id == tenant_id,
                Store.is_active.is_(True),
            )
        )

        if store_id is not None:
            query = query.filter(StoreTarget.store_id == store_id)

        if status is not None:
            query = query.filter(StoreTarget.status == status)

        if period is not None:
            query = query.filter(StoreTarget.period == period)

        if target_type is not None:
            query = query.filter(StoreTarget.target_type == target_type)

        return query.order_by(StoreTarget.id.desc()).all()

    @staticmethod
    def update(
        db: Session,
        target: StoreTarget,
    ) -> StoreTarget:
        target.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(target)
        return target

    @staticmethod
    def delete(
        db: Session,
        target: StoreTarget,
    ) -> None:
        db.delete(target)
        db.commit()

    @staticmethod
    def get_overlapping_target(
        db: Session,
        tenant_id: int,
        store_id: int,
        target_type: str,
        start_date: datetime,
        end_date: datetime,
        exclude_target_id: Optional[int] = None,
    ) -> StoreTarget | None:
        """
        Check if an active target with the same target_type already overlaps
        the proposed date range for this store.
        """
        query = (
            db.query(StoreTarget)
            .join(Store, Store.id == StoreTarget.store_id)
            .filter(
                Store.tenant_id == tenant_id,
                StoreTarget.store_id == store_id,
                StoreTarget.target_type == target_type,
                StoreTarget.status == "active",
                # Overlap condition: existing.start < new.end AND existing.end > new.start
                and_(
                    StoreTarget.start_date < end_date,
                    StoreTarget.end_date > start_date,
                ),
            )
        )

        if exclude_target_id is not None:
            query = query.filter(StoreTarget.id != exclude_target_id)

        return query.first()

