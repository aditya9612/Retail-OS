from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.store_expense import (
    StoreExpenseAnalyticsSummary,
    StoreExpenseCreate,
    StoreExpenseDailyReportResponse,
    StoreExpenseResponse,
    StoreExpenseUpdate,
)
from app.services.store_expense_service import StoreExpenseService


router = APIRouter(
    prefix="/store-expenses",
    tags=["Store Expenses"],
)


@router.post(
    "",
    response_model=StoreExpenseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_store_expense(
    expense: StoreExpenseCreate,
    user: User = Depends(
        require_permission("store_expenses:write")
    ),
    db: Session = Depends(get_db),
):
    return StoreExpenseService.create_expense(
        db=db,
        data=expense,
        created_by=user.id,
        tenant_id=user.tenant_id,
    )


@router.get(
    "",
    response_model=list[StoreExpenseResponse],
)
def get_store_expenses(
    store_id: Optional[int] = Query(
        None,
        gt=0,
        description="Filter expenses by store ID (optional, omit to view all stores in tenant)",
    ),
    category: Optional[str] = Query(
        None,
        description="Filter expenses by category (e.g. Rent, Utilities, Salary)",
    ),
    payment_method: Optional[str] = Query(
        None,
        description="Filter expenses by payment method (cash, card, upi, bank_transfer, cheque, other)",
    ),
    start_date: Optional[date] = Query(
        None,
        description="Filter expenses from this date (YYYY-MM-DD)",
    ),
    end_date: Optional[date] = Query(
        None,
        description="Filter expenses until this date (YYYY-MM-DD)",
    ),
    skip: int = Query(
        0,
        ge=0,
        description="Number of records to skip for pagination",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of records to return",
    ),
    user: User = Depends(
        require_permission("store_expenses:read")
    ),
    db: Session = Depends(get_db),
):
    return StoreExpenseService.get_expenses(
        db=db,
        tenant_id=user.tenant_id,
        store_id=store_id,
        category=category,
        payment_method=payment_method,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/summary",
    response_model=StoreExpenseAnalyticsSummary,
    description="Get comprehensive expense analytics, category breakdown, payment method breakdown, and store comparison",
)
def get_store_expenses_summary(
    store_id: Optional[int] = Query(
        None,
        gt=0,
        description="Filter summary by store ID",
    ),
    category: Optional[str] = Query(
        None,
        description="Filter summary by category",
    ),
    start_date: Optional[date] = Query(
        None,
        description="Start date (YYYY-MM-DD)",
    ),
    end_date: Optional[date] = Query(
        None,
        description="End date (YYYY-MM-DD)",
    ),
    user: User = Depends(
        require_permission("store_expenses:read")
    ),
    db: Session = Depends(get_db),
):
    return StoreExpenseService.get_analytics_summary(
        db=db,
        tenant_id=user.tenant_id,
        store_id=store_id,
        category=category,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/daily-report",
    response_model=StoreExpenseDailyReportResponse,
    description="Get day-end store expense reconciliation report for cash drawer balancing",
)
def get_store_expenses_daily_report(
    store_id: Optional[int] = Query(
        None,
        gt=0,
        description="Filter daily report by store ID",
    ),
    report_date: Optional[date] = Query(
        None,
        description="Date of the report (defaults to today YYYY-MM-DD)",
    ),
    user: User = Depends(
        require_permission("store_expenses:read")
    ),
    db: Session = Depends(get_db),
):
    return StoreExpenseService.get_daily_report(
        db=db,
        tenant_id=user.tenant_id,
        store_id=store_id,
        report_date=report_date,
    )



@router.get(
    "/{expense_id}",
    response_model=StoreExpenseResponse,
    description="Get details of a specific store expense by ID",
)
def get_store_expense(
    expense_id: int,
    user: User = Depends(
        require_permission("store_expenses:read")
    ),
    db: Session = Depends(get_db),
):
    if expense_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expense ID must be greater than 0",
        )

    return StoreExpenseService.get_expense(
        db=db,
        expense_id=expense_id,
        tenant_id=user.tenant_id,
    )
@router.put(
    "/{expense_id}",
    response_model=StoreExpenseResponse,
)
def update_store_expense(
    expense_id: int,
    expense: StoreExpenseUpdate,
    user: User = Depends(
        require_permission("store_expenses:write")
    ),
    db: Session = Depends(get_db),
):
    if expense_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expense ID must be greater than 0",
        )

    return StoreExpenseService.update_expense(
        db=db,
        expense_id=expense_id,
        data=expense,
        tenant_id=user.tenant_id,
    )


@router.delete(
    "/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Expense deleted successfully"}
    },
)
def delete_store_expense(
    expense_id: int,
    user: User = Depends(
        require_permission("store_expenses:write")
    ),
    db: Session = Depends(get_db),
):
    if expense_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expense ID must be greater than 0",
        )

    StoreExpenseService.delete_expense(
        db=db,
        expense_id=expense_id,
        tenant_id=user.tenant_id,
    )

    return None
