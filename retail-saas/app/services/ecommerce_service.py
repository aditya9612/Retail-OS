from typing import Optional
from sqlalchemy.orm import Session

from app.repositories.ecommerce_repo import EcommerceRepository
from app.schemas.ecommerce import (
    EcommerceDashboardResponse,
    EcommerceKPIsResponse,
    OrderStatusBreakdownResponse,
    RecentOnlineOrdersResponse,
    RevenueComparisonResponse,
    TopSellingProductsResponse,
)


class EcommerceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = EcommerceRepository(db)

    def get_full_dashboard(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_year",
    ) -> EcommerceDashboardResponse:
        return self.repo.get_full_dashboard(
            tenant_id=tenant_id,
            store_id=store_id,
            period=period,
        )

    def get_kpis(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_year",
    ) -> EcommerceKPIsResponse:
        return self.repo.get_kpis(
            tenant_id=tenant_id,
            store_id=store_id,
            period=period,
        )

    def get_revenue_comparison(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_year",
    ) -> RevenueComparisonResponse:
        return self.repo.get_revenue_comparison(
            tenant_id=tenant_id,
            store_id=store_id,
            period=period,
        )

    def get_order_status_breakdown(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_year",
    ) -> OrderStatusBreakdownResponse:
        return self.repo.get_order_status_breakdown(
            tenant_id=tenant_id,
            store_id=store_id,
            period=period,
        )

    def get_recent_online_orders(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        limit: int = 10,
    ) -> RecentOnlineOrdersResponse:
        return self.repo.get_recent_online_orders(
            tenant_id=tenant_id,
            store_id=store_id,
            limit=limit,
        )

    def get_top_selling_products(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        limit: int = 10,
    ) -> TopSellingProductsResponse:
        return self.repo.get_top_selling_products(
            tenant_id=tenant_id,
            store_id=store_id,
            limit=limit,
        )

