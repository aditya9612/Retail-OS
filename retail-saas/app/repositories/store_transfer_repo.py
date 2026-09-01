from sqlalchemy.orm import Session, joinedload

from app.models.store_transfer import StoreTransfer


class StoreTransferRepository:

    @staticmethod
    def create(db: Session, transfer: StoreTransfer):
        db.add(transfer)
        db.commit()
        db.refresh(transfer)
        return transfer

    @staticmethod
    def get_by_id(db: Session, transfer_id: int):
        return (
            db.query(StoreTransfer)
            .options(joinedload(StoreTransfer.items))
            .filter(StoreTransfer.id == transfer_id)
            .first()
        )

    @staticmethod
    def get_all(
        db: Session,
        source_store_id: int | None = None,
        destination_store_id: int | None = None,
        status: str | None = None
    ):
        query = db.query(StoreTransfer)

        if source_store_id is not None:
            query = query.filter(
                StoreTransfer.source_store_id == source_store_id
            )

        if destination_store_id is not None:
            query = query.filter(
                StoreTransfer.destination_store_id == destination_store_id
            )

        if status is not None:
            query = query.filter(
                StoreTransfer.status == status
            )

        return query.order_by(StoreTransfer.id.desc()).all()

    @staticmethod
    def update(db: Session, transfer: StoreTransfer):
        db.commit()
        db.refresh(transfer)
        return transfer