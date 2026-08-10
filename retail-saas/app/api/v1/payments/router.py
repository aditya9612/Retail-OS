from fastapi import APIRouter, Depends, Request ,Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.order import PaymentCreate, PaymentResponse
from app.schemas.payment import (
    PaymentVerify,
    PaymentGatewayCreate,
    PaymentGatewayUpdate,
    PaymentGatewayResponse,
    PaymentSplitCreate,
    PaymentSplitResponse,
    SettlementCreate,
    SettlementResponse,
    PaymentWebhookLogCreate,
    PaymentWebhookLogResponse,
)
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

@router.get("/history", response_model=list[PaymentResponse])
def payment_history(
    status: Optional[str] = Query(None),
    payment_method: Optional[str] = Query(None),
    user: User = Depends(require_permission("payments:read")),
    db: Session = Depends(get_db),
):
    service = PaymentService(db)

    return service.payment_history(
        tenant_id=user.tenant_id,
        status=status,
        payment_method=payment_method,
    )    

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

@router.post(
    "/webhooks",
    response_model=PaymentWebhookLogResponse,
)
def create_webhook_log(
    data: PaymentWebhookLogCreate,
    user: User = Depends(require_permission("payments:write")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).create_webhook_log(
        user.tenant_id,
        data,
    )

@router.get(
    "/webhooks",
    response_model=list[PaymentWebhookLogResponse],
)
def list_webhook_logs(
    user: User = Depends(require_permission("payments:read")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).list_webhook_logs()

@router.get(
    "/webhooks/{webhook_id}",
    response_model=PaymentWebhookLogResponse,
)
def get_webhook_log(
    webhook_id: int,
    user: User = Depends(require_permission("payments:read")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).get_webhook_log(webhook_id)

@router.post(
    "/payment-gateways",
    response_model=PaymentGatewayResponse,
    status_code=201,
)
def create_payment_gateway(
    data: PaymentGatewayCreate,
    user: User = Depends(require_permission("payments:write")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).create_payment_gateway(
        user.tenant_id,
        data,
    )

@router.get(
    "/payment-gateways",
    response_model=list[PaymentGatewayResponse],
)
def list_payment_gateways(
    user: User = Depends(require_permission("payments:read")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).list_payment_gateways(
        user.tenant_id,
    )

@router.get(
    "/payment-gateways/{gateway_id}",
    response_model=PaymentGatewayResponse,
)
def get_payment_gateway(
    gateway_id: int,
    user: User = Depends(require_permission("payments:read")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).get_payment_gateway(
        user.tenant_id,
        gateway_id,
    )

@router.put(
    "/payment-gateways/{gateway_id}",
    response_model=PaymentGatewayResponse,
)
def update_payment_gateway(
    gateway_id: int,
    data: PaymentGatewayUpdate,
    user: User = Depends(require_permission("payments:write")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).update_payment_gateway(
        user.tenant_id,
        gateway_id,
        data,
    )

@router.delete("/payment-gateways/{gateway_id}")
def delete_payment_gateway(
    gateway_id: int,
    user: User = Depends(require_permission("payments:write")),
    db: Session = Depends(get_db),
):
    PaymentService(db).delete_payment_gateway(
        user.tenant_id,
        gateway_id,
    )

    return {
        "message": "Payment Gateway deleted successfully"
    }

@router.post(
    "/payment-splits",
    response_model=PaymentSplitResponse,
)
def create_payment_split(
    data: PaymentSplitCreate,
    user: User = Depends(require_permission("payments:write")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).create_payment_split(
        user.tenant_id,
        data,
    )


@router.get(
    "/payment-splits",
    response_model=list[PaymentSplitResponse],
)
def list_payment_splits(
    user: User = Depends(require_permission("payments:read")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).list_payment_splits()


@router.get(
    "/payment-splits/{split_id}",
    response_model=PaymentSplitResponse,
)
def get_payment_split(
    split_id: int,
    user: User = Depends(require_permission("payments:read")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).get_payment_split(split_id)

@router.post(
    "/settlements",
    response_model=SettlementResponse,
    status_code=201,
)
def create_settlement(
    data: SettlementCreate,
    user: User = Depends(require_permission("payments:write")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).create_settlement(
        user.tenant_id,
        data,
    )

@router.get(
    "/settlements",
    response_model=list[SettlementResponse],
)
def list_settlements(
    user: User = Depends(require_permission("payments:read")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).list_settlements()

@router.get(
    "/settlements/{settlement_id}",
    response_model=SettlementResponse,
)
def get_settlement(
    settlement_id: int,
    user: User = Depends(require_permission("payments:read")),
    db: Session = Depends(get_db),
):
    return PaymentService(db).get_settlement(
        settlement_id
    )

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

@router.post("/{payment_id}/verify")
def verify_payment_api(
    payment_id: int,
    verify_data: PaymentVerify,
    db: Session = Depends(get_db),
):
    service = PaymentService(db)
    return service.verify_payment_service(payment_id, verify_data)        


