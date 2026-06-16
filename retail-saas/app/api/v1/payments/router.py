from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.order import PaymentCreate, PaymentResponse
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("", response_model=list[PaymentResponse])
def list_payments(
    order_id: int | None = None,
    user: User = Depends(require_permission("payments:read")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).list_payments(user.tenant_id, order_id)


@router.post("", response_model=PaymentResponse, status_code=201)
def record_payment(
    data: PaymentCreate,
    user: User = Depends(require_permission("payments:write")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).record_payment(user.tenant_id, data)


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: int,
    user: User = Depends(require_permission("payments:read")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).get_payment(user.tenant_id, payment_id)


@router.post("/{payment_id}/refund", response_model=PaymentResponse)
def refund_payment(
    payment_id: int,
    user: User = Depends(require_permission("payments:write")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).refund_payment(user.tenant_id, payment_id)


@router.get("/qr/{order_id}")
def get_qr_payload(
    order_id: int,
    upi_id: str = "merchant@upi",
    user: User = Depends(require_permission("payments:read")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).generate_qr_payload(user.tenant_id, order_id, upi_id)


@router.post("/webhook")
async def payment_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    return PaymentService(db).webhook_handler(payload)
