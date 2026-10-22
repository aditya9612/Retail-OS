from datetime import datetime
from typing import List, Optional

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
