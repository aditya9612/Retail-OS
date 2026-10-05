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

    model_config = ConfigDict(from_attributes=True)


class MonthlySales(BaseModel):
    month: str
    sales: float


class DashboardOverviewResponse(BaseModel):
    period: str
    overview: List[MonthlySales]

    model_config = ConfigDict(from_attributes=True)


class RevenueVsCostResponse(BaseModel):
    period: str
    revenue: float
    cost: float

    model_config = ConfigDict(from_attributes=True)


class TopProduct(BaseModel):
    product_name: str
    quantity_sold: int
    revenue: float


class TopProductsResponse(BaseModel):
    top_products: list[TopProduct]
