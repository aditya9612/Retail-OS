
from fastapi import APIRouter, Depends, HTTPException, Query, status

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.store_expense import (
    StoreExpenseCreate,
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
    service = StoreExpenseService(db)

    return service.create_expense(expense)


@router.get(
    "",
    response_model=list[StoreExpenseResponse],
)
def get_store_expenses(
    store_id: int | None = Query(default=None, gt=0),
    user: User = Depends(
        require_permission("store_expenses:read")
    ),
    db: Session = Depends(get_db),
):
    service = StoreExpenseService(db)

    return service.get_expenses(store_id=store_id)


@router.get(
    "/{expense_id}",
    response_model=StoreExpenseResponse,
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

    service = StoreExpenseService(db)

    return service.get_expense(expense_id)


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

    service = StoreExpenseService(db)

    return service.update_expense(expense_id, expense)


@router.delete(
    "/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
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

    service = StoreExpenseService(db)

    service.delete_expense(expense_id)

    return None
