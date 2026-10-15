from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.store_expense import StoreExpense


class StoreExpenseRepository:

    @staticmethod
    def create(
        db: Session,
        expense: StoreExpense,
    ) -> StoreExpense:
        db.add(expense)
        db.commit()
        db.refresh(expense)

        return expense

    @staticmethod
    def get_by_id(
        db: Session,
        expense_id: int,
        tenant_id: int,
    ) -> Optional[StoreExpense]:
        from sqlalchemy.orm import joinedload
        from app.models.store import Store

        return (
            db.query(StoreExpense)
            .options(
                joinedload(StoreExpense.store),
                joinedload(StoreExpense.creator),
            )
            .join(Store, StoreExpense.store_id == Store.id)
            .filter(
                StoreExpense.id == expense_id,
                Store.tenant_id == tenant_id,
            )
            .first()
        )

    @staticmethod
    def get_by_reference_number(
        db: Session,
        reference_number: str,
        tenant_id: int,
        exclude_id: Optional[int] = None,
    ) -> Optional[StoreExpense]:
        from app.models.store import Store

        query = (
            db.query(StoreExpense)
            .join(Store, StoreExpense.store_id == Store.id)
            .filter(
                StoreExpense.reference_number == reference_number,
                StoreExpense.status == "active",
                Store.tenant_id == tenant_id,
            )
        )

        if exclude_id is not None:
            query = query.filter(StoreExpense.id != exclude_id)

        return query.first()

    @staticmethod
    def get_all(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
        category: Optional[str] = None,
        payment_method: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: Optional[int] = None,
    ):
        from sqlalchemy.orm import joinedload
        from app.models.store import Store

        query = (
            db.query(StoreExpense)
            .options(
                joinedload(StoreExpense.store),
                joinedload(StoreExpense.creator),
            )
            .join(Store, StoreExpense.store_id == Store.id)
            .filter(
                StoreExpense.status == "active",
                Store.tenant_id == tenant_id,
            )
        )

        if store_id is not None:
            query = query.filter(
                StoreExpense.store_id == store_id
            )

        if category:
            query = query.filter(
                StoreExpense.category.ilike(category.strip())
            )

        if payment_method:
            query = query.filter(
                StoreExpense.payment_method == payment_method.strip().lower()
            )

        if start_date:
            query = query.filter(
                StoreExpense.expense_date >= start_date
            )

        if end_date:
            query = query.filter(
                StoreExpense.expense_date <= end_date
            )

        query = query.order_by(
            StoreExpense.expense_date.desc(),
            StoreExpense.id.desc(),
        )

        if skip > 0:
            query = query.offset(skip)
        if limit is not None and limit > 0:
            query = query.limit(limit)

        return query.all()

    @staticmethod
    def get_daily_report_expenses(
        db: Session,
        tenant_id: int,
        report_date: date,
        store_id: Optional[int] = None,
    ):
        from sqlalchemy.orm import joinedload
        from app.models.store import Store

        query = (
            db.query(StoreExpense)
            .options(
                joinedload(StoreExpense.store),
                joinedload(StoreExpense.creator),
            )
            .join(Store, StoreExpense.store_id == Store.id)
            .filter(
                StoreExpense.status == "active",
                Store.tenant_id == tenant_id,
                StoreExpense.expense_date == report_date,
            )
        )

        if store_id is not None:
            query = query.filter(StoreExpense.store_id == store_id)

        return query.order_by(StoreExpense.id.desc()).all()

    @staticmethod
    def update(
        db: Session,
        expense: StoreExpense,
    ) -> StoreExpense:
        db.commit()
        db.refresh(expense)

        return expense

    @staticmethod
    def delete(
        db: Session,
        expense: StoreExpense,
    ) -> StoreExpense:
        expense.status = "deleted"

        db.commit()
        db.refresh(expense)

        return expense

    @staticmethod
    def get_summary(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ):
        from app.models.store import Store

        query = (
            db.query(
                StoreExpense.store_id,
                func.coalesce(
                    func.sum(StoreExpense.amount),
                    0,
                ).label("total_expenses"),
                func.count(StoreExpense.id).label("expense_count"),
            )
            .join(Store, StoreExpense.store_id == Store.id)
            .filter(
                StoreExpense.status == "active",
                Store.tenant_id == tenant_id,
            )
        )

        if store_id is not None:
            query = query.filter(
                StoreExpense.store_id == store_id
            )

        if start_date:
            query = query.filter(
                StoreExpense.expense_date >= start_date
            )

        if end_date:
            query = query.filter(
                StoreExpense.expense_date <= end_date
            )

        return (
            query
            .group_by(StoreExpense.store_id)
            .order_by(StoreExpense.store_id)
            .all()
        )

    @staticmethod
    def get_categories(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
    ):
        from app.models.store import Store

        query = (
            db.query(StoreExpense.category)
            .join(Store, StoreExpense.store_id == Store.id)
            .filter(
                StoreExpense.status == "active",
                Store.tenant_id == tenant_id,
            )
            .distinct()
        )

        if store_id is not None:
            query = query.filter(
                StoreExpense.store_id == store_id
            )

        return query.order_by(
            StoreExpense.category
        ).all()