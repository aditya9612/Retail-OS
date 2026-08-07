from pydantic import BaseModel
from typing import List


class DashboardResponse(BaseModel):
    today_sales: float
    monthly_sales: float
    total_customers: int
    total_revenue: float
    low_stock_products: int

    class Config:
        from_attributes = True


class MonthlySales(BaseModel):
    month: str
    sales: float


class DashboardOverviewResponse(BaseModel):
    overview: List[MonthlySales]

    class Config:
        from_attributes = True 

class RevenueVsCostResponse(BaseModel):
    revenue: float
    cost: float

    class Config:
        from_attributes = True   

class TopProduct(BaseModel):
    product_name: str
    quantity_sold: int
    revenue: float


class TopProductsResponse(BaseModel):
    top_products: list[TopProduct]        


