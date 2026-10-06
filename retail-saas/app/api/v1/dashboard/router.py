
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import require_permission
from app.models.user import User
from app.schemas.dashboard import (
    DashboardOverviewResponse,
    DashboardResponse,
    RevenueVsCostResponse,
    TopProductsResponse,
)
from app.services.dashboard_service import DashboardService


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _resolve_effective_store_id(
    user: User,
    store_id: Optional[int],
) -> Optional[int]:
    if user.store_id is not None:
        if store_id is not None and store_id != user.store_id:
            raise ForbiddenException(
                "Store staff are not authorized to access other stores' dashboard data"
            )
        return user.store_id

    return store_id


@router.get(
    "",
    response_model=DashboardResponse,
    summary="Get dashboard summary",
)
def dashboard(
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter",
    ),
    user: User = Depends(require_permission("dashboard:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(
        user,
        store_id,
    )

    return DashboardService(db).get_dashboard(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
    )


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    summary="Get dashboard sales overview",
)
def dashboard_overview(
    period: str = Query(
        default="this_year",
        description="Overview period: this_month, last_month, or this_year",
        pattern="^(this_month|last_month|this_year)$",
    ),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter",
    ),
    user: User = Depends(require_permission("dashboard:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(
        user,
        store_id,
    )

    return DashboardService(db).get_dashboard_overview(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        period=period,
    )


@router.get(
    "/revenue-vs-cost",
    response_model=RevenueVsCostResponse,
    summary="Get revenue versus cost",
)
def revenue_vs_cost(
    period: str = Query(
        default="this_month",
        description="Revenue period: this_month, last_month, or this_year",
        pattern="^(this_month|last_month|this_year)$",
    ),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter",
    ),
    user: User = Depends(require_permission("dashboard:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(
        user,
        store_id,
    )

    return DashboardService(db).get_revenue_vs_cost(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        period=period,
    )


@router.get(
    "/top-products",
    response_model=TopProductsResponse,
    summary="Get top selling products",
)
def top_products(
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Number of top products to return",
    ),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter",
    ),
    user: User = Depends(require_permission("dashboard:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(
        user,
        store_id,
    )

    return DashboardService(db).get_top_products(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        limit=limit,
    )
