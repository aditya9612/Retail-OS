from sqlalchemy.orm import Session

from app.models.purchase_order import PurchaseOrder


class PurchaseOrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, purchase_order: PurchaseOrder) -> PurchaseOrder:
        self.db.add(purchase_order)
        self.db.commit()
        self.db.refresh(purchase_order)
        return purchase_order

    def get_by_id(
        self,
        purchase_order_id: int,
        tenant_id: int,
    ) -> PurchaseOrder | None:
        return (
            self.db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.id == purchase_order_id,
                PurchaseOrder.tenant_id == tenant_id,
            )
            .first()
        )

    def list_purchase_orders(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
    ) -> list[PurchaseOrder]:
        return (
            self.db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(
        self,
        purchase_order: PurchaseOrder,
    ) -> PurchaseOrder:
        self.db.commit()
        self.db.refresh(purchase_order)
        return purchase_order