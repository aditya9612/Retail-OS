from sqlalchemy.orm import Session

from app.repositories.dashboard_repo import DashboardRepository


class DashboardService:

    def __init__(self, db: Session):
        self.repo = DashboardRepository(db)

    def get_dashboard(self, tenant_id: int):
        return self.repo.get_dashboard(tenant_id)

    def get_dashboard_overview(self, tenant_id: int):
        return self.repo.get_dashboard_overview(tenant_id)  

    def get_revenue_vs_cost(self, tenant_id: int):
        return self.repo.get_revenue_vs_cost(tenant_id) 

    def get_top_products(self, tenant_id: int):
        return self.repo.get_top_products(tenant_id)     