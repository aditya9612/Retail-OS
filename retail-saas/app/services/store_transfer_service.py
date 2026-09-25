from datetime import datetime

from sqlalchemy.orm import Session

from app.models.product import Product
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
        items: list,
        tenant_id: int
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

        if source_store.tenant_id != tenant_id:
            raise ValueError(
                "Source store does not belong to the user's tenant"
            )

        destination_store = db.query(Store).filter(
            Store.id == destination_store_id
        ).first()

        if not destination_store:
            raise ValueError(
                "Destination store not found"
            )

        if destination_store.tenant_id != tenant_id:
            raise ValueError(
                "Destination store does not belong to the user's tenant"
            )

        from app.models.product import Product

        for item in items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                raise ValueError(f"Product {item.product_id} not found")
            if product.tenant_id != tenant_id:
                raise ValueError(f"Product {item.product_id} does not belong to the user's tenant")
            if getattr(item, "quantity", 0) <= 0:
                raise ValueError(f"Quantity must be greater than 0 for product {item.product_id}")

        transfer_number = (
            f"TRF-{source_store_id}-"
            f"{destination_store_id}-"
            f"{db.query(StoreTransfer).count() + 1:05d}"
        )

        transfer = StoreTransfer(
            transfer_number=transfer_number,
            source_store_id=source_store_id,
            destination_store_id=destination_store_id,
            status="Pending",
            created_at=datetime.now()
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
        transfer_id: int,
        tenant_id: int
    ):
        transfer = StoreTransferRepository.get_by_id(
            db,
            transfer_id,
            tenant_id=tenant_id
        )

        if not transfer:
            raise ValueError("Transfer not found")

        return transfer

    @staticmethod
    def get_transfers(
        db: Session,
        tenant_id: int,
        source_store_id: int | None = None,
        destination_store_id: int | None = None,
        status: str | None = None
    ):
        return StoreTransferRepository.get_all(
            db,
            tenant_id=tenant_id,
            source_store_id=source_store_id,
            destination_store_id=destination_store_id,
            status=status
        )

    @staticmethod
    def approve_transfer(
        db: Session,
        transfer_id: int,
        approved_by: int,
        tenant_id: int
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id,
            tenant_id=tenant_id
        )

        if transfer.status not in ["Pending", "Draft"]:
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
        transfer_id: int,
        tenant_id: int
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id,
            tenant_id=tenant_id
        )

        if transfer.status not in ["Pending", "Draft"]:
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
        transfer_id: int,
        tenant_id: int
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id,
            tenant_id=tenant_id
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
        transfer_id: int,
        tenant_id: int
    ):
        transfer = StoreTransferService.get_transfer(
            db,
            transfer_id,
            tenant_id=tenant_id
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
