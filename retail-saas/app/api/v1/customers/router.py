from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date
from fastapi import Path

from typing import Optional
from fastapi import Query
from app.services.customer_service import (
    fetch_customers,
    fetch_customer_stats,
)
from app.services.order_service import CustomerService, OrderService


from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.customer import (
    CustomerCreate,
    CustomerResponse,
    CustomerStatsResponse,
    CustomerUpdate,
    MessageResponse,
    CustomerFeedbackCreate,
    CustomerFeedbackResponse,
    WalletCreditRequest,
    WalletDebitRequest,
    WalletResponse,
    WalletTransactionResponse,
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
)

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerResponse])
def list_customers(
    name: Optional[str] = Query(None, min_length=2, max_length=100),
    mobile: Optional[str] = Query(None, pattern=r"^[6-9]\d{9}$"),
    segment: Optional[str] = Query(
        None,
        pattern="^(new|regular|vip|inactive)$"
    ),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return fetch_customers(
        db=db,
        tenant_id=user.tenant_id,
        name=name,
        mobile=mobile,
        segment=segment
    )

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
    return CustomerService(db).create_feedback(data)

@router.get(
    "/feedback",
    response_model=list[CustomerFeedbackResponse],
)
def get_feedback(
    customer_id: int | None = Query(None),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_feedback(customer_id)

@router.get(
    "/wallet/{customer_id}",
    response_model=WalletResponse,
)
def get_wallet(
    customer_id: int,
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_wallet(
        user.tenant_id,
        customer_id,
    )

@router.post(
    "/wallet/credit",
    response_model=WalletResponse,
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
    response_model=WalletResponse,
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
    response_model=list[WalletTransactionResponse],
)
def wallet_transactions(
    customer_id: int,
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_wallet_transactions(
        user.tenant_id,
        customer_id,
    )

@router.get(
    "/birthdays",
    response_model=list[CustomerResponse],
)
def birthday_customers(
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    today = date.today()

    return CustomerService(db).get_birthday_customers(
        tenant_id=user.tenant_id,
        month=today.month,
        day=today.day,
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
    response_model=list[ReferralResponse],
)
def get_referrals(
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_referrals(
        user.tenant_id,
    )

@router.get(
    "/communications",
    response_model=list[CommunicationResponse],
)
def get_communications(
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_communications(
        user.tenant_id,
    )
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
    )

@router.get(
    "/notes",
    response_model=list[CustomerNoteResponse],
)
def get_notes(
    customer_id: int | None = Query(None),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_notes(
        user.tenant_id,
        customer_id,
    )            

@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: int,
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_customer(user.tenant_id, customer_id)


@router.patch("/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).update_customer(user.tenant_id, customer_id, data)


@router.get("/{customer_id}/orders")
def customer_orders(
    customer_id: int = Path(..., gt=0),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return OrderService(db).get_customer_history(user.tenant_id, customer_id)


@router.post("/{customer_id}/loyalty")
def add_loyalty(
    customer_id: int = Path(..., gt=0),
    points: int = Query(..., gt=0, le=10000),
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).add_loyalty_points(user.tenant_id, customer_id, points)

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
    customer_id: int,
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_loyalty(
        user.tenant_id,
        customer_id,
    )

@router.get(
    "/{customer_id}/loyalty/history",
    response_model=list[LoyaltyResponse],
)
def get_loyalty_history(
    customer_id: int,
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_loyalty_history(
        user.tenant_id,
        customer_id,
    )



@router.delete("/{customer_id}", response_model=MessageResponse)
def delete_customer(
    customer_id: int,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).delete_customer(
        user.tenant_id,
        customer_id
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
    return CustomerService(db).send_communication(
        user.tenant_id,
        data,
    )

@router.post(
    "/notifications/whatsapp",
    response_model=CommunicationResponse,
)
def send_whatsapp(
    data: CommunicationCreate,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    data.communication_type = "WHATSAPP"

    return CustomerService(db).send_communication(
        user.tenant_id,
        data,
    )

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
    response_model=list[TopCustomerResponse]
)
def top_customers(
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_top_customers(user.tenant_id)   

@router.get(
    "/customer-analytics/retention",
    response_model=RetentionResponse,
)
def retention_report(
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_retention_report(
        user.tenant_id
    )


@router.get(
    "/customer-analytics/lifetime-value",
    response_model=list[LifetimeValueResponse],
)
def lifetime_value(
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_lifetime_value(
        user.tenant_id
    )

@router.get(
    "/customer-analytics/loyalty-report",
    response_model=list[LoyaltyReportResponse],
)
def loyalty_report(
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_loyalty_report(
        user.tenant_id
    )
        
