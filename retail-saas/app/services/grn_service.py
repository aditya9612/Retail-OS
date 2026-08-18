from datetime import datetime

from app.core.exceptions import NotFoundException
from app.models.grn import GRN, GRNItem
from app.repositories.grn_repo import GRNRepository
from app.schemas.grn import GRNCreate


class GRNService:

    def __init__(self, db):
        self.repo = GRNRepository(db)

    def create(
        self,
        tenant_id: int,
        data: GRNCreate,
    ):

        grn_number = (
            f"GRN-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        )

        grn = GRN(
            tenant_id=tenant_id,
            purchase_order_id=data.purchase_order_id,
            warehouse_id=data.warehouse_id,
            grn_number=grn_number,
            status="pending",
            remarks=data.remarks,
        )

        for item in data.items:

            grn.items.append(
                GRNItem(
                    product_id=item.product_id,
                    ordered_quantity=item.ordered_quantity,
                    received_quantity=item.received_quantity,
                    remarks=item.remarks,
                )
            )

        return self.repo.create(grn)

    def list(
        self,
        tenant_id: int,
    ):

        return self.repo.list(tenant_id)

    def get(
        self,
        tenant_id: int,
        grn_id: int,
    ):

        grn = self.repo.get_by_id(
            grn_id,
            tenant_id,
        )

        if not grn:
            raise NotFoundException(
                "GRN not found"
            )

        return grn

    def receive(
        self,
        tenant_id: int,
        grn_id: int,
    ):

        grn = self.get(
            tenant_id,
            grn_id,
        )

        grn.status = "received"
        grn.received_at = datetime.utcnow()

        return self.repo.update(grn)

    def reject(
        self,
        tenant_id: int,
        grn_id: int,
    ):

        grn = self.get(
            tenant_id,
            grn_id,
        )

        grn.status = "rejected"

        return self.repo.update(grn)
    
    def history(
        self,
        tenant_id: int,
        grn_id: int,
    ):
        grn = self.get(
            tenant_id=tenant_id,
            grn_id=grn_id,
        )

        return {
            "grn_id": grn.id,
            "grn_number": grn.grn_number,
            "status": grn.status,
            "created_at": grn.created_at,
            "received_at": grn.received_at,
            "updated_at": grn.updated_at,
        }
        
    def print_grn(
        self,
        tenant_id: int,
        grn_id: int,
    ):
        grn = self.get(
            tenant_id=tenant_id,
            grn_id=grn_id,
        )

        return grn