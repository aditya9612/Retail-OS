from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import require_permission
from app.models.user import User

from app.schemas.dashboard import (
    DashboardResponse,
    DashboardOverviewResponse,
    RevenueVsCostResponse,
    TopProductsResponse,
)
from app.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


def _resolve_effective_store_id(user: User, store_id: Optional[int]) -> Optional[int]:
    """
    Resolve the store filter enforcing tenancy & store boundaries:
    - If user is assigned to a specific store (e.g., Cashier / Store Manager with user.store_id):
      - If store_id query param is supplied and does not match user.store_id -> 403 Forbidden.
      - Automatically enforce user.store_id if omitted or matching.
    - If user is tenant-level (Owner / Admin with user.store_id is None):
      - Allowed to view consolidated view (store_id=None) or drill down to any store (store_id=X).
    """
    if user.store_id is not None:
        if store_id is not None and store_id != user.store_id:
            raise ForbiddenException("Store staff are not authorized to access other stores' dashboard data")
        return user.store_id
    return store_id


@router.get(
    "",
    response_model=DashboardResponse,
    summary="Dashboard Summary"
)
def get_dashboard(
    store_id: Optional[int] = Query(default=None, gt=0, description="Optional store ID filter"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard:view")),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return DashboardService(db).get_dashboard(user.tenant_id, store_id=effective_store_id)


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    summary="Dashboard Overview Chart",
)
def dashboard_overview(
    store_id: Optional[int] = Query(default=None, gt=0, description="Optional store ID filter"),
    user: User = Depends(require_permission("dashboard:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return DashboardService(db).get_dashboard_overview(user.tenant_id, store_id=effective_store_id)


@router.get(
    "/revenue-vs-cost",
    response_model=RevenueVsCostResponse,
    summary="Revenue vs Cost",
)
def revenue_vs_cost(
    store_id: Optional[int] = Query(default=None, gt=0, description="Optional store ID filter"),
    user: User = Depends(require_permission("dashboard:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return DashboardService(db).get_revenue_vs_cost(user.tenant_id, store_id=effective_store_id)


@router.get(
    "/top-products",
    response_model=TopProductsResponse,
    summary="Top Products",
)
def get_top_products(
    store_id: Optional[int] = Query(default=None, gt=0, description="Optional store ID filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard:view")),
):
    effective_store_id = _resolve_effective_store_id(current_user, store_id)
    return DashboardService(db).get_top_products(current_user.tenant_id, store_id=effective_store_id)