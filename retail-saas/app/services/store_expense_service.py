from datetime import date
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.store_expense import StoreExpense
from app.repositories.store_expense_repo import (
    StoreExpenseRepository,
)
from app.schemas.store_expense import (
    StoreExpenseCreate,
    StoreExpenseUpdate,
)


class StoreExpenseService:

    @staticmethod
    def create_expense(
        db: Session,
        data: StoreExpenseCreate,
        created_by: Optional[int] = None,
    ):
        # Verify store
        from app.models.store import Store

        store = (
            db.query(Store)
            .filter(Store.id == data.store_id)
            .first()
        )

        if not store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Store not found",
            )

        expense = StoreExpense(
            store_id=data.store_id,
            amount=data.amount,
            category=data.category,
            description=data.description,
            expense_date=data.expense_date,
            payment_method=data.payment_method,
            reference_number=data.reference_number,
            created_by=created_by,
            status="active",
        )

        return StoreExpenseRepository.create(
            db,
            expense,
        )

    @staticmethod
    def get_expense(
        db: Session,
        expense_id: int,
    ):
        expense = StoreExpenseRepository.get_by_id(
            db,
            expense_id,
        )

        if not expense or expense.status == "deleted":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Expense not found",
            )

        return expense

    @staticmethod
    def get_expenses(
        db: Session,
        store_id: Optional[int] = None,
        category: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ):
        if (
            start_date
            and end_date
            and start_date > end_date
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date cannot be greater than end_date",
            )

        return StoreExpenseRepository.get_all(
            db=db,
            store_id=store_id,
            category=category,
            start_date=start_date,
            end_date=end_date,
        )

    @staticmethod
    def update_expense(
        db: Session,
        expense_id: int,
        data: StoreExpenseUpdate,
    ):
        expense = StoreExpenseRepository.get_by_id(
            db,
            expense_id,
        )

        if not expense or expense.status == "deleted":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Expense not found",
            )

        update_data = data.model_dump(
            exclude_unset=True
        )

        if "store_id" in update_data:
            from app.models.store import Store

            store = (
                db.query(Store)
                .filter(
                    Store.id == update_data["store_id"]
                )
                .first()
            )

            if not store:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Store not found",
                )

        for field, value in update_data.items():
            setattr(expense, field, value)

        return StoreExpenseRepository.update(
            db,
            expense,
        )

    @staticmethod
    def delete_expense(
        db: Session,
        expense_id: int,
    ):
        expense = StoreExpenseRepository.get_by_id(
            db,
            expense_id,
        )

        if not expense or expense.status == "deleted":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Expense not found",
            )

        return StoreExpenseRepository.delete(
            db,
            expense,
        )

    @staticmethod
    def get_summary(
        db: Session,
        store_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ):
        if (
            start_date
            and end_date
            and start_date > end_date
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date cannot be greater than end_date",
            )

        return StoreExpenseRepository.get_summary(
            db=db,
            store_id=store_id,
            start_date=start_date,
            end_date=end_date,
        )

    @staticmethod
    def get_categories(
        db: Session,
        store_id: Optional[int] = None,
    ):
        return StoreExpenseRepository.get_categories(
            db,
            store_id,
        )
