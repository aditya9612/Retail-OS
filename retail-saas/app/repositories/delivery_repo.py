from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.delivery import Delivery
from app.models.delivery_method import DeliveryMethod
from app.models.delivery_zone import DeliveryZone
from app.models.delivery_partner import DeliveryPartner
from app.models.order import Order, OrderTracking


class DeliveryRepository:

    def __init__(self, db: Session):
        self.db = db

    def list_deliveries(
        self,
        tenant_id: int,
        page: int | None = None,
        page_size: int | None = None,
        status: str | None = None,
        delivery_person: str | None = None,
        partner_id: int | None = None,
        order_id: int | None = None,
        is_cod: bool | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
    ) -> tuple[list[Delivery], int]:
        query = (
            self.db.query(Delivery)
            .options(
                joinedload(Delivery.order),
                joinedload(Delivery.partner),
                joinedload(Delivery.delivery_method),
                joinedload(Delivery.zone),
            )
            .filter(Delivery.tenant_id == tenant_id)
        )

        if status:
            s_clean = status.strip().lower()
            if s_clean != "all":
                query = query.filter(func.lower(Delivery.status) == s_clean)

        if delivery_person:
            query = query.filter(func.lower(Delivery.delivery_person).contains(delivery_person.strip().lower()))

        if partner_id is not None:
            query = query.filter(Delivery.partner_id == partner_id)

        if order_id is not None:
            query = query.filter(Delivery.order_id == order_id)

        if is_cod is not None:
            query = query.filter(Delivery.is_cod == is_cod)

        if date_from is not None:
            query = query.filter(Delivery.created_at >= date_from)

        if date_to is not None:
            query = query.filter(Delivery.created_at <= date_to)

        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            query = query.outerjoin(Delivery.order).filter(
                (func.lower(Delivery.tracking_number).like(term))
                | (func.lower(Delivery.delivery_person).like(term))
                | (func.lower(Order.order_number).like(term))
            )

        total = query.count()

        query = query.order_by(Delivery.created_at.desc(), Delivery.id.desc())

        if page is not None and page_size is not None:
            skip = (page - 1) * page_size
            items = query.offset(skip).limit(page_size).all()
        elif page_size is not None:
            items = query.limit(page_size).all()
        else:
            items = query.all()

        return items, total

    def get_by_id(
        self,
        delivery_id: int,
        tenant_id: int,
    ) -> Delivery | None:

        return (
            self.db.query(Delivery)
            .options(
                joinedload(Delivery.order),
                joinedload(Delivery.partner),
                joinedload(Delivery.delivery_method),
                joinedload(Delivery.zone),
            )
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

    def get_cod_reconciliation(
        self,
        tenant_id: int,
        delivery_person: str | None = None,
        partner_id: int | None = None,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict:
        query = (
            self.db.query(Delivery)
            .options(
                joinedload(Delivery.order),
                joinedload(Delivery.partner),
            )
            .filter(
                Delivery.tenant_id == tenant_id,
                Delivery.is_cod == True,
            )
        )

        if delivery_person:
            query = query.filter(func.lower(Delivery.delivery_person).contains(delivery_person.strip().lower()))

        if partner_id is not None:
            query = query.filter(Delivery.partner_id == partner_id)

        if status:
            s_clean = status.strip().lower()
            if s_clean == "collected":
                query = query.filter(Delivery.cod_collected == True)
            elif s_clean == "pending":
                query = query.filter(Delivery.cod_collected == False)

        if date_from is not None:
            query = query.filter(Delivery.created_at >= date_from)

        if date_to is not None:
            query = query.filter(Delivery.created_at <= date_to)

        deliveries = query.order_by(Delivery.created_at.desc()).all()

        total_cod_orders = len(deliveries)
        total_cod_amount = sum((d.cod_amount or Decimal("0.00")) for d in deliveries)

        collected = [d for d in deliveries if d.cod_collected]
        collected_orders_count = len(collected)
        total_collected_amount = sum((d.cod_amount or Decimal("0.00")) for d in collected)

        pending = [d for d in deliveries if not d.cod_collected]
        pending_orders_count = len(pending)
        total_pending_amount = sum((d.cod_amount or Decimal("0.00")) for d in pending)

        by_delivery_person: dict[str, Decimal] = {}
        for d in deliveries:
            person = d.delivery_person or (d.partner.name if d.partner else "Unassigned")
            by_delivery_person[person] = by_delivery_person.get(person, Decimal("0.00")) + (d.cod_amount or Decimal("0.00"))

        delivery_items = []
        for d in deliveries:
            delivery_items.append({
                "delivery_id": d.id,
                "order_id": d.order_id,
                "order_number": d.order.order_number if d.order else f"ORD-{d.order_id}",
                "delivery_person": d.delivery_person,
                "partner_id": d.partner_id,
                "partner_name": d.partner.name if d.partner else None,
                "cod_amount": d.cod_amount or Decimal("0.00"),
                "cod_collected": d.cod_collected,
                "cod_collected_at": d.cod_collected_at,
                "delivery_status": d.status,
                "delivered_at": d.delivered_at,
                "recipient_name": d.recipient_name,
                "recipient_phone": d.recipient_phone,
            })

        return {
            "summary": {
                "total_cod_orders": total_cod_orders,
                "total_cod_amount": total_cod_amount,
                "collected_orders_count": collected_orders_count,
                "total_collected_amount": total_collected_amount,
                "pending_orders_count": pending_orders_count,
                "total_pending_amount": total_pending_amount,
                "by_delivery_person": by_delivery_person,
            },
            "deliveries": delivery_items,
        }

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

