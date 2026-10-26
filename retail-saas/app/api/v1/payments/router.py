from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_operational_write
from app.models.user import User
from app.schemas.order import PaymentResponse
from app.schemas.payment import (
    PaymentCreate,
    PaymentGatewayCreate,
    PaymentGatewayResponse,
    PaymentGatewayUpdate,
    PaymentSplitCreate,
    PaymentSplitResponse,
    PaymentStatusValue,
    PaymentVerify,
    SettlementCreate,
    SettlementResponse,
    PaymentWebhookLogCreate,
    PaymentWebhookLogResponse,
    PaymentWebhookRequest,
    PaymentMethodValue,
)
from app.services.payment_service import PaymentService


router = APIRouter(
    prefix="/payments",
    tags=["payments"],
)


def get_payment_service(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PaymentService:
    return PaymentService(db, user.tenant_id)


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_operational_write)])
def create_payment(
    data: PaymentCreate,
    service: PaymentService = Depends(get_payment_service),
):
    return service.record_payment(data)


@router.get("", response_model=list[PaymentResponse])
def list_payments(
    order_id: int | None = Query(default=None, gt=0),
    payment_method: PaymentMethodValue | None = Query(default=None),
    status: PaymentStatusValue | None = Query(default=None),
    store_id: int | None = Query(default=None, gt=0, description="Filter payments by store ID"),
    service: PaymentService = Depends(get_payment_service),
):
    return service.list_payments(
        order_id=order_id,
        status=status,
        method=payment_method,
        store_id=store_id,
    )


@router.get("/history", response_model=list[PaymentResponse])
def payment_history(
    status: PaymentStatusValue | None = Query(default=None),
    payment_method: PaymentMethodValue | None = Query(default=None),
    store_id: int | None = Query(default=None, gt=0, description="Filter payment history by store ID"),
    service: PaymentService = Depends(get_payment_service),
):
    return service.payment_history(
        status=status,
        method=payment_method,
        store_id=store_id,
    )


@router.get(
    "/qr/{order_id}",
    summary="Generate Payment UPI QR Code",
    description=(
        "Generates a dynamic UPI QR code for an order. "
        "Supports delivery modes: 'preview' (renders visual QR code PNG directly inline in Swagger UI / browser), "
        "'download' (triggers file download of QR PNG), or 'json' (returns raw UPI payload metadata)."
    ),
    responses={
        200: {
            "content": {
                "image/png": {
                    "schema": {"type": "string", "format": "binary"},
                    "description": "Visual QR code PNG image for preview or download",
                },
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "integer"},
                            "upi_id": {"type": "string"},
                            "amount": {"type": "number"},
                            "qr_payload": {"type": "string"},
                            "qr_code_base64": {"type": "string"},
                        },
                    },
                    "description": "UPI payload and QR data in JSON format",
                },
            },
            "description": "Dynamic QR code in PNG visual format or JSON format.",
        }
    },
)
def generate_payment_qr(
    order_id: int,
    upi_id: str | None = Query(default=None, description="Payee VPA / UPI ID (defaults to system/store UPI)"),
    amount: float | None = Query(default=None, description="Optional custom amount (auto-detected from created payment or order total)"),
    mode: Literal["preview", "download", "json"] = Query(
        default="preview",
        description="Delivery mode: 'preview' (renders visual QR code PNG inline in Swagger UI / browser), 'download' (downloads PNG file), or 'json' (returns UPI payload JSON)",
    ),
    service: PaymentService = Depends(get_payment_service),
):
    qr_data = service.generate_qr_payload(order_id=order_id, upi_id=upi_id, amount=amount)

    if mode == "json":
        return qr_data

    qr_image_bytes = service.generate_qr_image_bytes(qr_data["qr_payload"])
    filename = f"order_{order_id}_qr.png"

    if mode == "download":
        return Response(
            content=qr_image_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
            },
        )

    # mode == "preview" (default): inline display in Swagger UI and browser
    return Response(
        content=qr_image_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f"inline; filename={filename}",
            "X-Document-Preview-Type": "Visual-PNG-Preview",
        },
    )


@router.post("/webhook")
def process_webhook(
    data: PaymentWebhookRequest,
    service: PaymentService = Depends(get_payment_service),
):
    return service.webhook_handler(data)


@router.post("/webhooks", response_model=PaymentWebhookLogResponse, status_code=status.HTTP_201_CREATED)
def create_webhook_log(
    data: PaymentWebhookLogCreate,
    service: PaymentService = Depends(get_payment_service),
):
    return service.create_webhook_log(data)


@router.get("/webhooks", response_model=list[PaymentWebhookLogResponse])
def list_webhook_logs(
    status: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    transaction_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    service: PaymentService = Depends(get_payment_service),
):
    return service.list_webhook_logs(
        status=status,
        event_type=event_type,
        transaction_id=transaction_id,
        page=page,
        page_size=page_size,
    )


@router.get("/webhooks/{log_id}", response_model=PaymentWebhookLogResponse)
def get_webhook_log(log_id: int, service: PaymentService = Depends(get_payment_service)):
    result = service.get_webhook_log(log_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Webhook log not found")
    return result


@router.post(
    "/payment-gateways",
    response_model=PaymentGatewayResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_payment_gateway(
    data: PaymentGatewayCreate,
    service: PaymentService = Depends(get_payment_service),
):
    return service.create_gateway(data)


@router.get("/payment-gateways", response_model=list[PaymentGatewayResponse])
def list_payment_gateways(service: PaymentService = Depends(get_payment_service)):
    return service.list_gateways()


@router.get("/payment-gateways/{gateway_id}", response_model=PaymentGatewayResponse)
def get_payment_gateway(gateway_id: int, service: PaymentService = Depends(get_payment_service)):
    result = service.get_gateway(gateway_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Payment gateway not found")
    return result


@router.put("/payment-gateways/{gateway_id}", response_model=PaymentGatewayResponse)
def update_payment_gateway(gateway_id: int, data: PaymentGatewayUpdate, service: PaymentService = Depends(get_payment_service)):
    return service.update_gateway(gateway_id, data)


@router.delete("/payment-gateways/{gateway_id}")
def delete_payment_gateway(gateway_id: int, service: PaymentService = Depends(get_payment_service)):
    return service.delete_gateway(gateway_id)


@router.post(
    "/payment-splits",
    response_model=PaymentSplitResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_payment_split(
    data: PaymentSplitCreate,
    service: PaymentService = Depends(get_payment_service),
):
    return service.create_payment_split(data)


@router.get("/payment-splits", response_model=list[PaymentSplitResponse])
def list_payment_splits(transaction_id: int | None = Query(default=None, gt=0), service: PaymentService = Depends(get_payment_service)):
    return service.list_payment_splits(transaction_id=transaction_id)


@router.get("/payment-splits/{split_id}", response_model=PaymentSplitResponse)
def get_payment_split(split_id: int, service: PaymentService = Depends(get_payment_service)):
    result = service.get_payment_split(split_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Payment split not found")
    return result


@router.post(
    "/settlements",
    response_model=SettlementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_settlement(
    data: SettlementCreate,
    service: PaymentService = Depends(get_payment_service),
):
    return service.create_settlement(data)


@router.get(
    "/settlements",
    response_model=list[SettlementResponse],
)
def list_settlements(
    gateway_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    service: PaymentService = Depends(get_payment_service),
):
    return service.list_settlements(
        gateway_id=gateway_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.get("/settlements/{settlement_id}", response_model=SettlementResponse)
def get_settlement(settlement_id: int, service: PaymentService = Depends(get_payment_service)):
    result = service.get_settlement(settlement_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Settlement not found")
    return result


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(payment_id: int, service: PaymentService = Depends(get_payment_service)):
    result = service.get_payment(payment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return result


@router.post("/{payment_id}/verify", response_model=PaymentResponse)
def verify_payment(payment_id: int, data: PaymentVerify, service: PaymentService = Depends(get_payment_service)):
    return service.verify_payment_service(payment_id, data)
