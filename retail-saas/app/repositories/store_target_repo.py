from sqlalchemy.orm import Session

from app.models.store_target import StoreTarget


class StoreTargetRepository:

    @staticmethod
    def create(
        db: Session,
        target: StoreTarget
    ) -> StoreTarget:

        db.add(target)
        db.commit()
        db.refresh(target)

        return target

    @staticmethod
    def get_by_id(
        db: Session,
        target_id: int
    ) -> StoreTarget | None:

        return (
            db.query(StoreTarget)
            .filter(StoreTarget.id == target_id)
            .first()
        )

    @staticmethod
    def get_all(
        db: Session,
        store_id: int | None = None
    ) -> list[StoreTarget]:

        query = db.query(StoreTarget)

        if store_id is not None:
            query = query.filter(
                StoreTarget.store_id == store_id
            )

        return (
            query
            .order_by(StoreTarget.id.desc())
            .all()
        )

    @staticmethod
    def update(
        db: Session,
        target: StoreTarget
    ) -> StoreTarget:

        db.commit()
        db.refresh(target)

        return target
    