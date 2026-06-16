from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.services.report_service import ReportService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/products")
def product_performance(
    limit: int = 10,
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).product_performance(user.tenant_id, limit)


@router.get("/customers")
def customer_analytics(
    user: User = Depends(require_permission("analytics:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).customer_analytics(user.tenant_id)
