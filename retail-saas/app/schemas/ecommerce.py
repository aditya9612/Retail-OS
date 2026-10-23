from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class EcommerceKPIItem(BaseModel):
    value: float = Field(default=0.0, description="Metric primary value")
    change_percentage: float = Field(default=0.0, description="Growth percentage compared to previous period")
    comparison_text: Optional[str] = Field(default=None, description="Comparison context e.g. 'vs last year'")
    subtext: Optional[str] = Field(default=None, description="Additional context e.g. 'in product catalog'")
    today_count: Optional[int] = Field(default=None, description="Count recorded today")
    new_this_month: Optional[int] = Field(default=None, description="New entries this month")


class EcommerceKPIsResponse(BaseModel):
    online_revenue: EcommerceKPIItem
    total_online_orders: EcommerceKPIItem
    active_products: EcommerceKPIItem
    conversion_rate: EcommerceKPIItem
    cart_abandonment: EcommerceKPIItem
    avg_order_value: EcommerceKPIItem
    online_customers: EcommerceKPIItem
    pending_deliveries: EcommerceKPIItem


class MonthlyRevenuePoint(BaseModel):
    month: str = Field(description="Month abbreviation e.g. 'Jan'")
    online: float = Field(default=0.0, description="Online channel revenue for this month")
    offline: float = Field(default=0.0, description="Offline POS channel revenue for this month")


class RevenueComparisonSummary(BaseModel):
    total_online: float = Field(default=0.0, description="Total online revenue in period")
    total_offline: float = Field(default=0.0, description="Total offline POS revenue in period")


class RevenueComparisonResponse(BaseModel):
    summary: RevenueComparisonSummary
    period: str = Field(default="this_year", description="Period covered")
    monthly_data: list[MonthlyRevenuePoint] = Field(default_factory=list, description="Monthly timeseries data")


class OrderStatusItem(BaseModel):
    status: str = Field(description="Normalized status key e.g. 'processing'")
    label: str = Field(description="Display label e.g. 'Processing'")
    count: int = Field(default=0, description="Order count in this status")
    percentage: float = Field(default=0.0, description="Percentage of total orders")
    color: str = Field(default="#6b7280", description="Hex color code for chart")


class OrderStatusBreakdownResponse(BaseModel):
    total_orders: int = Field(default=0, description="Total orders evaluated")
    breakdown: list[OrderStatusItem] = Field(default_factory=list, description="Order status breakdown slices")


class RecentOnlineOrderItem(BaseModel):
    order_id: str = Field(description="Order number or identifier")
    customer_name: str = Field(description="Customer full name")
    amount: float = Field(description="Total order amount")
    items_count: int = Field(default=1, description="Number of items or units")
    payment_mode: str = Field(default="Online", description="Payment method or channel")
    status: str = Field(description="Current order status")
    created_at: str = Field(description="Order creation timestamp")


class RecentOnlineOrdersResponse(BaseModel):
    orders: list[RecentOnlineOrderItem] = Field(default_factory=list)
    total: int = Field(default=0)


class TopSellingProductItem(BaseModel):
    rank: int = Field(description="Rank position")
    product_id: int = Field(description="Product ID")
    product_name: str = Field(description="Product title")
    category: str = Field(default="General", description="Product category name")
    orders_count: int = Field(default=0, description="Units sold or orders containing product")
    revenue: float = Field(default=0.0, description="Total sales value generated")
    progress_percentage: float = Field(default=0.0, description="Visual bar percentage relative to top product")


class TopSellingProductsResponse(BaseModel):
    products: list[TopSellingProductItem] = Field(default_factory=list)
    total: int = Field(default=0)


class EcommerceDashboardResponse(BaseModel):
    kpis: EcommerceKPIsResponse
    revenue_comparison: RevenueComparisonResponse
    order_status_breakdown: OrderStatusBreakdownResponse
    recent_orders: list[RecentOnlineOrderItem] = Field(default_factory=list)
    top_products: list[TopSellingProductItem] = Field(default_factory=list)

