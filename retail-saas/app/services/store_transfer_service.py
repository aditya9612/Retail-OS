from sqlalchemy.orm import Session

from app.models.store import Store
from app.models.store_transfer import StoreTransfer
from app.models.store_transfer_item import StoreTransferItem
from app.repositories.store_transfer_repo import StoreTransferRepository


class StoreTransferService:

    @staticmethod
    def create_transfer(
        db: Session,
        source_store_id: int,
        destination_store_id: int,
        items: list
    ):
        if source_store_id == destination_store_id:
            raise ValueError(
                "Source and destination stores cannot be the same"
            )

        source_store = db.query(Store).filter(
            Store.id == source_store_id
        ).first()

        if not source_store:
            raise ValueError(
                "Source store not found"
            )

        destination_store = db.query(Store).filter(
            Store.id == destination_store_id
        ).first()

        if not destination_store:
            raise ValueError(
                "Destination store not found"
            )

        transfer_number = (
            f"TRF-{source_store_id}-"
            f"{destination_store_id}-"
            f"{StoreTransferRepository.get_all(db).__len__() + 1:05d}"
        )

        transfer = StoreTransfer(
            transfer_number=transfer_number,
            source_store_id=source_store_id,
            destination_store_id=destination_store_id,
            status="Draft"
        )

        for item in items:
            transfer.items.append(
                StoreTransferItem(
                    product_id=item.product_id,
                    quantity=item.quantity
                )
            )

        return StoreTransferRepository.create(db, transfer)

    @staticmethod
    def get_transfer(
        db: Session,
        transfer_id: int
    ):
        transfer = StoreTransferRepository.get_by_id(
            db,
            transfer_id
        )

        if not transfer:
            raise ValueError("Transfer not found")

        return transfer

    @staticmethod
    def get_transfers(
        db: Session,
        source_store_id: int | None = None,
        destination_store_id: int | None = None,
        status: str | None = None
    ):
        return StoreTransferRepository.get_all(
            db,
            source_store_id,
            destination_store_id,
            status
        )

    @staticmethod
    def approve_transfer(
        db: Session,
        transfer_id: int,
        approved_by: int
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id
        )

        if transfer.status != "Pending":
            raise ValueError(
                "Only pending transfers can be approved"
            )

        transfer.status = "Approved"
        transfer.approved_by = approved_by

        return StoreTransferRepository.update(
            db,
            transfer
        )

    @staticmethod
    def reject_transfer(
        db: Session,
        transfer_id: int
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id
        )

        if transfer.status != "Pending":
            raise ValueError(
                "Only pending transfers can be rejected"
            )

        transfer.status = "Rejected"

        return StoreTransferRepository.update(
            db,
            transfer
        )

    @staticmethod
    def dispatch_transfer(
        db: Session,
        transfer_id: int
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id
        )

        if transfer.status != "Approved":
            raise ValueError(
                "Only approved transfers can be dispatched"
            )

        transfer.status = "Dispatched"

        return StoreTransferRepository.update(
            db,
            transfer
        )

    @staticmethod
    def receive_transfer(
        db: Session,
        transfer_id: int
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id
        )

        if transfer.status != "Dispatched":
            raise ValueError(
                "Only dispatched transfers can be received"
            )

        transfer.status = "Received"

        return StoreTransferRepository.update(
            db,
            transfer
        )