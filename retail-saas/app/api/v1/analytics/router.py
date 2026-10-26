from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import is_tenant_wide_authorized, require_permission
from app.models.user import User
from app.schemas.analytics import CustomerAnalyticsResponse, ProductPerformanceItem
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
    description="Returns product performance metrics including quantity sold and revenue.",
)
def product_performance(
    limit: int = Query(default=10, ge=1, le=100, description="Max number of products to return"),
    store_id: Optional[int] = Query(default=None, gt=0, description="Filter product performance by store ID"),
    period: Optional[str] = Query(
        default=None,
        description="Optional period filter: this_month, last_month, or this_year",
        pattern="^(this_month|last_month|this_year)$",
    ),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id, db)
    return ReportService(db).product_performance(
        tenant_id=user.tenant_id,
        limit=limit,
        store_id=effective_store_id,
        period=period,
    )


@router.get(
    "/customers",
    response_model=CustomerAnalyticsResponse,
    summary="Get Customer Analytics & Retention Metrics",
    description="Returns customer retention, repeat customer rate, and order value metrics.",
)
def customer_analytics(
    store_id: Optional[int] = Query(default=None, gt=0, description="Filter customer analytics by store ID"),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id, db)
    return ReportService(db).customer_analytics(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
    )
