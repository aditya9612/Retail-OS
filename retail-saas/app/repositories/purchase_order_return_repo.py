from sqlalchemy.orm import Session, joinedload

from app.models.purchase_order_return import (
    PurchaseOrderReturn,
)


class PurchaseOrderReturnRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        purchase_order_return: PurchaseOrderReturn,
    ) -> PurchaseOrderReturn:

        self.db.add(purchase_order_return)
        self.db.commit()
        self.db.refresh(purchase_order_return)

        return purchase_order_return

    def get_by_id(
        self,
        return_id: int,
        tenant_id: int,
    ) -> PurchaseOrderReturn | None:

        return (
            self.db.query(PurchaseOrderReturn)
            .options(
                joinedload(PurchaseOrderReturn.items)
            )
            .filter(
                PurchaseOrderReturn.id == return_id,
                PurchaseOrderReturn.tenant_id == tenant_id,
            )
            .first()
        )

    def list_returns(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
    ) -> list[PurchaseOrderReturn]:

        return (
            self.db.query(PurchaseOrderReturn)
            .options(
                joinedload(PurchaseOrderReturn.items)
            )
            .filter(
                PurchaseOrderReturn.tenant_id == tenant_id
            )
            .order_by(
                PurchaseOrderReturn.created_at.desc()
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(
        self,
        purchase_order_return: PurchaseOrderReturn,
    ) -> PurchaseOrderReturn:

        self.db.commit()
        self.db.refresh(purchase_order_return)

        return purchase_order_return