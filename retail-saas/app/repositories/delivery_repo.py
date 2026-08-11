from sqlalchemy.orm import Session

from app.models.delivery import Delivery


class DeliveryRepository:

    def __init__(self, db: Session):
        self.db = db

    def list_deliveries(
        self,
        tenant_id: int,
    ) -> list[Delivery]:

        return (
            self.db.query(Delivery)
            .filter(
                Delivery.tenant_id == tenant_id,
            )
            .order_by(Delivery.created_at.desc())
            .all()
        )

    def get_by_id(
        self,
        delivery_id: int,
        tenant_id: int,
    ) -> Delivery | None:

        return (
            self.db.query(Delivery)
            .filter(
                Delivery.id == delivery_id,
                Delivery.tenant_id == tenant_id,
            )
            .first()
        )

    def update(
        self,
        delivery: Delivery,
    ) -> Delivery:

        self.db.commit()
        self.db.refresh(delivery)
        return delivery