from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import is_tenant_wide_authorized, require_permission
from app.models.user import User
from app.schemas.analytics import (
    CustomerAnalyticsResponse,
    CustomerSegmentsResponse,
    DeadStockSummaryResponse,
    ProductPerformanceItem,
    SalesForecastResponse,
    SalesTrendsResponse,
)
from app.services.report_service import ReportService

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _resolve_effective_store_id(user: User, store_id: Optional[int], db: Session) -> Optional[int]:
    if user.store_id is not None:
        if store_id is not None and store_id != user.store_id:
            if not is_tenant_wide_authorized(user, db):
                raise ForbiddenException("Store staff are not authorized to access other stores' analytics data")
        return user.store_id
    return store_id


@router.get(
    "/products",
    response_model=List[ProductPerformanceItem],
    summary="Get Top Product Performance",
    description="Returns product performance metrics including quantity sold, revenue, COGS, gross profit, and profit margin.",
)
def product_performance(
    limit: int = Query(default=10, ge=1, le=100, description="Max number of products to return"),
    store_id: Optional[int] = Query(default=None, gt=0, description="Filter product performance by store ID"),
    category_id: Optional[int] = Query(default=None, gt=0, description="Filter product performance by category ID"),
    period: Optional[str] = Query(
        default=None,
        description="Optional period filter: today, yesterday, this_week, last_week, this_month, last_month, this_year, last_year",
        pattern="^(today|yesterday|this_week|last_week|this_month|last_month|this_year|last_year)$",
    ),
    date_from: Optional[date] = Query(default=None, description="Start date (YYYY-MM-DD) for custom range"),
    date_to: Optional[date] = Query(default=None, description="End date (YYYY-MM-DD) for custom range"),
    sort_by: str = Query(default="revenue", pattern="^(revenue|quantity|profit|margin)$", description="Field to sort by"),
    order: str = Query(default="desc", pattern="^(asc|desc)$", description="Sort direction"),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id, db)
    return ReportService(db).product_performance(
        tenant_id=user.tenant_id,
        limit=limit,
        store_id=effective_store_id,
        period=period,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        order=order,
        category_id=category_id,
    )


@router.get(
    "/customers",
    response_model=CustomerAnalyticsResponse,
    summary="Get Customer Analytics & Retention Metrics",
    description="Returns customer retention, repeat customer rate, active vs zero-order counts, and order value metrics.",
)
def customer_analytics(
    store_id: Optional[int] = Query(default=None, gt=0, description="Filter customer analytics by store ID"),
    period: Optional[str] = Query(
        default=None,
        description="Optional period filter: today, yesterday, this_week, last_week, this_month, last_month, this_year, last_year",
        pattern="^(today|yesterday|this_week|last_week|this_month|last_month|this_year|last_year)$",
    ),
    date_from: Optional[date] = Query(default=None, description="Start date (YYYY-MM-DD) for custom range"),
    date_to: Optional[date] = Query(default=None, description="End date (YYYY-MM-DD) for custom range"),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id, db)
    return ReportService(db).customer_analytics(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        period=period,
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/dead-stock",
    response_model=DeadStockSummaryResponse,
    summary="Get Slow-Moving & Dead Stock Analytics",
    description="Identifies unsold inventory and tied-up working capital for stock inactive beyond the given threshold.",
)
def dead_stock(
    days: int = Query(default=60, ge=7, le=365, description="Inactivity threshold in days"),
    store_id: Optional[int] = Query(default=None, gt=0, description="Filter dead stock by store ID"),
    category_id: Optional[int] = Query(default=None, gt=0, description="Filter dead stock by category ID"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum items to return"),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id, db)
    return ReportService(db).dead_stock(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        category_id=category_id,
        days=days,
        limit=limit,
    )


@router.get(
    "/sales-trends",
    response_model=SalesTrendsResponse,
    summary="Get Sales & Revenue Trends",
    description="Returns time-series revenue, COGS, gross margin, and order count trends aggregated by hourly, daily, weekly, or monthly intervals.",
)
def sales_trends(
    interval: str = Query(default="daily", pattern="^(hourly|daily|weekly|monthly)$", description="Aggregation interval"),
    period: Optional[str] = Query(
        default="this_month",
        description="Period preset: today, yesterday, this_week, last_week, this_month, last_month, this_year, last_year",
        pattern="^(today|yesterday|this_week|last_week|this_month|last_month|this_year|last_year)$",
    ),
    date_from: Optional[date] = Query(default=None, description="Start date (YYYY-MM-DD) for custom range"),
    date_to: Optional[date] = Query(default=None, description="End date (YYYY-MM-DD) for custom range"),
    store_id: Optional[int] = Query(default=None, gt=0, description="Filter sales trends by store ID"),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id, db)
    return ReportService(db).sales_trends(
        tenant_id=user.tenant_id,
        interval=interval,
        period=period,
        date_from=date_from,
        date_to=date_to,
        store_id=effective_store_id,
    )


@router.get(
    "/customer-segments",
    response_model=CustomerSegmentsResponse,
    summary="Get RFM Customer Segmentation",
    description="Groups customers into standard RFM behavior segments: Champions, Loyal, Potential Loyalists, At Risk, Lost, and Prospects.",
)
def customer_segments(
    store_id: Optional[int] = Query(default=None, gt=0, description="Filter segments by store ID"),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id, db)
    return ReportService(db).customer_segments(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
    )


@router.get(
    "/forecast",
    response_model=SalesForecastResponse,
    summary="Get Sales Demand & Revenue Forecast",
    description="Projects future revenue and order volume based on historical sales velocity and day-of-week seasonality.",
)
def sales_forecast(
    days_ahead: int = Query(default=7, ge=1, le=30, description="Forecast horizon (1-30 days)"),
    store_id: Optional[int] = Query(default=None, gt=0, description="Filter forecast by store ID"),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id, db)
    return ReportService(db).demand_forecast(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        days_ahead=days_ahead,
    )
