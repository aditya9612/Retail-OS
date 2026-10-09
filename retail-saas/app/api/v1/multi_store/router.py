from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.multi_store_analytics import (
    StoreCustomerComparisonResponse,
    StoreInventoryComparisonResponse,
    StoreProfitComparisonResponse,
    StoreRevenueComparisonResponse,
)
from app.services.multi_store_analytics_service import MultiStoreAnalyticsService

router = APIRouter(
    prefix="/multi-store",
    tags=["Multi-Store Reports"],
)


def require_multi_store_read_permission(
    user: User = Depends(get_current_user),
) -> User:
    """
    Ensures user has sufficient reporting or store-reading privileges.
    Permits roles with '*', 'reports:read', 'stores:read', or 'analytics:read'.
    """
    perms = user.role.permissions if (user.role and user.role.permissions) else []
    if (
        "*" in perms
        or "reports:read" in perms
        or "stores:read" in perms
        or "analytics:read" in perms
    ):
        return user
    raise ForbiddenException("Missing permission: reports:read or stores:read")


@router.get(
    "/revenue-comparison",
    response_model=StoreRevenueComparisonResponse,
    summary="Multi-Store Revenue Comparison",
    description="Cross-store comparative revenue analytics, total sales, average order value, and order count across stores.",
)
def get_revenue_comparison(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    store_ids: Optional[List[int]] = Query(default=None),
    user: User = Depends(require_multi_store_read_permission),
    db: Session = Depends(get_db),
):
    return MultiStoreAnalyticsService(db).revenue_comparison(
        user=user,
        start_date=start_date,
        end_date=end_date,
        store_ids=store_ids,
    )


@router.get(
    "/profit-comparison",
    response_model=StoreProfitComparisonResponse,
    summary="Multi-Store Profit Comparison",
    description="Cross-store profitability comparison analyzing total revenue, cost of goods, gross profit, and profit margins.",
)
def get_profit_comparison(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    store_ids: Optional[List[int]] = Query(default=None),
    user: User = Depends(require_multi_store_read_permission),
    db: Session = Depends(get_db),
):
    return MultiStoreAnalyticsService(db).profit_comparison(
        user=user,
        start_date=start_date,
        end_date=end_date,
        store_ids=store_ids,
    )


@router.get(
    "/inventory-comparison",
    response_model=StoreInventoryComparisonResponse,
    summary="Multi-Store Inventory Comparison",
    description="Cross-store inventory analytics comparing total stock units, inventory valuation, and out-of-stock items across stores.",
)
def get_inventory_comparison(
    store_ids: Optional[List[int]] = Query(default=None),
    user: User = Depends(require_multi_store_read_permission),
    db: Session = Depends(get_db),
):
    return MultiStoreAnalyticsService(db).inventory_comparison(
        user=user,
        store_ids=store_ids,
    )


@router.get(
    "/customer-comparison",
    response_model=StoreCustomerComparisonResponse,
    summary="Multi-Store Customer Comparison",
    description="Cross-store customer metrics comparing unique customers, new customer acquisitions, repeat rates, and revenue per customer.",
)
def get_customer_comparison(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    store_ids: Optional[List[int]] = Query(default=None),
    user: User = Depends(require_multi_store_read_permission),
    db: Session = Depends(get_db),
):
    return MultiStoreAnalyticsService(db).customer_comparison(
        user=user,
        start_date=start_date,
        end_date=end_date,
        store_ids=store_ids,
    )
