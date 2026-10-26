from datetime import date
import re
from typing import Optional, Union, Literal
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pdf_utils import render_pdf_or_preview
from app.core.security import require_permission
from app.models.user import User
from app.schemas.customer import (
    CustomerCreate,
    CustomerResponse,
    CustomerStatsResponse,
    CustomerUpdate,
    CustomerExportStatus,
    CustomerExportFormat,
    MessageResponse,
    CustomerFeedbackCreate,
    CustomerFeedbackResponse,
    SubResourceNoDataResponse,
    CustomerOrdersResponse,
    validate_customer_name,
    WalletCreditRequest,
    WalletDebitRequest,
    WalletResponse,
    WalletTransactionResponse,
    WalletOperationResponse,
    LoyaltyAddPointsRequest,
    LoyaltyEarnRequest,
    LoyaltyRedeemRequest,
    LoyaltyResponse,
    CommunicationCreate,
    CommunicationResponse,
    ReferralCreate,
    ReferralResponse,
    CustomerNoteCreate,
    CustomerNoteResponse,
    CampaignSendRequest,
    CampaignSendResponse,
    TopCustomerResponse,
    RetentionResponse,
    LifetimeValueResponse,
    LoyaltyReportResponse,
    CustomerStatusUpdate,
    CustomerListResponse,
    CustomerReferralListResponse,
    CustomerCommunicationListResponse,
    TopCustomerListResponse,
    LifetimeValueListResponse,
    LoyaltyReportListResponse,
    CreditLimitUpdateRequest,
    CustomerPaymentRequest,
    CustomerLedgerEntryResponse,
    CustomerLedgerStatementResponse,
    FeedbackAnalyticsResponse,
    CustomerDeleteResponse,
    SendLedgerPdfResponse,
)
from app.services.customer_service import (
    fetch_customers,
    fetch_customer_stats,
    CustomerService,
)
from app.services.order_service import OrderService

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerResponse])
def list_customers(
    name: Optional[str] = Query(None, min_length=2, max_length=100),
    mobile: Optional[str] = Query(None, pattern=r"^[6-9]\d{9}$"),
    segment: Optional[str] = Query(
        None,
        pattern=r"^(new|regular|vip|inactive)$"
    ),
    status: Optional[str] = Query(
        None,
        pattern=r"^(active|inactive|blocked)$"
    ),
    search: Optional[str] = Query(None),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    if name is not None:
        name_clean = name.strip()
        if not name_clean:
            raise HTTPException(status_code=422, detail="Name filter cannot be empty or whitespace")
        try:
            validate_customer_name(name_clean)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        name = name_clean

    if mobile is not None:
        mobile_clean = mobile.strip()
        if not mobile_clean:
            raise HTTPException(status_code=422, detail="Mobile filter cannot be empty or whitespace")
        if not re.fullmatch(r"^[6-9]\d{9}$", mobile_clean):
            raise HTTPException(status_code=422, detail="Mobile number must follow ^[6-9]\\d{9}$")
        mobile = mobile_clean

    if search is not None:
        search_clean = search.strip()
        if not search_clean:
            raise HTTPException(status_code=422, detail="Search query cannot be empty or whitespace")
        search = search_clean

    if status is not None:
        status_clean = status.strip()
        if not status_clean:
            raise HTTPException(status_code=422, detail="Status filter cannot be empty or whitespace")
        if status_clean not in ("active", "inactive", "blocked"):
            raise HTTPException(status_code=422, detail="Invalid status filter")
        status = status_clean

    if segment is not None:
        segment_clean = segment.strip()
        if not segment_clean:
            raise HTTPException(status_code=422, detail="Segment filter cannot be empty or whitespace")
        if segment_clean not in ("new", "regular", "vip", "inactive"):
            raise HTTPException(status_code=422, detail="Invalid segment filter")
        segment = segment_clean

    customers = fetch_customers(
        db=db,
        tenant_id=user.tenant_id,
        name=name,
        mobile=mobile,
        segment=segment,
        status=status,
        search=search,
        page=page,
        page_size=page_size,
    )

    if (name is not None or search is not None) and not customers:
        term = name if name is not None else search
        raise HTTPException(
            status_code=404,
            detail=f"No customer found matching '{term}'"
        )

    return customers


@router.get("/stats", response_model=CustomerStatsResponse)
def customer_stats(
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return fetch_customer_stats(
        db=db,
        tenant_id=user.tenant_id,
    )


@router.post("", response_model=CustomerResponse, status_code=201)
def create_customer(
    data: CustomerCreate,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).create_customer(user.tenant_id, data)


@router.post(
    "/feedback",
    response_model=CustomerFeedbackResponse,
    status_code=201,
)
def create_feedback(
    data: CustomerFeedbackCreate,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).create_feedback(user.tenant_id, data)


@router.get(
    "/feedback",
    response_model=Union[list[CustomerFeedbackResponse], SubResourceNoDataResponse],
)
def get_feedback(
    customer_id: Optional[int] = Query(None, gt=0, deprecated=True, description="Deprecated: Use GET /customers/feedback/{customer_id} instead"),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_feedback(
        user.tenant_id,
        customer_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/feedback/analytics",
    response_model=FeedbackAnalyticsResponse,
)
def get_feedback_analytics(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_feedback_analytics(
        user.tenant_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get(
    "/feedback/{customer_id}",
    response_model=Union[list[CustomerFeedbackResponse], SubResourceNoDataResponse],
)
def get_feedback_by_customer_id(
    customer_id: int = Path(..., gt=0),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_feedback(
        user.tenant_id,
        customer_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/wallet/{customer_id}",
    response_model=WalletResponse,
)
def get_wallet(
    customer_id: int = Path(..., gt=0),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_wallet(
        user.tenant_id,
        customer_id,
    )


@router.post(
    "/wallet/credit",
    response_model=WalletOperationResponse,
)
def credit_wallet(
    data: WalletCreditRequest,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).credit_wallet(
        user.tenant_id,
        data,
    )


@router.post(
    "/wallet/debit",
    response_model=WalletOperationResponse,
)
def debit_wallet(
    data: WalletDebitRequest,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).debit_wallet(
        user.tenant_id,
        data,
    )


@router.get(
    "/wallet/transactions/{customer_id}",
    response_model=Union[list[WalletTransactionResponse], SubResourceNoDataResponse],
)
def wallet_transactions(
    customer_id: int = Path(..., gt=0),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_wallet_transactions(
        user.tenant_id,
        customer_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/birthdays",
    response_model=Union[list[CustomerResponse], SubResourceNoDataResponse],
)
def birthday_customers(
    month: Optional[int] = Query(None, ge=1, le=12),
    day: Optional[int] = Query(None, ge=1, le=31),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    if month is None and day is None:
        today = date.today()
        target_month = today.month
        target_day = today.day
    else:
        target_month = month
        target_day = day

    return CustomerService(db).get_birthday_customers(
        tenant_id=user.tenant_id,
        month=target_month,
        day=target_day,
    )


@router.post(
    "/referrals",
    response_model=ReferralResponse,
)
def create_referral(
    data: ReferralCreate,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).create_referral(
        user.tenant_id,
        data,
    )


@router.get(
    "/referrals",
    response_model=CustomerReferralListResponse,
)
def get_referrals(
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    referrals = CustomerService(db).get_referrals(
        user.tenant_id,
        page=page,
        page_size=page_size,
    )
    return {
        "success": True,
        "message": "Referrals retrieved successfully" if referrals else "No referrals found",
        "data": referrals,
    }


@router.get(
    "/communications",
    response_model=CustomerCommunicationListResponse,
)
def get_communications(
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    comms = CustomerService(db).get_communications(
        user.tenant_id,
        page=page,
        page_size=page_size,
    )
    return {
        "success": True,
        "message": "Communications retrieved successfully" if comms else "No communications found",
        "data": comms,
    }


@router.post(
    "/notes",
    response_model=CustomerNoteResponse,
)
def create_note(
    data: CustomerNoteCreate,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).create_note(
        user.tenant_id,
        data,
        user_id=user.id,
    )


@router.get(
    "/notes",
    response_model=Union[list[CustomerNoteResponse], SubResourceNoDataResponse],
)
def get_notes(
    customer_id: Optional[int] = Query(None, gt=0, deprecated=True, description="Deprecated: Use GET /customers/notes/{customer_id} instead"),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_notes(
        user.tenant_id,
        customer_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/notes/{customer_id}",
    response_model=Union[list[CustomerNoteResponse], SubResourceNoDataResponse],
)
def get_notes_by_customer_id(
    customer_id: int = Path(..., gt=0),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_notes(
        user.tenant_id,
        customer_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/export-directory",
    summary="Export Complete Customer Directory",
    description=(
        "Exports the tenant customer directory filtered by status ('all', 'active', 'inactive') "
        "as either an analytical Excel workbook (.xlsx) or a branded PDF document (.pdf). "
        "Features customer contact details, loyalty points, and account status. "
        "Requires 'customers:read' permission."
    ),
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
                "application/pdf": {},
            },
            "description": "Exported Customer Directory file stream (Excel or PDF).",
        }
    },
)
def export_directory(
    status: CustomerExportStatus = Query(
        ...,
        description="Customer status filter (required: 'all', 'active', 'inactive')"
    ),
    format: CustomerExportFormat = Query(
        ...,
        description="Export format (required: 'excel', 'pdf')"
    ),
    mode: Literal["download", "preview"] = Query(default="download", description="Delivery mode: 'download' (attachment) or 'preview' (visual preview)"),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db)
):
    service = CustomerService(db)

    file = service.export_directory(
        tenant_id=user.tenant_id,
        status=status.value,
        format=format.value
    )

    if format.value == "excel":
        return StreamingResponse(
            file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition":
                "attachment; filename=customer_directory.xlsx"
            }
        )

    return render_pdf_or_preview(
        pdf_content=file,
        filename_base="customer_directory",
        mode=mode,
    )


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: int = Path(..., gt=0),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_customer(user.tenant_id, customer_id)


@router.put("/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: int = Path(..., gt=0),
    data: CustomerUpdate = ...,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).update_customer(user.tenant_id, customer_id, data)


@router.delete(
    "/{customer_id}",
    response_model=CustomerDeleteResponse,
)
def delete_customer(
    customer_id: int = Path(..., gt=0),
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).delete_customer(user.tenant_id, customer_id)


@router.get(
    "/{customer_id}/orders",
    response_model=CustomerOrdersResponse,
)
def customer_orders(
    customer_id: int = Path(..., gt=0),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return OrderService(db).get_customer_history(user.tenant_id, customer_id)


@router.post("/{customer_id}/loyalty", response_model=LoyaltyResponse)
def add_loyalty(
    customer_id: int = Path(..., gt=0),
    data: LoyaltyAddPointsRequest = ...,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).add_loyalty_points(user.tenant_id, customer_id, data.points)


@router.post(
    "/loyalty/earn",
    response_model=LoyaltyResponse,
)
def earn_loyalty(
    data: LoyaltyEarnRequest,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).earn_loyalty_points(
        user.tenant_id,
        data,
    )


@router.post(
    "/loyalty/redeem",
    response_model=LoyaltyResponse,
)
def redeem_loyalty(
    data: LoyaltyRedeemRequest,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).redeem_loyalty_points(
        user.tenant_id,
        data,
    )


@router.get(
    "/{customer_id}/loyalty",
    response_model=LoyaltyResponse,
)
def get_loyalty(
    customer_id: int = Path(..., gt=0),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_loyalty(
        user.tenant_id,
        customer_id,
    )


@router.get(
    "/{customer_id}/loyalty/history",
    response_model=Union[list[LoyaltyResponse], SubResourceNoDataResponse],
)
def get_loyalty_history(
    customer_id: int = Path(..., gt=0),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_loyalty_history(
        user.tenant_id,
        customer_id,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/{customer_id}/status",
    response_model=CustomerResponse,
)
def update_customer_status(
    customer_id: int = Path(..., gt=0),
    data: CustomerStatusUpdate = ...,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).update_customer_status(
        user.tenant_id,
        customer_id,
        data.status
    )


@router.patch(
    "/{customer_id}/credit-limit",
    response_model=CustomerResponse,
)
def update_credit_limit(
    customer_id: int = Path(..., gt=0),
    data: CreditLimitUpdateRequest = ...,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).update_credit_limit(
        user.tenant_id,
        customer_id,
        data.credit_limit,
    )


@router.get(
    "/{customer_id}/ledger",
    response_model=CustomerLedgerStatementResponse,
)
def get_customer_ledger(
    customer_id: int = Path(..., gt=0),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_customer_ledger(
        user.tenant_id,
        customer_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.post(
    "/{customer_id}/ledger/payment",
    response_model=CustomerLedgerEntryResponse,
    status_code=201,
)
def record_customer_payment(
    customer_id: int = Path(..., gt=0),
    data: CustomerPaymentRequest = ...,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).record_customer_payment(
        user.tenant_id,
        customer_id,
        data,
    )


@router.get(
    "/{customer_id}/ledger/pdf",
    summary="Download or Preview Customer Ledger PDF",
    description="Exports or previews customer account statement/ledger. Mode can be 'download' (attachment .pdf) or 'preview' (visual PNG preview in Swagger UI / browser).",
    responses={
        200: {
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                "image/png": {"schema": {"type": "string", "format": "binary"}, "description": "Visual document PNG preview for Swagger UI / browser"},
            },
            "description": "Rendered Ledger PDF download or visual PNG preview for Swagger UI.",
        }
    },
)
def export_customer_ledger_pdf(
    customer_id: int = Path(..., gt=0),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    mode: Literal["download", "preview"] = Query(default="download", description="Delivery mode: 'download' or 'preview'"),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    pdf_stream = CustomerService(db).export_ledger_pdf(
        user.tenant_id,
        customer_id,
        from_date=from_date,
        to_date=to_date,
    )
    return render_pdf_or_preview(
        pdf_content=pdf_stream,
        filename_base=f"customer_{customer_id}_ledger",
        mode=mode,
    )


@router.post(
    "/{customer_id}/send-ledger-pdf",
    response_model=SendLedgerPdfResponse,
)
def send_customer_ledger_pdf(
    customer_id: int = Path(..., gt=0),
    channel: str = Query("WHATSAPP", pattern="^(WHATSAPP|SMS|EMAIL)$"),
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).send_ledger_pdf(
        user.tenant_id,
        customer_id,
        channel=channel,
    )


@router.post(
    "/notifications/sms",
    response_model=CommunicationResponse,
)
def send_sms(
    data: CommunicationCreate,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    if data.communication_type != "SMS":
        raise HTTPException(
            status_code=422,
            detail="Only SMS communication type is allowed for this endpoint",
        )

    return CustomerService(db).send_communication(
        user.tenant_id,
        data,
    )


@router.get(
    "/notifications/sms",
    response_model=CustomerCommunicationListResponse,
)
def get_sms_notifications(
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    sms_list = CustomerService(db).get_communications_by_type(
        user.tenant_id,
        "SMS",
        page=page,
        page_size=page_size,
    )
    return {
        "success": True,
        "message": "SMS notifications retrieved successfully" if sms_list else "No SMS notifications found",
        "data": sms_list,
    }


@router.post(
    "/notifications/whatsapp",
    response_model=CommunicationResponse,
)
def send_whatsapp(
    data: CommunicationCreate,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    if data.communication_type != "WHATSAPP":
        raise HTTPException(
            status_code=422,
            detail="Only WHATSAPP communication type is allowed for this endpoint",
        )

    return CustomerService(db).send_communication(
        user.tenant_id,
        data,
    )


@router.get(
    "/notifications/whatsapp",
    response_model=CustomerCommunicationListResponse,
)
def get_whatsapp_notifications(
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    wa_list = CustomerService(db).get_communications_by_type(
        user.tenant_id,
        "WHATSAPP",
        page=page,
        page_size=page_size,
    )
    return {
        "success": True,
        "message": "WhatsApp notifications retrieved successfully" if wa_list else "No WhatsApp notifications found",
        "data": wa_list,
    }


@router.post(
    "/campaigns/send",
    response_model=CampaignSendResponse,
)
def send_campaign(
    data: CampaignSendRequest,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).send_campaign(
        user.tenant_id,
        data,
    )


@router.get(
    "/customer-analytics/top-customers",
    response_model=list[TopCustomerResponse],
)
def top_customers(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    limit: Optional[int] = Query(10, ge=1, le=100),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_top_customers(
        user.tenant_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit or 10,
    )


@router.get(
    "/customer-analytics/retention",
    response_model=RetentionResponse,
)
def retention_report(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_retention_report(
        user.tenant_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get(
    "/customer-analytics/lifetime-value",
    response_model=list[LifetimeValueResponse],
)
def lifetime_value(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_lifetime_value(
        user.tenant_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get(
    "/customer-analytics/loyalty-report",
    response_model=list[LoyaltyReportResponse],
)
def loyalty_report(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_loyalty_report(
        user.tenant_id,
        from_date=from_date,
        to_date=to_date,
    )
