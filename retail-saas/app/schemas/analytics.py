from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ProductPerformanceItem(BaseModel):
    product_id: int
    product_name: str
    sku: Optional[str] = None
    category_name: Optional[str] = None
    quantity_sold: int
    revenue: float
    cost_price: float = 0.0
    cogs: float = 0.0
    gross_profit: float = 0.0
    margin_percentage: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class CustomerAnalyticsResponse(BaseModel):
    total_customers: int
    active_customers: int = 0
    repeat_customers: int = 0
    one_time_customers: int = 0
    zero_order_customers: int = 0
    repeat_rate_percentage: float = 0.0
    total_orders: int = 0
    total_revenue: float = 0.0
    average_order_value: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class DeadStockItem(BaseModel):
    product_id: int
    product_name: str
    sku: Optional[str] = None
    category_name: Optional[str] = None
    current_stock: int
    cost_price: float
    stock_value: float
    days_inactive: int
    last_sold_date: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DeadStockSummaryResponse(BaseModel):
    threshold_days: int
    total_dead_stock_items: int
    total_tied_capital: float
    items: List[DeadStockItem]

    model_config = ConfigDict(from_attributes=True)


class SalesTrendItem(BaseModel):
    period_label: str
    order_count: int
    total_revenue: float
    total_cogs: float = 0.0
    gross_profit: float = 0.0
    average_order_value: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class SalesTrendsResponse(BaseModel):
    interval: str
    total_revenue: float
    total_orders: int
    overall_aov: float = 0.0
    trends: List[SalesTrendItem]

    model_config = ConfigDict(from_attributes=True)


class CustomerSegmentItem(BaseModel):
    segment: str
    customer_count: int
    percentage_of_total: float
    total_revenue: float
    average_spend: float

    model_config = ConfigDict(from_attributes=True)


class CustomerSegmentsResponse(BaseModel):
    total_customers: int
    segments: List[CustomerSegmentItem]

    model_config = ConfigDict(from_attributes=True)


class ForecastDayItem(BaseModel):
    date: str
    predicted_revenue: float
    predicted_orders: int
    confidence_score: float

    model_config = ConfigDict(from_attributes=True)


class SalesForecastResponse(BaseModel):
    days_ahead: int
    historical_days_analyzed: int
    daily_average_revenue: float
    daily_average_orders: float
    growth_rate_percentage: float
    total_forecasted_revenue: float
    total_forecasted_orders: int
    forecast: List[ForecastDayItem]

    model_config = ConfigDict(from_attributes=True)
