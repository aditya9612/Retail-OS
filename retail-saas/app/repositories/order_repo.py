from datetime import datetime
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.order import Order


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, order_id: int, tenant_id: int) -> Optional[Order]:
        return (
            self.db.query(Order)
            .options(joinedload(Order.items))
            .filter(Order.id == order_id, Order.tenant_id == tenant_id)
            .first()
        )

    def get_by_number(self, order_number: str, tenant_id: int) -> Optional[Order]:
        return (
            self.db.query(Order)
            .options(joinedload(Order.items))
            .filter(Order.order_number == order_number, Order.tenant_id == tenant_id)
            .first()
        )

    def list_orders(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        order_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[Order]:
        query = self.db.query(Order).options(joinedload(Order.items)).filter(Order.tenant_id == tenant_id)
        if store_id is not None:
            query = query.filter(Order.store_id == store_id)
        if status is not None:
            query = query.filter(Order.status == status)
        if customer_id is not None:
            query = query.filter(Order.customer_id == customer_id)
        if order_type is not None:
            query = query.filter(Order.order_type == order_type)
        if date_from is not None:
            query = query.filter(Order.created_at >= date_from)
        if date_to is not None:
            query = query.filter(Order.created_at <= date_to)
        if search:
            search_pattern = f"%{search.strip()}%"
            query = query.filter(
                (Order.order_number.ilike(search_pattern)) |
                (Order.notes.ilike(search_pattern)) |
                (Order.coupon_code.ilike(search_pattern))
            )
        return query.order_by(Order.created_at.desc()).offset(skip).limit(limit).all()

    def count_orders(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        order_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
    ) -> int:
        query = self.db.query(Order).filter(Order.tenant_id == tenant_id)
        if store_id is not None:
            query = query.filter(Order.store_id == store_id)
        if status is not None:
            query = query.filter(Order.status == status)
        if customer_id is not None:
            query = query.filter(Order.customer_id == customer_id)
        if order_type is not None:
            query = query.filter(Order.order_type == order_type)
        if date_from is not None:
            query = query.filter(Order.created_at >= date_from)
        if date_to is not None:
            query = query.filter(Order.created_at <= date_to)
        if search:
            search_pattern = f"%{search.strip()}%"
            query = query.filter(
                (Order.order_number.ilike(search_pattern)) |
                (Order.notes.ilike(search_pattern)) |
                (Order.coupon_code.ilike(search_pattern))
            )
        return query.count()

    def get_order_counts(self, tenant_id: int, store_id: Optional[int] = None) -> dict[str, int]:
        """Return order status breakdown counts in a single grouped query."""
        query = self.db.query(Order.status, func.count(Order.id)).filter(Order.tenant_id == tenant_id)
        if store_id is not None:
            query = query.filter(Order.store_id == store_id)
        rows = query.group_by(Order.status).all()
        by_status = {str(s).lower(): int(c) for s, c in rows if s is not None}
        return {
            "total": sum(by_status.values()),
            "draft": by_status.get("draft", 0),
            "pending": by_status.get("pending", 0),
            "confirmed": by_status.get("confirmed", 0),
            "processing": by_status.get("processing", 0),
            "packed": by_status.get("packed", 0),
            "dispatched": by_status.get("dispatched", 0),
            "out_for_delivery": by_status.get("out_for_delivery", 0),
            "delivered": by_status.get("delivered", 0),
            "completed": by_status.get("completed", 0),
            "cancelled": by_status.get("cancelled", 0),
        }

    def create(self, order: Order, commit: bool = True) -> Order:
        self.db.add(order)
        if commit:
            self.db.commit()
            self.db.refresh(order)
        else:
            self.db.flush()
        return order

    def update(self, order: Order) -> Order:
        self.db.commit()
        self.db.refresh(order)
        return order
