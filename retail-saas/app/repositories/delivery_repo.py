from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.delivery import Delivery
from app.models.delivery_method import DeliveryMethod
from app.models.delivery_zone import DeliveryZone
from app.models.delivery_partner import DeliveryPartner
from app.models.order import OrderTracking


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

    def get_by_order_id(
        self,
        order_id: int,
        tenant_id: int,
    ) -> Delivery | None:
        return (
            self.db.query(Delivery)
            .filter(
                Delivery.order_id == order_id,
                Delivery.tenant_id == tenant_id,
            )
            .first()
        )

    def create(
        self,
        delivery: Delivery,
    ) -> Delivery:
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def update(
        self,
        delivery: Delivery,
    ) -> Delivery:

        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def get_latest_tracking(
        self,
        order_id: int,
    ) -> OrderTracking | None:
        return (
            self.db.query(OrderTracking)
            .filter(OrderTracking.order_id == order_id)
            .order_by(OrderTracking.created_at.desc(), OrderTracking.id.desc())
            .first()
        )

    def get_tracking_history(
        self,
        order_id: int,
    ) -> list[OrderTracking]:
        return (
            self.db.query(OrderTracking)
            .filter(OrderTracking.order_id == order_id)
            .order_by(OrderTracking.created_at.desc(), OrderTracking.id.desc())
            .all()
        )

    def get_stats(
        self,
        tenant_id: int,
    ) -> dict[str, int]:
        results = (
            self.db.query(
                Delivery.status,
                func.count(Delivery.id),
            )
            .filter(Delivery.tenant_id == tenant_id)
            .group_by(Delivery.status)
            .all()
        )
        counts = {status: count for status, count in results}
        total = sum(counts.values())
        return {
            "total_deliveries": total,
            "pending_deliveries": counts.get("pending", 0),
            "assigned_deliveries": counts.get("assigned", 0),
            "out_for_delivery_deliveries": counts.get("out_for_delivery", 0),
            "delivered_deliveries": counts.get("delivered", 0),
            "cancelled_deliveries": counts.get("cancelled", 0),
        }

    def get_for_export(
        self,
        tenant_id: int,
        status: str | None = None,
    ) -> list[Delivery]:
        query = self.db.query(Delivery).filter(Delivery.tenant_id == tenant_id)
        if status:
            query = query.filter(Delivery.status == status)
        return query.order_by(Delivery.created_at.desc()).all()

    def list_methods(
        self,
        tenant_id: int,
        is_active: bool | None = None,
    ) -> list[DeliveryMethod]:
        query = self.db.query(DeliveryMethod).filter(
            DeliveryMethod.tenant_id == tenant_id,
        )
        if is_active is not None:
            query = query.filter(DeliveryMethod.is_active == is_active)
        return query.order_by(DeliveryMethod.id.asc()).all()

    def get_method_by_id(
        self,
        method_id: int,
        tenant_id: int,
    ) -> DeliveryMethod | None:
        return (
            self.db.query(DeliveryMethod)
            .filter(
                DeliveryMethod.id == method_id,
                DeliveryMethod.tenant_id == tenant_id,
            )
            .first()
        )

    def get_method_by_code(
        self,
        code: str,
        tenant_id: int,
    ) -> DeliveryMethod | None:
        return (
            self.db.query(DeliveryMethod)
            .filter(
                DeliveryMethod.code == code,
                DeliveryMethod.tenant_id == tenant_id,
            )
            .first()
        )

    def create_method(
        self,
        method: DeliveryMethod,
    ) -> DeliveryMethod:
        self.db.add(method)
        self.db.commit()
        self.db.refresh(method)
        return method

    def update_method(
        self,
        method: DeliveryMethod,
    ) -> DeliveryMethod:
        self.db.commit()
        self.db.refresh(method)
        return method

    def delete_method(
        self,
        method: DeliveryMethod,
    ) -> None:
        self.db.delete(method)
        self.db.commit()

    def list_zones(
        self,
        tenant_id: int,
        is_active: bool | None = None,
    ) -> list[DeliveryZone]:
        query = self.db.query(DeliveryZone).filter(
            DeliveryZone.tenant_id == tenant_id,
        )
        if is_active is not None:
            query = query.filter(DeliveryZone.is_active == is_active)
        return query.order_by(DeliveryZone.id.asc()).all()

    def get_zone_by_id(
        self,
        zone_id: int,
        tenant_id: int,
    ) -> DeliveryZone | None:
        return (
            self.db.query(DeliveryZone)
            .filter(
                DeliveryZone.id == zone_id,
                DeliveryZone.tenant_id == tenant_id,
            )
            .first()
        )

    def get_zone_by_code(
        self,
        code: str,
        tenant_id: int,
    ) -> DeliveryZone | None:
        return (
            self.db.query(DeliveryZone)
            .filter(
                DeliveryZone.code == code,
                DeliveryZone.tenant_id == tenant_id,
            )
            .first()
        )

    def create_zone(
        self,
        zone: DeliveryZone,
    ) -> DeliveryZone:
        self.db.add(zone)
        self.db.commit()
        self.db.refresh(zone)
        return zone

    def update_zone(
        self,
        zone: DeliveryZone,
    ) -> DeliveryZone:
        self.db.commit()
        self.db.refresh(zone)
        return zone

    def delete_zone(
        self,
        zone: DeliveryZone,
    ) -> None:
        self.db.delete(zone)
        self.db.commit()

    def list_partners(
        self,
        tenant_id: int,
        is_active: bool | None = None,
    ) -> list[DeliveryPartner]:
        query = self.db.query(DeliveryPartner).filter(
            DeliveryPartner.tenant_id == tenant_id,
        )
        if is_active is not None:
            query = query.filter(DeliveryPartner.is_active == is_active)
        return query.order_by(DeliveryPartner.id.asc()).all()

    def get_partner_by_id(
        self,
        partner_id: int,
        tenant_id: int,
    ) -> DeliveryPartner | None:
        return (
            self.db.query(DeliveryPartner)
            .filter(
                DeliveryPartner.id == partner_id,
                DeliveryPartner.tenant_id == tenant_id,
            )
            .first()
        )

    def get_partner_by_code(
        self,
        code: str,
        tenant_id: int,
    ) -> DeliveryPartner | None:
        return (
            self.db.query(DeliveryPartner)
            .filter(
                DeliveryPartner.code == code,
                DeliveryPartner.tenant_id == tenant_id,
            )
            .first()
        )

    def create_partner(
        self,
        partner: DeliveryPartner,
    ) -> DeliveryPartner:
        self.db.add(partner)
        self.db.commit()
        self.db.refresh(partner)
        return partner

    def update_partner(
        self,
        partner: DeliveryPartner,
    ) -> DeliveryPartner:
        self.db.commit()
        self.db.refresh(partner)
        return partner

    def delete_partner(
        self,
        partner: DeliveryPartner,
    ) -> None:
        self.db.delete(partner)
        self.db.commit()

    def find_active_zone_by_pincode(
        self,
        tenant_id: int,
        pincode: str,
    ) -> DeliveryZone | None:
        active_zones = (
            self.db.query(DeliveryZone)
            .filter(
                DeliveryZone.tenant_id == tenant_id,
                DeliveryZone.is_active == True,
            )
            .all()
        )
        for zone in active_zones:
            if zone.pincodes and pincode in zone.pincodes:
                return zone
        return None

