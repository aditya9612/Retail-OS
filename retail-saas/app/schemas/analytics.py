from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ProductPerformanceItem(BaseModel):
    product_id: int
    product_name: str
    quantity_sold: int
    revenue: float

    model_config = ConfigDict(from_attributes=True)


class CustomerAnalyticsResponse(BaseModel):
    total_customers: int
    repeat_customers: int
    one_time_customers: int = 0
    repeat_rate_percentage: float = 0.0
    total_orders: int = 0
    total_revenue: float = 0.0
    average_order_value: float = 0.0

    model_config = ConfigDict(from_attributes=True)

