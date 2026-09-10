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
    ) -> Optional[StoreExpense]:
        return (
            db.query(StoreExpense)
            .filter(StoreExpense.id == expense_id)
            .first()
        )

    @staticmethod
    def get_all(
        db: Session,
        store_id: Optional[int] = None,
        category: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ):
        query = db.query(StoreExpense).filter(
            StoreExpense.status == "active"
        )

        if store_id is not None:
            query = query.filter(
                StoreExpense.store_id == store_id
            )

        if category:
            query = query.filter(
                StoreExpense.category == category
            )

        if start_date:
            query = query.filter(
                StoreExpense.expense_date >= start_date
            )

        if end_date:
            query = query.filter(
                StoreExpense.expense_date <= end_date
            )

        return query.order_by(
            StoreExpense.expense_date.desc(),
            StoreExpense.id.desc(),
        ).all()

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
        store_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ):
        query = db.query(
            StoreExpense.store_id,
            func.coalesce(
                func.sum(StoreExpense.amount),
                0,
            ).label("total_expenses"),
            func.count(StoreExpense.id).label("expense_count"),
        ).filter(
            StoreExpense.status == "active"
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
        store_id: Optional[int] = None,
    ):
        query = (
            db.query(StoreExpense.category)
            .filter(StoreExpense.status == "active")
            .distinct()
        )

        if store_id is not None:
            query = query.filter(
                StoreExpense.store_id == store_id
            )

        return query.order_by(
            StoreExpense.category
        ).all()