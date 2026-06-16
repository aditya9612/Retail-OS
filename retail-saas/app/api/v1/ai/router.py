from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.services.ai_service import AIService

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/reorder-prediction")
def reorder_prediction(
    store_id: int | None = None,
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).reorder_prediction(user.tenant_id, store_id)


@router.get("/demand-forecast/{product_id}")
def demand_forecast(
    product_id: int,
    days: int = 30,
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).demand_forecast(user.tenant_id, product_id, days)


@router.get("/best-sellers")
def best_sellers(
    limit: int = 10,
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).best_selling_products(user.tenant_id, limit)


@router.get("/customer-patterns/{customer_id}")
def customer_patterns(
    customer_id: int,
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).customer_purchase_patterns(user.tenant_id, customer_id)


@router.get("/offer-recommendations/{customer_id}")
def offer_recommendations(
    customer_id: int,
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return AIService(db).smart_offer_recommendations(user.tenant_id, customer_id)
