from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.grn import GRN
from app.models.purchase_order import PurchaseOrder


class GRNRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, grn: GRN) -> GRN:
        self.db.add(grn)
        self.db.commit()
        self.db.refresh(grn)
        return grn

    def list(
        self,
        tenant_id: int,
        purchase_order_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        store_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[GRN]:
        query = (
            self.db.query(GRN)
            .options(
                joinedload(GRN.items),
                joinedload(GRN.purchase_order),
                joinedload(GRN.warehouse),
                joinedload(GRN.store),
                joinedload(GRN.created_by),
                joinedload(GRN.received_by),
            )
            .filter(GRN.tenant_id == tenant_id)
        )
        if purchase_order_id is not None:
            query = query.filter(GRN.purchase_order_id == purchase_order_id)
        if warehouse_id is not None:
            query = query.filter(GRN.warehouse_id == warehouse_id)
        if store_id is not None:
            query = query.filter(GRN.store_id == store_id)
        if status:
            query = query.filter(GRN.status == status)

        if supplier_id is not None:
            query = query.join(GRN.purchase_order).filter(PurchaseOrder.supplier_id == supplier_id)

        if from_date is not None:
            query = query.filter(GRN.created_at >= datetime.combine(from_date, time.min))
        if to_date is not None:
            query = query.filter(GRN.created_at <= datetime.combine(to_date, time.max))

        if search:
            search_pattern = f"%{search.strip()}%"
            if supplier_id is None:
                query = query.outerjoin(GRN.purchase_order)
            query = query.filter(
                or_(
                    GRN.grn_number.ilike(search_pattern),
                    GRN.invoice_number.ilike(search_pattern),
                    GRN.remarks.ilike(search_pattern),
                    PurchaseOrder.order_number.ilike(search_pattern),
                )
            )

        query = query.order_by(GRN.created_at.desc())

        if page is not None and page_size is not None:
            offset_val = (page - 1) * page_size
            query = query.offset(offset_val).limit(page_size)
        elif skip is not None or limit is not None:
            if skip is not None:
                query = query.offset(skip)
            if limit is not None:
                query = query.limit(limit)

        return query.all()

    def get_by_id(
        self,
        grn_id: int,
        tenant_id: int,
    ) -> GRN | None:
        return (
            self.db.query(GRN)
            .options(
                joinedload(GRN.items),
                joinedload(GRN.purchase_order),
                joinedload(GRN.warehouse),
                joinedload(GRN.store),
                joinedload(GRN.created_by),
                joinedload(GRN.received_by),
            )
            .filter(
                GRN.id == grn_id,
                GRN.tenant_id == tenant_id,
            )
            .first()
        )

    def get_by_number(
        self,
        grn_number: str,
        tenant_id: int,
    ) -> GRN | None:
        trimmed = grn_number.strip()
        # 1. Exact match on GRN number (case-insensitive)
        grn = (
            self.db.query(GRN)
            .options(
                joinedload(GRN.items),
                joinedload(GRN.purchase_order),
                joinedload(GRN.warehouse),
                joinedload(GRN.store),
                joinedload(GRN.created_by),
                joinedload(GRN.received_by),
            )
            .filter(
                GRN.grn_number.ilike(trimmed),
                GRN.tenant_id == tenant_id,
            )
            .first()
        )
        if grn:
            return grn

        # 2. Fallback: if user passed integer ID instead of string GRN number
        if trimmed.isdigit():
            return (
                self.db.query(GRN)
                .options(
                    joinedload(GRN.items),
                    joinedload(GRN.purchase_order),
                    joinedload(GRN.warehouse),
                    joinedload(GRN.store),
                    joinedload(GRN.created_by),
                    joinedload(GRN.received_by),
                )
                .filter(
                    GRN.id == int(trimmed),
                    GRN.tenant_id == tenant_id,
                )
                .first()
            )

        return None

    def get_stats(self, tenant_id: int, store_id: Optional[int] = None) -> dict:
        today_start = datetime.combine(date.today(), time.min)
        base_q = self.db.query(func.count(GRN.id)).filter(GRN.tenant_id == tenant_id)
        if store_id is not None:
            base_q = base_q.filter(GRN.store_id == store_id)

        total_grns = base_q.scalar() or 0
        pending_grns = base_q.filter(GRN.status == "pending").scalar() or 0
        received_grns = base_q.filter(GRN.status == "received").scalar() or 0
        rejected_grns = base_q.filter(GRN.status == "rejected").scalar() or 0
        received_today = (
            base_q
            .filter(GRN.status == "received", GRN.received_at >= today_start)
            .scalar() or 0
        )

        rec_q = (
            self.db.query(GRN)
            .options(joinedload(GRN.items))
            .filter(GRN.tenant_id == tenant_id, GRN.status == "received")
        )
        if store_id is not None:
            rec_q = rec_q.filter(GRN.store_id == store_id)
        received_list = rec_q.all()
        total_inward_value = sum(g.total_cost_value for g in received_list) if received_list else Decimal("0.00")

        recent = (
            self.db.query(GRN)
            .options(
                joinedload(GRN.items),
                joinedload(GRN.purchase_order),
                joinedload(GRN.warehouse),
                joinedload(GRN.store),
            )
            .filter(GRN.tenant_id == tenant_id)
            .order_by(GRN.created_at.desc())
            .limit(5)
            .all()
        )

        return {
            "total_grns": total_grns,
            "pending_grns": pending_grns,
            "received_grns": received_grns,
            "rejected_grns": rejected_grns,
            "received_today": received_today,
            "total_inward_value": total_inward_value,
            "recent_grns": recent,
        }

    def update(
        self,
        grn: GRN,
    ) -> GRN:
        self.db.commit()
        self.db.refresh(grn)
        return grn

    def delete(
        self,
        grn: GRN,
    ) -> None:
        self.db.delete(grn)
        self.db.commit()

