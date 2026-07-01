from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.billing import RefundCreate, RefundResponse
from app.services.billing_service import BillingService

router = APIRouter(prefix="/refunds", tags=["refunds"])


@router.post("", response_model=RefundResponse, status_code=201)
def create_refund(
    payload: RefundCreate,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    return BillingService(db).create_refund(
        user.tenant_id,
        payload.invoice_id,
        payload.refund_amount,
        payload.refund_method,
        payload.reason,
    )


@router.get("", response_model=list[RefundResponse])
def list_refunds(
    invoice_id: Optional[int] = Query(default=None),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).list_refunds(user.tenant_id, invoice_id)


@router.get("/{refund_id}", response_model=RefundResponse)
def get_refund(
    refund_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return BillingService(db).get_refund(user.tenant_id, refund_id)


@router.post("/{refund_id}/approve", response_model=RefundResponse)
def approve_refund(
    refund_id: int,
    user: User = Depends(require_permission("billing:refund")),
    db: Session = Depends(get_db),
):
    return BillingService(db).approve_refund(user.tenant_id, refund_id, user.id)


@router.post("/{refund_id}/reject", response_model=RefundResponse)
def reject_refund(
    refund_id: int,
    user: User = Depends(require_permission("billing:refund")),
    db: Session = Depends(get_db),
):
    return BillingService(db).reject_refund(user.tenant_id, refund_id)
