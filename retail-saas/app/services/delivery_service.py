from datetime import datetime

from app.core.exceptions import NotFoundException
from app.repositories.delivery_repo import DeliveryRepository
from app.models.order import OrderTracking

class DeliveryService:

    def __init__(self, db):
        self.db = db
        self.repo = DeliveryRepository(db)

    def list_deliveries(self, tenant_id):
        return self.repo.list_deliveries(tenant_id)

    def get_delivery(self, tenant_id, delivery_id):
        delivery = self.repo.get_by_id(delivery_id, tenant_id)

        if not delivery:
            raise NotFoundException("Delivery not found")

        return delivery

    def update_status(
        self,
        tenant_id,
        delivery_id,
        status,
    ):
        delivery = self.get_delivery(
            tenant_id,
            delivery_id,
        )

        delivery.status = status

        if status.lower() == "delivered":
            delivery.delivered_at = datetime.utcnow()
            
        tracking = OrderTracking(
             order_id=delivery.order_id,
             status=status,
             remarks=f"Order {status.replace('_', ' ')}",
            )
        
        print("Tracking object created:", tracking)

        self.db.add(tracking)


        return self.repo.update(delivery)