from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class ReorderPredictionItem(BaseModel):
    product_id: int
    product_name: str
    sku: Optional[str] = None
    store_id: int
    current_stock: int
    min_stock_level: int
    reorder_level: int
    daily_run_rate: float
    estimated_runout_days: Optional[float] = None
    pending_order_qty: int = 0
    recommended_order: int
    urgency: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]

    model_config = ConfigDict(from_attributes=True)


class DemandForecastResponse(BaseModel):
    product_id: int
    product_name: str
    sku: Optional[str] = None
    period_days: int
    total_sold: int
    daily_average: float
    forecast_next_7_days: float
    forecast_next_30_days: float
    trend: Literal["increasing", "stable", "decreasing"]

    model_config = ConfigDict(from_attributes=True)


class BestSellerItem(BaseModel):
    product_id: int
    product_name: str
    sku: Optional[str] = None
    quantity_sold: int
    total_revenue: float
    current_stock: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CustomerPatternResponse(BaseModel):
    customer_id: int
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    order_count: int
    total_spent: float
    average_order_value: float
    preferred_day: Optional[str] = None
    preferred_category: Optional[str] = None
    last_purchase_date: Optional[datetime] = None
    days_since_last_purchase: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class OfferRecommendationItem(BaseModel):
    type: Literal["loyalty", "upsell", "welcome", "winback", "category_affinity"]
    message: str
    discount_type: Literal["percentage", "fixed"]
    discount_value: float
    coupon_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FrequentlyBoughtTogetherItem(BaseModel):
    product_id: int
    product_name: str
    sku: Optional[str] = None
    co_occurrence_count: int
    correlation_percentage: float

    model_config = ConfigDict(from_attributes=True)


class CustomerChurnRiskItem(BaseModel):
    customer_id: int
    customer_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    last_purchase_date: Optional[datetime] = None
    days_inactive: int
    total_orders: int
    total_spent: float
    risk_level: Literal["CRITICAL", "HIGH", "MEDIUM"]
    recommended_action: str

    model_config = ConfigDict(from_attributes=True)


class SlowMovingStockItem(BaseModel):
    product_id: int
    product_name: str
    sku: Optional[str] = None
    store_id: int
    current_stock: int
    stock_value: float
    quantity_sold_in_period: int
    days_since_last_sold: Optional[int] = None
    recommended_discount_percent: int

    model_config = ConfigDict(from_attributes=True)


class AIChatQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500, description="Natural language retail question")
    store_id: Optional[int] = Field(None, gt=0, description="Optional store context")


class AIChatQueryResponse(BaseModel):
    query: str
    intent: str
    answer: str
    data: Optional[Dict[str, Any]] = None
    suggested_actions: List[str] = []

    model_config = ConfigDict(from_attributes=True)

