from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.ai import (
    AIChatQueryRequest,
    AIChatQueryResponse,
    BestSellerItem,
    CustomerChurnRiskItem,
    CustomerPatternResponse,
    DemandForecastResponse,
    FrequentlyBoughtTogetherItem,
    OfferRecommendationItem,
    ReorderPredictionItem,
    SlowMovingStockItem,
)
from app.services.ai_service import AIService

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get(
    "/reorder-prediction",
    response_model=List[ReorderPredictionItem],
    summary="Reorder Prediction",
    description="Predicts items running low on stock using sales run rate, min/max levels, and pending POs.",
)
def reorder_prediction(
    store_id: Optional[int] = Query(None, gt=0, description="Filter predictions by store ID"),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).reorder_prediction(user.tenant_id, store_id)


@router.get(
    "/demand-forecast/{product_id}",
    response_model=DemandForecastResponse,
    summary="Demand Forecast",
    description="Forecasts future product demand over next 7 and 30 days with trend detection.",
)
def demand_forecast(
    product_id: int,
    days: int = Query(default=30, gt=0, le=365, description="Historical analysis window in days"),
    store_id: Optional[int] = Query(None, gt=0, description="Filter demand forecast by store ID"),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).demand_forecast(user.tenant_id, product_id, days=days, store_id=store_id)


@router.get(
    "/best-sellers",
    response_model=List[BestSellerItem],
    summary="Best Sellers",
    description="Lists top selling products by quantity or revenue with period filtering.",
)
def best_sellers(
    limit: int = Query(default=10, gt=0, le=100),
    period: Literal["today", "this_week", "this_month", "last_30_days", "all_time"] = Query(
        default="all_time", description="Historical period window"
    ),
    sort_by: Literal["quantity", "revenue"] = Query(default="quantity", description="Sort criteria"),
    store_id: Optional[int] = Query(None, gt=0, description="Filter best sellers by store ID"),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).best_selling_products(
        user.tenant_id, limit, store_id=store_id, period=period, sort_by=sort_by
    )


@router.get(
    "/customer-patterns/{customer_id}",
    response_model=CustomerPatternResponse,
    summary="Customer Patterns",
    description="Analyzes customer purchasing frequency, average basket size, preferred day, and favorite category.",
)
def customer_patterns(
    customer_id: int,
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).customer_purchase_patterns(user.tenant_id, customer_id)


@router.get(
    "/offer-recommendations/{customer_id}",
    response_model=List[OfferRecommendationItem],
    summary="Offer Recommendations",
    description="Generates actionable, personalized coupon and promotion recommendations for the customer.",
)
def offer_recommendations(
    customer_id: int,
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).smart_offer_recommendations(user.tenant_id, customer_id)


@router.get(
    "/frequently-bought-together/{product_id}",
    response_model=List[FrequentlyBoughtTogetherItem],
    summary="Frequently Bought Together (Market Basket Analysis)",
    description="Identifies items frequently co-purchased with the specified product for cross-selling recommendations.",
)
def frequently_bought_together(
    product_id: int,
    limit: int = Query(default=5, gt=0, le=20),
    store_id: Optional[int] = Query(None, gt=0, description="Filter by store ID"),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).frequently_bought_together(user.tenant_id, product_id, limit=limit, store_id=store_id)


@router.get(
    "/customer-churn-risk",
    response_model=List[CustomerChurnRiskItem],
    summary="Customer Churn Risk Analysis",
    description="Identifies lapsed customers at risk of churn based on days of inactivity since their last purchase.",
)
def customer_churn_risk(
    inactive_days: int = Query(default=45, ge=7, le=365, description="Days of inactivity threshold"),
    limit: int = Query(default=50, gt=0, le=200),
    store_id: Optional[int] = Query(None, gt=0, description="Filter by store ID"),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).customer_churn_risk(
        user.tenant_id, inactive_days=inactive_days, limit=limit, store_id=store_id
    )


@router.get(
    "/slow-moving-stock",
    response_model=List[SlowMovingStockItem],
    summary="Slow Moving & Dead Stock Detection",
    description="Detects dead stock and slow-moving items with high holding capital and recommends clearance discounts.",
)
def slow_moving_stock(
    days: int = Query(default=60, ge=14, le=365, description="Historical period window in days"),
    threshold_sales: int = Query(default=2, ge=0, le=50, description="Max units sold to qualify as slow moving"),
    store_id: Optional[int] = Query(None, gt=0, description="Filter by store ID"),
    limit: int = Query(default=50, gt=0, le=200),
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).slow_moving_stock(
        user.tenant_id, days=days, threshold_sales=threshold_sales, store_id=store_id, limit=limit
    )


@router.post(
    "/chat-query",
    response_model=AIChatQueryResponse,
    summary="Retail-OS AI Natural Language Assistant",
    description="Answers natural language business questions about sales, revenue, low stock, and customer stats.",
)
def chat_query(
    payload: AIChatQueryRequest,
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).chat_query(user.tenant_id, payload.query, store_id=payload.store_id)
