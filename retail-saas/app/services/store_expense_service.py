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

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    @staticmethod
    def create_expense(
        db: Session,
        data: StoreExpenseCreate,
        created_by: Optional[int] = None,
        tenant_id: int = None,
    ):
        # Verify store
        from app.models.store import Store

        query = db.query(Store).filter(Store.id == data.store_id)
        if tenant_id is not None:
            query = query.filter(Store.tenant_id == tenant_id)
        store = query.first()

        if not store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Store not found",
            )

        effective_tenant_id = tenant_id if tenant_id is not None else store.tenant_id

        # Validate duplicate reference number
        if data.reference_number:
            existing_ref = StoreExpenseRepository.get_by_reference_number(
                db=db,
                reference_number=data.reference_number,
                tenant_id=effective_tenant_id,
            )
            if existing_ref:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Reference number already exists",
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

        created_expense = StoreExpenseRepository.create(
            db,
            expense,
        )

        print("AMOUNT VALUE:", created_expense.amount)
        print("AMOUNT TYPE:", type(created_expense.amount))
        return created_expense

    @staticmethod
    def get_expense(
        db: Session,
        expense_id: int,
        tenant_id: int,
    ):
        expense = StoreExpenseRepository.get_by_id(
            db,
            expense_id,
            tenant_id=tenant_id,
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
        tenant_id: int,
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

        if store_id is not None:
            from app.models.store import Store

            store = (
                db.query(Store)
                .filter(
                    Store.id == store_id,
                    Store.tenant_id == tenant_id,
                )
                .first()
            )

            if not store:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Store not found",
                )

        return StoreExpenseRepository.get_all(
            db=db,
            tenant_id=tenant_id,
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
        tenant_id: int,
    ):
        expense = StoreExpenseRepository.get_by_id(
            db,
            expense_id,
            tenant_id=tenant_id,
        )

        if not expense or expense.status == "deleted":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Expense not found",
            )

        # Prevent store reassignment on update
        if data.store_id is not None and data.store_id != expense.store_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Store ID cannot be changed for an existing expense",
            )

        # Check duplicate reference number
        if data.reference_number is not None and data.reference_number.strip() != "":
            existing_ref = StoreExpenseRepository.get_by_reference_number(
                db=db,
                reference_number=data.reference_number.strip(),
                tenant_id=tenant_id,
                exclude_id=expense_id,
            )
            if existing_ref:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Reference number already exists",
                )

        # Validate reference_number and expense_date correlation
        target_ref = data.reference_number if data.reference_number is not None else expense.reference_number
        target_date = data.expense_date if data.expense_date is not None else expense.expense_date
        if target_ref and target_date:
            from app.schemas.store_expense import validate_reference_number_date
            try:
                validate_reference_number_date(target_ref, target_date)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                )

        update_data = data.model_dump(
            exclude_unset=True
        )

        # store_id is immutable during update, remove to ensure store assignment is never modified
        update_data.pop("store_id", None)

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
        tenant_id: int,
    ):
        expense = StoreExpenseRepository.get_by_id(
            db,
            expense_id,
            tenant_id=tenant_id,
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
        tenant_id: int,
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
            tenant_id=tenant_id,
            store_id=store_id,
            start_date=start_date,
            end_date=end_date,
        )

    @staticmethod
    def get_categories(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
    ):
        return StoreExpenseRepository.get_categories(
            db=db,
            tenant_id=tenant_id,
            store_id=store_id,
        )
