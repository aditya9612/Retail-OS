from datetime import date
from typing import List, Literal, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pdf_utils import render_pdf_or_preview
from app.core.security import get_current_customer
from app.models.customer import Customer
from app.schemas.common import ListWithCountsResponse, TotalCountOnly
from app.schemas.customer import (
    CustomerFeedbackResponse,
    CustomerLedgerStatementResponse,
    CustomerReferralListResponse,
    LoyaltyResponse,
    ReferralResponse,
    SubResourceNoDataResponse,
    WalletResponse,
    WalletTransactionResponse,
)
from app.schemas.storefront import (
    StorefrontCartItemRequest,
    StorefrontCartItemUpdate,
    StorefrontCartResponse,
    StorefrontCategoryItem,
    StorefrontCheckoutRequest,
    StorefrontCheckoutResponse,
    StorefrontCustomerProfileResponse,
    StorefrontCustomerProfileUpdate,
    StorefrontFeedbackRequest,
    StorefrontNotificationListResponse,
    StorefrontOrderCancelRequest,
    StorefrontOrderCancelResponse,
    StorefrontOrderCounts,
    StorefrontOrderDetailResponse,
    StorefrontOrderSummary,
    StorefrontProductDetailResponse,
    StorefrontProductListResponse,
    StorefrontReferralRequest,
)
from app.services.billing_service import BillingService
from app.services.storefront_service import StorefrontService

router = APIRouter(prefix="/storefront", tags=["Customer Storefront & Online Shopping"])


# ==============================================================================
# 1. CATALOG & PRODUCTS (Browse & Search)
# ==============================================================================

@router.get(
    "/categories",
    response_model=ListWithCountsResponse[StorefrontCategoryItem, TotalCountOnly],
    summary="List Store Categories",
    description="Browse all available product categories in the store.",
)
def list_categories(
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_categories_with_counts(customer.tenant_id)


@router.get(
    "/products",
    response_model=StorefrontProductListResponse,
    summary="List & Search Store Products",
    description="Search and browse products available in the store with prices, discounts, and stock availability.",
)
def list_products(
    store_id: Optional[int] = Query(default=None, gt=0, description="Optional Store ID to check store-specific inventory"),
    category_id: Optional[int] = Query(default=None, description="Filter by category ID"),
    search: Optional[str] = Query(default=None, description="Search by product name, barcode, or SKU"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Items per page"),
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_products(
        tenant_id=customer.tenant_id,
        store_id=store_id,
        category_id=category_id,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/products/{product_id}",
    response_model=StorefrontProductDetailResponse,
    summary="Get Store Product Details",
    description="Fetches full details, gallery images, barcode, category, and live stock for a product.",
)
def get_product_details(
    product_id: int,
    store_id: Optional[int] = Query(default=None, gt=0, description="Optional Store ID to check store-specific inventory"),
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_product_detail(
        tenant_id=customer.tenant_id,
        product_id=product_id,
        store_id=store_id,
    )


# ==============================================================================
# 2. SHOPPING CART (Customer Cart Operations)
# ==============================================================================

@router.get(
    "/cart",
    response_model=StorefrontCartResponse,
    summary="View Shopping Cart",
    description="Retrieves the logged-in customer's shopping cart, items, subtotal, and tax estimation.",
)
def get_cart(
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_cart(customer.tenant_id, customer.id)


@router.post(
    "/cart/items",
    response_model=StorefrontCartResponse,
    summary="Add Product to Cart",
    description="Adds a product to the customer's shopping cart with the specified quantity.",
)
def add_to_cart(
    payload: StorefrontCartItemRequest,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).add_to_cart(
        tenant_id=customer.tenant_id,
        customer_id=customer.id,
        product_id=payload.product_id,
        quantity=payload.quantity,
    )


@router.put(
    "/cart/items/{product_id}",
    response_model=StorefrontCartResponse,
    summary="Update Cart Item Quantity",
    description="Updates the quantity of an item in the cart. Passing quantity=0 removes the item.",
)
def update_cart_item(
    product_id: int,
    payload: StorefrontCartItemUpdate,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).update_cart_item(
        tenant_id=customer.tenant_id,
        customer_id=customer.id,
        product_id=product_id,
        quantity=payload.quantity,
    )


@router.delete(
    "/cart/items/{product_id}",
    response_model=StorefrontCartResponse,
    summary="Remove Item from Cart",
    description="Removes a specific product from the customer's shopping cart.",
)
def remove_from_cart(
    product_id: int,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).remove_from_cart(
        tenant_id=customer.tenant_id,
        customer_id=customer.id,
        product_id=product_id,
    )


@router.delete(
    "/cart",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear Entire Cart",
    description="Empties all items from the customer's shopping cart.",
)
def clear_cart(
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    StorefrontService(db).clear_cart(customer.tenant_id, customer.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# 3. CHECKOUT & ORDER PLACEMENT
# ==============================================================================

@router.post(
    "/checkout",
    response_model=StorefrontCheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Checkout & Place Online Order",
    description=(
        "Converts the active cart into an official customer order. "
        "Supports Home Delivery or Store Pickup, and COD / UPI / Wallet payment."
    ),
)
def checkout(
    payload: StorefrontCheckoutRequest,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).checkout(
        tenant_id=customer.tenant_id,
        customer=customer,
        payload=payload,
    )


# ==============================================================================
# 4. CUSTOMER ORDERS & INVOICES
# ==============================================================================

@router.get(
    "/my-orders",
    response_model=ListWithCountsResponse[StorefrontOrderSummary, StorefrontOrderCounts],
    summary="List Customer Orders",
    description="Retrieves the order history and statuses for the logged-in customer.",
)
def list_my_orders(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_my_orders_with_counts(
        customer.tenant_id, customer.id, page=page, page_size=page_size
    )


@router.get(
    "/my-orders/{order_id}",
    response_model=StorefrontOrderDetailResponse,
    summary="Get Order Details & Tracking",
    description="Returns detailed line items, live delivery tracking, and invoice link for an order.",
)
def get_order_details(
    order_id: int,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_order_details(
        tenant_id=customer.tenant_id,
        customer_id=customer.id,
        order_id=order_id,
    )


@router.post(
    "/my-orders/{order_id}/cancel",
    response_model=StorefrontOrderCancelResponse,
    summary="Cancel Customer Online Order",
    description=(
        "Allows customer to cancel a pending order. "
        "Automatically refunds wallet payments and restores inventory stock."
    ),
)
def cancel_my_order(
    order_id: int,
    payload: Optional[StorefrontOrderCancelRequest] = None,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).cancel_order(
        tenant_id=customer.tenant_id,
        customer_id=customer.id,
        order_id=order_id,
        payload=payload,
    )


@router.get(
    "/my-orders/{order_id}/pdf",
    summary="Download Order Tax Invoice PDF",
    description="Downloads the official GST tax invoice PDF for an issued sales order.",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Tax invoice PDF document download.",
        }
    },
)
def download_order_pdf(
    order_id: int,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    order_detail = StorefrontService(db).get_order_details(
        tenant_id=customer.tenant_id,
        customer_id=customer.id,
        order_id=order_id,
    )

    from app.models.invoice import Invoice
    invoice = (
        db.query(Invoice)
        .filter(Invoice.order_id == order_id, Invoice.tenant_id == customer.tenant_id)
        .first()
    )
    if not invoice:
        raise HTTPException(
            status_code=404,
            detail="Invoice not yet generated for this order (store processing)",
        )

    pdf_bytes = BillingService(db).generate_pdf(
        tenant_id=customer.tenant_id,
        invoice_id=invoice.id,
        system_context=True,
    )

    return render_pdf_or_preview(
        pdf_content=pdf_bytes,
        filename_base=f"invoice_{invoice.invoice_number}",
        mode="download",
    )


# ==============================================================================
# 5. CUSTOMER PROFILE & WALLET
# ==============================================================================

@router.get(
    "/profile",
    response_model=StorefrontCustomerProfileResponse,
    summary="Get Customer Profile & Wallet",
    description="Returns customer details, loyalty points, wallet balance, and outstanding ledger balance.",
)
def get_profile(
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_customer_profile(customer.tenant_id, customer.id)


@router.put(
    "/profile",
    response_model=StorefrontCustomerProfileResponse,
    summary="Update Customer Profile",
    description="Updates the customer's personal details, address, and birthday.",
)
def update_profile(
    payload: StorefrontCustomerProfileUpdate,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).update_customer_profile(
        customer.tenant_id, customer.id, payload
    )


# ==============================================================================
# 6. CUSTOMER WALLET & PASSBOOK
# ==============================================================================

@router.get(
    "/wallet",
    response_model=WalletResponse,
    summary="Get Customer Wallet Balance",
    description="Retrieves the logged-in customer's wallet balance and status.",
)
def get_my_wallet(
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_wallet(customer.tenant_id, customer.id)


@router.get(
    "/wallet/transactions",
    response_model=Union[List[WalletTransactionResponse], SubResourceNoDataResponse],
    summary="Get Wallet Transaction Passbook",
    description="Retrieves history of wallet credits, debits, and order refunds.",
)
def get_my_wallet_transactions(
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_wallet_transactions(
        customer.tenant_id, customer.id, page=page, page_size=page_size
    )


# ==============================================================================
# 7. CUSTOMER LOYALTY POINTS HISTORY
# ==============================================================================

@router.get(
    "/loyalty/history",
    response_model=Union[List[LoyaltyResponse], SubResourceNoDataResponse],
    summary="Get Customer Loyalty Points Passbook",
    description="Retrieves history of earned and redeemed loyalty rewards.",
)
def get_my_loyalty_history(
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_loyalty_history(
        customer.tenant_id, customer.id, page=page, page_size=page_size
    )


# ==============================================================================
# 8. CUSTOMER KHATA / UDHAR LEDGER STATEMENT
# ==============================================================================

@router.get(
    "/ledger",
    response_model=CustomerLedgerStatementResponse,
    summary="Get Customer Khata / Ledger Statement",
    description="Retrieves the customer's personal credit purchase, payment history, and current outstanding debt balance.",
)
def get_my_ledger(
    from_date: Optional[date] = Query(None, description="Statement start date"),
    to_date: Optional[date] = Query(None, description="Statement end date"),
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_customer_ledger(
        customer.tenant_id, customer.id, from_date=from_date, to_date=to_date
    )


@router.get(
    "/ledger/pdf",
    summary="Download Customer Khata Statement PDF",
    description="Generates and downloads the customer's official store credit ledger statement as PDF.",
    responses={
        200: {
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                "image/png": {"schema": {"type": "string", "format": "binary"}},
            },
            "description": "Rendered Ledger PDF download or visual PNG preview.",
        }
    },
)
def download_my_ledger_pdf(
    from_date: Optional[date] = Query(None, description="Statement start date"),
    to_date: Optional[date] = Query(None, description="Statement end date"),
    mode: Literal["download", "preview"] = Query(default="download", description="Delivery mode"),
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    pdf_stream = StorefrontService(db).export_ledger_pdf(
        customer.tenant_id, customer.id, from_date=from_date, to_date=to_date
    )
    return render_pdf_or_preview(
        pdf_content=pdf_stream,
        filename_base=f"khata_statement_{customer.phone}",
        mode=mode,
    )


# ==============================================================================
# 9. CUSTOMER FEEDBACK & REVIEWS
# ==============================================================================

@router.post(
    "/feedback",
    response_model=CustomerFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Customer Feedback & Rating",
    description="Allows the customer to submit a 1 to 5 star rating and comment for store service or delivery.",
)
def submit_customer_feedback(
    payload: StorefrontFeedbackRequest,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).create_feedback(
        customer.tenant_id, customer.id, payload
    )


# ==============================================================================
# 10. CUSTOMER REFERRALS (REFER & EARN)
# ==============================================================================

@router.post(
    "/referrals",
    response_model=ReferralResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a Friend (Refer & Earn)",
    description="Generates an official referral invite code to share with friends and family.",
)
def create_customer_referral(
    payload: StorefrontReferralRequest,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).create_referral(
        customer.tenant_id, customer.id, payload
    )


@router.get(
    "/referrals",
    response_model=CustomerReferralListResponse,
    summary="Get My Referrals",
    description="Lists all friends referred by the customer and referral reward statuses.",
)
def get_my_referrals(
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_my_referrals(
        customer.tenant_id, customer.id, page=page, page_size=page_size
    )


# ==============================================================================
# 11. CUSTOMER NOTIFICATIONS INBOX
# ==============================================================================

@router.get(
    "/notifications",
    response_model=StorefrontNotificationListResponse,
    summary="Get Customer Notifications Inbox",
    description="Retrieves order updates, delivery alerts, and promotional messages sent to this customer.",
)
def get_my_notifications(
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_my_notifications(
        customer.tenant_id, customer.id, page=page, page_size=page_size
    )
