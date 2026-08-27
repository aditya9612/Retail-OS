from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.gst_rate import GstRateCreate, GstRateResponse, GstRateUpdate
from app.services.gst_service import GstService

router = APIRouter(prefix="/gst-rates", tags=["gst-rates"])


@router.get("", response_model=list[GstRateResponse])
def list_gst_rates(
    supply_type: Optional[Literal["intra_state", "inter_state"]] = Query(
        default=None,
        description="intra_state returns CGST+SGST only; inter_state returns IGST only",
    ),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return GstService(db).list_rate_views(user.tenant_id, supply_type=supply_type)


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
