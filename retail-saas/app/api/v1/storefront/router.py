from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pdf_utils import render_pdf_or_preview
from app.core.security import get_current_customer
from app.models.customer import Customer
from app.schemas.storefront import (
    StorefrontCartItemRequest,
    StorefrontCartItemUpdate,
    StorefrontCartResponse,
    StorefrontCategoryItem,
    StorefrontCheckoutRequest,
    StorefrontCheckoutResponse,
    StorefrontCustomerProfileResponse,
    StorefrontOrderDetailResponse,
    StorefrontOrderSummary,
    StorefrontProductListResponse,
)
from app.services.billing_service import BillingService
from app.services.storefront_service import StorefrontService

router = APIRouter(prefix="/storefront", tags=["Customer Storefront & Online Shopping"])


# ==============================================================================
# 1. CATALOG & PRODUCTS (Browse & Search)
# ==============================================================================

@router.get(
    "/categories",
    response_model=List[StorefrontCategoryItem],
    summary="List Store Categories",
    description="Browse all available product categories in the store.",
)
def list_categories(
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_categories(customer.tenant_id)


@router.get(
    "/products",
    response_model=StorefrontProductListResponse,
    summary="List & Search Store Products",
    description="Search and browse products available in the store with prices, discounts, and stock availability.",
)
def list_products(
    category_id: Optional[int] = Query(default=None, description="Filter by category ID"),
    search: Optional[str] = Query(default=None, description="Search by product name, barcode, or SKU"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Items per page"),
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_products(
        tenant_id=customer.tenant_id,
        category_id=category_id,
        search=search,
        page=page,
        page_size=page_size,
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
    response_model=List[StorefrontOrderSummary],
    summary="List Customer Orders",
    description="Retrieves the order history and statuses for the logged-in customer.",
)
def list_my_orders(
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_my_orders(customer.tenant_id, customer.id)


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
