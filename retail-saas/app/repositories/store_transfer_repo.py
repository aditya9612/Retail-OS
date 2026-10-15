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
    def get_by_id(db: Session, transfer_id: int, tenant_id: int):
        from app.models.store import Store
        from app.models.store_transfer_item import StoreTransferItem

        return (
            db.query(StoreTransfer)
            .options(
                joinedload(StoreTransfer.items).joinedload(StoreTransferItem.product),
                joinedload(StoreTransfer.source_store),
                joinedload(StoreTransfer.destination_store),
                joinedload(StoreTransfer.approver),
            )
            .join(Store, StoreTransfer.source_store_id == Store.id)
            .filter(
                StoreTransfer.id == transfer_id,
                Store.tenant_id == tenant_id,
            )
            .first()
        )

    @staticmethod
    def get_all(
        db: Session,
        tenant_id: int,
        source_store_id: int | None = None,
        destination_store_id: int | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
    ):
        from sqlalchemy import func
        from app.models.store import Store
        from app.models.store_transfer_item import StoreTransferItem

        query = (
            db.query(StoreTransfer)
            .options(
                joinedload(StoreTransfer.items).joinedload(StoreTransferItem.product),
                joinedload(StoreTransfer.source_store),
                joinedload(StoreTransfer.destination_store),
                joinedload(StoreTransfer.approver),
            )
            .join(Store, StoreTransfer.source_store_id == Store.id)
            .filter(Store.tenant_id == tenant_id)
        )

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
                func.lower(StoreTransfer.status) == status.strip().lower()
            )

        if search:
            search_term = f"%{search.strip()}%"
            query = query.filter(
                StoreTransfer.transfer_number.ilike(search_term)
            )

        query = query.order_by(StoreTransfer.id.desc())

        if skip > 0:
            query = query.offset(skip)
        if limit is not None and limit > 0:
            query = query.limit(limit)

        return query.all()

    @staticmethod
    def update(db: Session, transfer: StoreTransfer):
        db.commit()
        db.refresh(transfer)
        return transfer