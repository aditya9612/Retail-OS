from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.saas_invoice import (
    SaaSInvoiceListResponse,
    SaaSInvoiceResponse,
)
from app.schemas.saas_subscription import (
    SaaSSubscriptionCancelRequest,
    SaaSSubscriptionResponse,
)
from app.schemas.saas_upi import (
    UPICheckoutPreviewResponse,
    UPIInitiateResponse,
    UPIQRCodeResponse,
    UPISubmitRequest,
    UPITransactionResponse,
)
from app.services.saas_invoice_service import SaaSInvoiceService
from app.services.saas_subscription_service import SaaSSubscriptionService
from app.services.saas_upi_service import SaaSUPIService


router = APIRouter(
    prefix="/saas-billing",
    tags=["SaaS Billing"],
)


@router.get(
    "/history",
    response_model=SaaSInvoiceListResponse,
    summary="Get Tenant Billing History",
)
def get_billing_history(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves paginated SaaS invoice billing history for the authenticated tenant.
    Enforces strict tenant isolation.
    """
    if not current_user.tenant_id:
        raise ForbiddenException("User is not associated with any tenant")

    return SaaSInvoiceService(db).list_billing_history(
        tenant_id=current_user.tenant_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/invoices/{invoice_id}",
    response_model=SaaSInvoiceResponse,
    summary="Get Tenant Invoice Detail",
)
def get_invoice_detail(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves details of a specific SaaS invoice for the authenticated tenant.
    Returns 404 if the invoice does not exist or belongs to another tenant.
    """
    if not current_user.tenant_id:
        raise ForbiddenException("User is not associated with any tenant")

    return SaaSInvoiceService(db).get_invoice(
        tenant_id=current_user.tenant_id,
        invoice_id=invoice_id,
    )


@router.get(
    "/upi/checkout-preview",
    response_model=UPICheckoutPreviewResponse,
    summary="Get SaaS UPI Checkout Preview",
)
def get_checkout_preview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns payable invoice and subscription details for UPI checkout.
    Enforces tenant isolation.
    """
    if not current_user.tenant_id:
        raise ForbiddenException("User is not associated with any tenant")

    return SaaSUPIService(db).get_checkout_preview(
        tenant_id=current_user.tenant_id
    )


@router.post(
    "/upi/initiate",
    response_model=UPIInitiateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate SaaS UPI Checkout",
)
def initiate_checkout(
    invoice_id: int = Query(..., description="Invoice ID to pay"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates or reuses a pending UPI transaction for the given invoice.
    Enforces tenant isolation, idempotency window, and amount integrity.
    """
    if not current_user.tenant_id:
        raise ForbiddenException("User is not associated with any tenant")

    return SaaSUPIService(db).initiate_checkout(
        tenant_id=current_user.tenant_id,
        invoice_id=invoice_id,
    )


@router.get(
    "/upi/qr-code",
    response_model=UPIQRCodeResponse,
    summary="Get UPI QR Code for Transaction",
)
def get_qr_code(
    reference: str = Query(..., description="UPI transaction reference"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns UPI deep-link payload and base64 QR PNG image.
    Enforces tenant isolation.
    """
    if not current_user.tenant_id:
        raise ForbiddenException("User is not associated with any tenant")

    return SaaSUPIService(db).get_qr_code(
        tenant_id=current_user.tenant_id,
        reference=reference,
    )


@router.get(
    "/upi/qr-image",
    summary="Get UPI QR Code PNG Image",
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "Returns raw PNG QR code image.",
        }
    },
)
def get_qr_image(
    reference: str = Query(..., description="UPI transaction reference"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns raw PNG QR code image.
    Enforces tenant isolation.
    """
    if not current_user.tenant_id:
        raise ForbiddenException("User is not associated with any tenant")

    image_bytes = SaaSUPIService(db).get_qr_image(
        tenant_id=current_user.tenant_id,
        reference=reference,
    )
    return Response(content=image_bytes, media_type="image/png")


@router.post(
    "/upi/submit",
    response_model=UPITransactionResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit UTR for UPI Transaction",
)
def submit_utr(
    data: UPISubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Transitions a pending UPI transaction to submitted state upon UTR entry.
    Enforces duplicate UTR check and tenant isolation.
    """
    if not current_user.tenant_id:
        raise ForbiddenException("User is not associated with any tenant")

    return SaaSUPIService(db).submit_utr(
        tenant_id=current_user.tenant_id,
        reference=data.reference,
        utr=data.utr,
        payer_vpa=data.payer_vpa,
        proof_image_url=data.proof_image_url,
    )


@router.get(
    "/upi/transactions/{reference}",
    response_model=UPITransactionResponse,
    summary="Get UPI Transaction Status",
)
def get_transaction_status(
    reference: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves the status of a specific UPI transaction for the authenticated tenant.
    Enforces tenant isolation (404 for cross-tenant access).
    """
    if not current_user.tenant_id:
        raise ForbiddenException("User is not associated with any tenant")

    return SaaSUPIService(db).get_transaction(
        tenant_id=current_user.tenant_id,
        reference=reference,
    )


@router.post(
    "/subscription/cancel",
    response_model=SaaSSubscriptionResponse,
    summary="Cancel Tenant Subscription",
)
def cancel_subscription(
    data: SaaSSubscriptionCancelRequest = SaaSSubscriptionCancelRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Schedules cancellation for the authenticated tenant's current subscription.
    - Tenant isolation: tenant_id is derived strictly from current_user.tenant_id.
    - Sets cancel_at_period_end = True and cancelled_at = current timestamp.
    - Subscription and tenant projection remain active until current_period_end.
    - Terminal states (cancelled, expired) cannot be cancelled.
    - Cancellation is idempotent.
    """
    if not current_user.tenant_id:
        raise ForbiddenException("User is not associated with any tenant")

    svc = SaaSSubscriptionService(db)
    sub = svc.cancel_subscription(
        tenant_id=current_user.tenant_id,
        cancel_at_period_end=data.cancel_at_period_end,
        reason=data.reason,
    )
    db.commit()
    db.refresh(sub)
    return sub

