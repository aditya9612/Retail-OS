from collections import defaultdict
from datetime import date
from decimal import Decimal
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

        if not store.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Store is inactive or has been deleted",
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
            payment_method=data.payment_method.value if hasattr(data.payment_method, "value") else str(data.payment_method),
            reference_number=data.reference_number,
            created_by=created_by,
            status="active",
        )

        created_expense = StoreExpenseRepository.create(
            db,
            expense,
        )

        return StoreExpenseRepository.get_by_id(
            db=db,
            expense_id=created_expense.id,
            tenant_id=effective_tenant_id,
        ) or created_expense

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
        payment_method: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: Optional[int] = None,
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
            payment_method=payment_method,
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit,
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

        if "payment_method" in update_data and update_data["payment_method"] is not None:
            pm = update_data["payment_method"]
            update_data["payment_method"] = pm.value if hasattr(pm, "value") else str(pm)

        for field, value in update_data.items():
            setattr(expense, field, value)

        StoreExpenseRepository.update(
            db,
            expense,
        )

        return StoreExpenseRepository.get_by_id(
            db,
            expense_id=expense.id,
            tenant_id=tenant_id,
        ) or expense

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
    def get_analytics_summary(
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

        expenses = StoreExpenseRepository.get_all(
            db=db,
            tenant_id=tenant_id,
            store_id=store_id,
            category=category,
            start_date=start_date,
            end_date=end_date,
        )

        total_amount = Decimal("0.00")
        cash_amount = Decimal("0.00")
        total_count = len(expenses)

        category_totals = defaultdict(Decimal)
        category_counts = defaultdict(int)
        payment_totals = defaultdict(Decimal)
        payment_counts = defaultdict(int)
        store_totals = defaultdict(Decimal)
        store_counts = defaultdict(int)
        store_names = {}

        for exp in expenses:
            amt = Decimal(str(exp.amount))
            total_amount += amt

            pm = (exp.payment_method or "").lower()
            if pm == "cash":
                cash_amount += amt
            payment_totals[pm] += amt
            payment_counts[pm] += 1

            cat = exp.category or "Other"
            category_totals[cat] += amt
            category_counts[cat] += 1

            sid = exp.store_id
            store_totals[sid] += amt
            store_counts[sid] += 1
            if sid not in store_names and exp.store:
                store_names[sid] = exp.store.name

        digital_amount = total_amount - cash_amount

        categories_breakdown = []
        for cat, amt in sorted(category_totals.items(), key=lambda x: x[1], reverse=True):
            pct = float((amt / total_amount) * 100) if total_amount > 0 else 0.0
            categories_breakdown.append({
                "category": cat,
                "total_amount": amt,
                "percentage": round(pct, 2),
                "count": category_counts[cat],
            })
        payment_methods_breakdown = []
        for pm, amt in sorted(payment_totals.items(), key=lambda x: x[1], reverse=True):
            pct = float((amt / total_amount) * 100) if total_amount > 0 else 0.0
            payment_methods_breakdown.append({
                "payment_method": pm or "other",
                "total_amount": amt,
                "percentage": round(pct, 2),
                "count": payment_counts[pm],
            })

        store_comparison = []
        for sid, amt in sorted(store_totals.items(), key=lambda x: x[1], reverse=True):
            pct = float((amt / total_amount) * 100) if total_amount > 0 else 0.0
            store_comparison.append({
                "store_id": sid,
                "store_name": store_names.get(sid, f"Store {sid}"),
                "total_amount": amt,
                "percentage": round(pct, 2),
                "count": store_counts[sid],
            })

        return {
            "total_expenses": total_amount,
            "total_count": total_count,
            "cash_expenses": cash_amount,
            "digital_expenses": digital_amount,
            "categories_breakdown": categories_breakdown,
            "payment_methods_breakdown": payment_methods_breakdown,
            "store_comparison": store_comparison,
            "recent_expenses": expenses[:5],
        }

    @staticmethod
    def get_daily_report(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
        report_date: Optional[date] = None,
    ):
        if report_date is None:
            report_date = date.today()

        resolved_store_name = None
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
            resolved_store_name = store.name

        expenses = StoreExpenseRepository.get_daily_report_expenses(
            db=db,
            tenant_id=tenant_id,
            report_date=report_date,
            store_id=store_id,
        )

        total_amount = Decimal("0.00")
        cash_amount = Decimal("0.00")
        cash_count = 0

        for exp in expenses:
            amt = Decimal(str(exp.amount))
            total_amount += amt
            if (exp.payment_method or "").lower() == "cash":
                cash_amount += amt
                cash_count += 1

        non_cash_amount = total_amount - cash_amount

        return {
            "report_date": report_date,
            "store_id": store_id,
            "store_name": resolved_store_name,
            "total_expenses": total_amount,
            "total_count": len(expenses),
            "cash_expense_total": cash_amount,
            "non_cash_expense_total": non_cash_amount,
            "cash_drawer_payout_count": cash_count,
            "expenses": expenses,
        }

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
