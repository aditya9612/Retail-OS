from datetime import date, datetime
from typing import Optional
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_return import (
    PurchaseOrderReturn,
)
from app.models.supplier import Supplier


class PurchaseOrderReturnRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        purchase_order_return: PurchaseOrderReturn,
    ) -> PurchaseOrderReturn:
        self.db.add(purchase_order_return)
        self.db.commit()
        self.db.refresh(purchase_order_return)
        return purchase_order_return

    def get_by_id(
        self,
        return_id: int,
        tenant_id: int,
    ) -> PurchaseOrderReturn | None:
        return (
            self.db.query(PurchaseOrderReturn)
            .options(
                joinedload(PurchaseOrderReturn.items),
                joinedload(PurchaseOrderReturn.purchase_order),
                joinedload(PurchaseOrderReturn.supplier),
                joinedload(PurchaseOrderReturn.store),
                joinedload(PurchaseOrderReturn.warehouse),
            )
            .filter(
                PurchaseOrderReturn.id == return_id,
                PurchaseOrderReturn.tenant_id == tenant_id,
            )
            .first()
        )

    def get_by_number(
        self,
        return_number: str,
        tenant_id: int,
    ) -> PurchaseOrderReturn | None:
        clean_num = str(return_number).strip().lower()
        return (
            self.db.query(PurchaseOrderReturn)
            .options(
                joinedload(PurchaseOrderReturn.items),
                joinedload(PurchaseOrderReturn.purchase_order),
                joinedload(PurchaseOrderReturn.supplier),
                joinedload(PurchaseOrderReturn.store),
                joinedload(PurchaseOrderReturn.warehouse),
            )
            .filter(
                PurchaseOrderReturn.tenant_id == tenant_id,
                or_(
                    func.lower(PurchaseOrderReturn.return_number) == clean_num,
                    func.lower(PurchaseOrderReturn.debit_note_number) == clean_num,
                ),
            )
            .first()
        )

    def _build_filtered_query(
        self,
        tenant_id: int,
        purchase_order_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        store_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        status: Optional[str] = None,
        from_date: Optional[date | datetime] = None,
        to_date: Optional[date | datetime] = None,
        search: Optional[str] = None,
    ):
        query = (
            self.db.query(PurchaseOrderReturn)
            .outerjoin(PurchaseOrder, PurchaseOrder.id == PurchaseOrderReturn.purchase_order_id)
            .outerjoin(Supplier, Supplier.id == PurchaseOrderReturn.supplier_id)
            .filter(PurchaseOrderReturn.tenant_id == tenant_id)
        )

        if purchase_order_id is not None:
            query = query.filter(PurchaseOrderReturn.purchase_order_id == purchase_order_id)

        if supplier_id is not None:
            query = query.filter(
                or_(
                    PurchaseOrderReturn.supplier_id == supplier_id,
                    PurchaseOrder.supplier_id == supplier_id,
                )
            )

        if store_id is not None:
            query = query.filter(
                or_(
                    PurchaseOrderReturn.store_id == store_id,
                    PurchaseOrder.store_id == store_id,
                )
            )

        if warehouse_id is not None:
            query = query.filter(
                or_(
                    PurchaseOrderReturn.warehouse_id == warehouse_id,
                    PurchaseOrder.warehouse_id == warehouse_id,
                )
            )

        if status:
            query = query.filter(PurchaseOrderReturn.status == status.strip().lower())

        if from_date:
            if isinstance(from_date, date) and not isinstance(from_date, datetime):
                from_dt = datetime.combine(from_date, datetime.min.time())
            else:
                from_dt = from_date
            query = query.filter(PurchaseOrderReturn.created_at >= from_dt)

        if to_date:
            if isinstance(to_date, date) and not isinstance(to_date, datetime):
                to_dt = datetime.combine(to_date, datetime.max.time())
            else:
                to_dt = to_date
            query = query.filter(PurchaseOrderReturn.created_at <= to_dt)

        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            query = query.filter(
                or_(
                    func.lower(PurchaseOrderReturn.return_number).like(term),
                    func.lower(PurchaseOrderReturn.debit_note_number).like(term),
                    func.lower(PurchaseOrderReturn.reason).like(term),
                    func.lower(PurchaseOrderReturn.remarks).like(term),
                    func.lower(PurchaseOrder.order_number).like(term),
                    func.lower(Supplier.name).like(term),
                )
            )

        return query

    def list_returns(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        purchase_order_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        store_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        status: Optional[str] = None,
        from_date: Optional[date | datetime] = None,
        to_date: Optional[date | datetime] = None,
        search: Optional[str] = None,
    ) -> list[PurchaseOrderReturn]:
        query = self._build_filtered_query(
            tenant_id=tenant_id,
            purchase_order_id=purchase_order_id,
            supplier_id=supplier_id,
            store_id=store_id,
            warehouse_id=warehouse_id,
            status=status,
            from_date=from_date,
            to_date=to_date,
            search=search,
        )

        return (
            query.options(
                joinedload(PurchaseOrderReturn.items),
                joinedload(PurchaseOrderReturn.purchase_order),
                joinedload(PurchaseOrderReturn.supplier),
                joinedload(PurchaseOrderReturn.store),
                joinedload(PurchaseOrderReturn.warehouse),
            )
            .order_by(PurchaseOrderReturn.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_returns(
        self,
        tenant_id: int,
        purchase_order_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        store_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        status: Optional[str] = None,
        from_date: Optional[date | datetime] = None,
        to_date: Optional[date | datetime] = None,
        search: Optional[str] = None,
    ) -> int:
        query = self._build_filtered_query(
            tenant_id=tenant_id,
            purchase_order_id=purchase_order_id,
            supplier_id=supplier_id,
            store_id=store_id,
            warehouse_id=warehouse_id,
            status=status,
            from_date=from_date,
            to_date=to_date,
            search=search,
        )
        return query.count()

    def update(
        self,
        purchase_order_return: PurchaseOrderReturn,
    ) -> PurchaseOrderReturn:
        self.db.commit()
        self.db.refresh(purchase_order_return)
        return purchase_order_return

    def delete(
        self,
        purchase_order_return: PurchaseOrderReturn,
    ) -> None:
        self.db.delete(purchase_order_return)
        self.db.commit()