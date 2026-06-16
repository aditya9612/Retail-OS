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

    def list_orders(self, tenant_id: int, store_id: Optional[int] = None, skip: int = 0, limit: int = 20) -> List[Order]:
        query = self.db.query(Order).options(joinedload(Order.items)).filter(Order.tenant_id == tenant_id)
        if store_id:
            query = query.filter(Order.store_id == store_id)
        return query.order_by(Order.created_at.desc()).offset(skip).limit(limit).all()

    def create(self, order: Order) -> Order:
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def update(self, order: Order) -> Order:
        self.db.commit()
        self.db.refresh(order)
        return order
