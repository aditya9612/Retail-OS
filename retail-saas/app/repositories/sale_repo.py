from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from app.models.sale import Sale


class SaleRepository:

    @staticmethod
    def create(
        db: Session,
        sale: Sale
    ):
        try:
            db.add(sale)
            db.commit()
            db.refresh(sale)
            return sale
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_by_id(
        db: Session,
        sale_id: int,
        tenant_id: int
    ):
        return (
            db.query(Sale)
            .options(joinedload(Sale.items))
            .filter(Sale.id == sale_id, Sale.tenant_id == tenant_id)
            .first()
        )

    @staticmethod
    def get_all(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        payment_method: Optional[str] = None,
        payment_status: Optional[str] = None,
        search: Optional[str] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ):
        query = (
            db.query(Sale)
            .options(joinedload(Sale.items))
            .filter(Sale.tenant_id == tenant_id)
        )

        if store_id is not None:
            query = query.filter(Sale.store_id == store_id)

        if start_date is not None:
            query = query.filter(Sale.created_at >= datetime.combine(start_date, datetime.min.time()))

        if end_date is not None:
            query = query.filter(Sale.created_at <= datetime.combine(end_date, datetime.max.time()))

        if payment_method:
            query = query.filter(func.lower(Sale.payment_method) == payment_method.strip().lower())

        if payment_status:
            query = query.filter(func.lower(Sale.payment_status) == payment_status.strip().lower())

        if search:
            search_clean = f"%{search.strip()}%"
            query = query.filter(Sale.sale_number.ilike(search_clean))

        query = query.order_by(Sale.id.desc())

        if page is not None and page_size is not None:
            query = query.offset((page - 1) * page_size).limit(page_size)
        elif page_size is not None:
            query = query.limit(page_size)

        return query.all()

    @staticmethod
    def get_summary(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ):
        query = db.query(Sale).filter(Sale.tenant_id == tenant_id)

        if store_id is not None:
            query = query.filter(Sale.store_id == store_id)

        if start_date is not None:
            query = query.filter(Sale.created_at >= datetime.combine(start_date, datetime.min.time()))

        if end_date is not None:
            query = query.filter(Sale.created_at <= datetime.combine(end_date, datetime.max.time()))

        sales = query.all()
        total_sales_count = len(sales)
        total_revenue = Decimal("0.00")
        total_subtotal = Decimal("0.00")
        total_tax = Decimal("0.00")
        total_discount = Decimal("0.00")
        payment_methods = {}
        payment_statuses = {}

        for s in sales:
            p_status = (s.payment_status or "paid").lower()
            payment_statuses[p_status] = payment_statuses.get(p_status, 0) + 1

            p_method = (s.payment_method or "cash").lower()

            if p_status not in ("cancelled", "voided"):
                total_revenue += Decimal(str(s.total_amount or 0))
                total_subtotal += Decimal(str(s.subtotal or 0))
                total_tax += Decimal(str(s.tax_amount or 0))
                total_discount += Decimal(str(getattr(s, "discount", 0) or 0))
                payment_methods[p_method] = round(payment_methods.get(p_method, 0.0) + float(s.total_amount or 0), 2)

        return {
            "total_sales_count": total_sales_count,
            "total_revenue": float(total_revenue.quantize(Decimal("0.01"))),
            "total_subtotal": float(total_subtotal.quantize(Decimal("0.01"))),
            "total_tax": float(total_tax.quantize(Decimal("0.01"))),
            "total_discount": float(total_discount.quantize(Decimal("0.01"))),
            "payment_methods": payment_methods,
            "payment_statuses": payment_statuses,
        }

    @staticmethod
    def update(
        db: Session,
        sale: Sale
    ):
        try:
            db.commit()
            db.refresh(sale)
            return sale
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def delete(
        db: Session,
        sale: Sale
    ):
        try:
            db.delete(sale)
            db.commit()
        except Exception:
            db.rollback()
            raise
