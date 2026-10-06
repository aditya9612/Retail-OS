from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.order_item import OrderItem
from app.models.order_item_batch_allocation import OrderItemBatchAllocation


class OrderItemBatchAllocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, allocation_id: int) -> Optional[OrderItemBatchAllocation]:
        return self.db.get(OrderItemBatchAllocation, allocation_id)

    def create(self, allocation: OrderItemBatchAllocation) -> OrderItemBatchAllocation:
        self.db.add(allocation)
        self.db.flush()
        return allocation

    def bulk_create(
        self, allocations: List[OrderItemBatchAllocation]
    ) -> List[OrderItemBatchAllocation]:
        self.db.add_all(allocations)
        self.db.flush()
        return allocations

    def get_by_order_item_id(self, order_item_id: int) -> List[OrderItemBatchAllocation]:
        stmt = (
            select(OrderItemBatchAllocation)
            .where(OrderItemBatchAllocation.order_item_id == order_item_id)
            .order_by(OrderItemBatchAllocation.id.asc())
        )
        return self.db.execute(stmt).scalars().all()

    def get_by_order_id(self, order_id: int) -> List[OrderItemBatchAllocation]:
        stmt = (
            select(OrderItemBatchAllocation)
            .join(OrderItem, OrderItem.id == OrderItemBatchAllocation.order_item_id)
            .where(OrderItem.order_id == order_id)
            .order_by(OrderItemBatchAllocation.id.asc())
        )
        return self.db.execute(stmt).scalars().all()

    def get_by_batch_id(self, batch_id: int) -> List[OrderItemBatchAllocation]:
        stmt = (
            select(OrderItemBatchAllocation)
            .where(OrderItemBatchAllocation.batch_id == batch_id)
            .order_by(OrderItemBatchAllocation.id.asc())
        )
        return self.db.execute(stmt).scalars().all()

