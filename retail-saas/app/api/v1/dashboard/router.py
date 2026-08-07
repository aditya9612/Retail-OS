from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User

from app.schemas.dashboard import DashboardResponse, DashboardOverviewResponse,RevenueVsCostResponse,TopProductsResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


@router.get(
    "",
    response_model=DashboardResponse,
    summary="Dashboard Summary"
)
def get_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard:view")),
):
    return DashboardService(db).get_dashboard(user.tenant_id)

@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    summary="Dashboard Overview Chart",
)
def dashboard_overview(
    user: User = Depends(require_permission("dashboard:read")),
    db: Session = Depends(get_db),
):
    return DashboardService(db).get_dashboard_overview(user.tenant_id)  

@router.get(
    "/revenue-vs-cost",
    response_model=RevenueVsCostResponse,
    summary="Revenue vs Cost",
)
def revenue_vs_cost(
    user: User = Depends(require_permission("dashboard:read")),
    db: Session = Depends(get_db),
):
    return DashboardService(db).get_revenue_vs_cost(user.tenant_id)   


@router.get(
    "/top-products",
    response_model=TopProductsResponse,
    summary="Top Products",
)
def get_top_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard:view")),
):
    return DashboardService(db).get_top_products(current_user.tenant_id)