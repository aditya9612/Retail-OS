from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.gst_rate import GstRateCreate, GstRateResponse, GstRateUpdate
from app.services.gst_service import GstService

router = APIRouter(prefix="/gst-rates", tags=["gst-rates"])


@router.get("", response_model=list[GstRateResponse])
def list_gst_rates(
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return GstService(db).list_rates(user.tenant_id)


@router.post("", response_model=GstRateResponse, status_code=201)
def create_gst_rate(
    payload: GstRateCreate,
    user: User = Depends(require_permission("billing:gst_config")),
    db: Session = Depends(get_db),
):
    return GstService(db).create_rate(user.tenant_id, payload)


@router.put("/{rate_id}", response_model=GstRateResponse)
def update_gst_rate(
    rate_id: int,
    payload: GstRateUpdate,
    user: User = Depends(require_permission("billing:gst_config")),
    db: Session = Depends(get_db),
):
    return GstService(db).update_rate(user.tenant_id, rate_id, payload)
