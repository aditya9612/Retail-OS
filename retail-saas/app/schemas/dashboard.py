
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class StoreSummaryItem(BaseModel):
    store_id: int
    store_name: str
    today_sales: float
    monthly_sales: float
    orders_count: int
    low_stock_count: int
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class RecentTransaction(BaseModel):
    order_id: int
    order_number: str
    amount: float
    order_status: str
    payment_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DashboardResponse(BaseModel):
    mode: str = "all_stores"
    store_id: Optional[int] = None
    store_name: Optional[str] = None
    today_sales: float
    monthly_sales: float
    total_customers: int
    total_revenue: float
    low_stock_products: int
    stores_summary: Optional[List[StoreSummaryItem]] = None

    total_sales: float = 0.0
    sales_target: float = 0.0
    sales_achievement_percentage: float = 0.0

    total_cost: float = 0.0
    cost_target: float = 0.0
    cost_achievement_percentage: float = 0.0

    products_sold: int = 0
    products_target: float = 0.0
    products_achievement_percentage: float = 0.0

    gross_profit: float = 0.0
    gross_margin_percentage: float = 0.0

    recent_transactions: List[RecentTransaction] = []

    model_config = ConfigDict(from_attributes=True)


class MonthlySales(BaseModel):
    month: str
    sales: float
    target: float = 0.0


class DashboardOverviewResponse(BaseModel):
    period: str
    overview: List[MonthlySales]

    model_config = ConfigDict(from_attributes=True)


class MonthlyRevCost(BaseModel):
    month: str
    revenue: float = 0.0
    cost: float = 0.0
    gross_profit: float = 0.0


class RevenueVsCostResponse(BaseModel):
    period: str
    revenue: float
    cost: float
    gross_profit: float = 0.0
    gross_margin_percentage: float = 0.0
    monthly: Optional[List[MonthlyRevCost]] = None

    model_config = ConfigDict(from_attributes=True)


class TopProduct(BaseModel):
    product_name: str
    quantity_sold: int
    revenue: float


class TopProductsResponse(BaseModel):
    top_products: List[TopProduct]


class RecentTransactionsResponse(BaseModel):
    transactions: List[RecentTransaction]

    model_config = ConfigDict(from_attributes=True)