
from typing import Optional

from sqlalchemy.orm import Session

from app.repositories.dashboard_repo import DashboardRepository


class DashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DashboardRepository(db)

    def get_dashboard(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ):
        return self.repo.get_dashboard(
            tenant_id=tenant_id,
            store_id=store_id,
        )

    def get_dashboard_overview(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_year",
    ):
        return self.repo.get_dashboard_overview(
            tenant_id=tenant_id,
            store_id=store_id,
            period=period,
        )

    def get_revenue_vs_cost(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_month",
    ):
        return self.repo.get_revenue_vs_cost(
            tenant_id=tenant_id,
            store_id=store_id,
            period=period,
        )

    def get_top_products(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        limit: int = 10,
    ):
        return self.repo.get_top_products(
            tenant_id=tenant_id,
            store_id=store_id,
            limit=limit,
        )
