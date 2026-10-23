from datetime import date
from typing import Optional
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.purchase_order import PurchaseOrder
from app.models.supplier import Supplier


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
            .options(
                joinedload(PurchaseOrder.items),
                joinedload(PurchaseOrder.supplier),
                joinedload(PurchaseOrder.store),
                joinedload(PurchaseOrder.warehouse),
                joinedload(PurchaseOrder.created_by),
                joinedload(PurchaseOrder.approved_by),
            )
            .filter(
                PurchaseOrder.id == purchase_order_id,
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.is_deleted == False,
            )
            .first()
        )

    def _build_filter_query(
        self,
        tenant_id: int,
        status: Optional[str] = None,
        supplier_id: Optional[int] = None,
        store_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        search: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        delivery_from_date: Optional[date] = None,
        delivery_to_date: Optional[date] = None,
    ):
        query = (
            self.db.query(PurchaseOrder)
            .outerjoin(Supplier, PurchaseOrder.supplier_id == Supplier.id)
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.is_deleted == False,
            )
        )

        if status:
            clean_status = status.strip().lower()
            query = query.filter(func.lower(PurchaseOrder.status) == clean_status)

        if supplier_id is not None:
            query = query.filter(PurchaseOrder.supplier_id == supplier_id)

        if store_id is not None:
            query = query.filter(PurchaseOrder.store_id == store_id)

        if warehouse_id is not None:
            query = query.filter(PurchaseOrder.warehouse_id == warehouse_id)

        if from_date:
            query = query.filter(func.date(PurchaseOrder.created_at) >= from_date)

        if to_date:
            query = query.filter(func.date(PurchaseOrder.created_at) <= to_date)

        if delivery_from_date:
            query = query.filter(PurchaseOrder.expected_delivery_date >= delivery_from_date)

        if delivery_to_date:
            query = query.filter(PurchaseOrder.expected_delivery_date <= delivery_to_date)

        if search:
            search_pattern = f"%{search.strip().lower()}%"
            query = query.filter(
                or_(
                    func.lower(PurchaseOrder.order_number).like(search_pattern),
                    func.lower(PurchaseOrder.invoice_number).like(search_pattern),
                    func.lower(Supplier.name).like(search_pattern),
                )
            )

        return query

    def list_purchase_orders(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        supplier_id: Optional[int] = None,
        store_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        search: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        delivery_from_date: Optional[date] = None,
        delivery_to_date: Optional[date] = None,
    ) -> list[PurchaseOrder]:
        query = self._build_filter_query(
            tenant_id=tenant_id,
            status=status,
            supplier_id=supplier_id,
            store_id=store_id,
            warehouse_id=warehouse_id,
            search=search,
            from_date=from_date,
            to_date=to_date,
            delivery_from_date=delivery_from_date,
            delivery_to_date=delivery_to_date,
        )

        return (
            query.options(
                joinedload(PurchaseOrder.items),
                joinedload(PurchaseOrder.supplier),
                joinedload(PurchaseOrder.store),
                joinedload(PurchaseOrder.warehouse),
                joinedload(PurchaseOrder.created_by),
                joinedload(PurchaseOrder.approved_by),
            )
            .order_by(PurchaseOrder.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_purchase_orders(
        self,
        tenant_id: int,
        status: Optional[str] = None,
        supplier_id: Optional[int] = None,
        store_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        search: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        delivery_from_date: Optional[date] = None,
        delivery_to_date: Optional[date] = None,
    ) -> int:
        query = self._build_filter_query(
            tenant_id=tenant_id,
            status=status,
            supplier_id=supplier_id,
            store_id=store_id,
            warehouse_id=warehouse_id,
            search=search,
            from_date=from_date,
            to_date=to_date,
            delivery_from_date=delivery_from_date,
            delivery_to_date=delivery_to_date,
        )
        return query.count()

    def update(
        self,
        purchase_order: PurchaseOrder,
    ) -> PurchaseOrder:
        self.db.commit()
        self.db.refresh(purchase_order)
        return purchase_order

    def delete(
        self,
        purchase_order: PurchaseOrder,
    ) -> None:
        self.db.delete(purchase_order)
        self.db.commit()