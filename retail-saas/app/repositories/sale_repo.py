from datetime import date, datetime
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
