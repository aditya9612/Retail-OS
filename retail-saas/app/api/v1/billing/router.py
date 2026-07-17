from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.order import Order
from app.models.user import User
from app.schemas.billing import ReturnItemRequest
from app.schemas.cart import CartDiscountApply, CartItemCreate, CartItemUpdate, CartSummaryResponse
from app.schemas.order import InvoiceResponse
from app.services.billing_service import BillingService
from app.services.cart_service import CartService
from app.utils.constants import OrderStatus

router = APIRouter(prefix="/billing", tags=["billing"])


def _to_cart_response(cart: dict) -> CartSummaryResponse:
    return CartSummaryResponse(
        store_id=cart.get("store_id") or 0,
        customer_id=cart.get("customer_id"),
        items=[
            {
                **item,
                "quantity": Decimal(item["quantity"]),
                "unit_price": Decimal(item["unit_price"]),
                "discount": Decimal(item.get("discount", "0")),
                "gst_rate": Decimal(item["gst_rate"]),
                "gst_amount": Decimal(item["gst_amount"]),
                "cgst_amount": Decimal(item["cgst_amount"]),
                "sgst_amount": Decimal(item["sgst_amount"]),
                "igst_amount": Decimal(item["igst_amount"]),
                "total_amount": Decimal(item["total_amount"]),
            }
            for item in cart.get("items", [])
        ],
        subtotal=Decimal(cart.get("subtotal", "0")),
        discount_amount=Decimal(cart.get("discount_amount", "0")),
        gst_amount=Decimal(cart.get("gst_amount", "0")),
        cgst_amount=Decimal(cart.get("cgst_amount", "0")),
        sgst_amount=Decimal(cart.get("sgst_amount", "0")),
        igst_amount=Decimal(cart.get("igst_amount", "0")),
        grand_total=Decimal(cart.get("grand_total", "0")),
        same_state=cart.get("same_state", True),
        coupon_code=cart.get("coupon_code"),
    )


@router.post("/cart/add-item", response_model=CartSummaryResponse)
def cart_add_item(
    payload: CartItemCreate,
    store_id: int = Query(...),
    same_state: bool = Query(default=True),
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    cart = CartService(db).add_item(
        user.tenant_id,
        user.id,
        store_id,
        payload.product_id,
        payload.quantity,
        payload.unit_price,
        payload.discount,
        same_state,
    )
    return _to_cart_response(cart)


@router.put("/cart/update-item", response_model=CartSummaryResponse)
def cart_update_item(
    payload: CartItemUpdate,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    cart = CartService(db).update_item(
        user.tenant_id,
        user.id,
        payload.product_id,
        payload.quantity,
        payload.unit_price,
        payload.discount,
    )
    return _to_cart_response(cart)


@router.delete("/cart/remove-item", response_model=CartSummaryResponse)
def cart_remove_item(
    product_id: int = Query(...),
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    cart = CartService(db).remove_item(user.tenant_id, user.id, product_id)
    return _to_cart_response(cart)


@router.get("/cart", response_model=CartSummaryResponse)
def get_cart(
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    cart = CartService(db).get_cart(user.tenant_id, user.id)
    return _to_cart_response(cart)


@router.post("/cart/apply-discount", response_model=CartSummaryResponse)
def cart_apply_discount(
    payload: CartDiscountApply,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    cart = CartService(db).apply_discount(
        user.tenant_id,
        user.id,
        payload.discount_type,
        payload.value,
        payload.coupon_code,
    )
    return _to_cart_response(cart)


@router.post("/invoices/{order_id}", response_model=InvoiceResponse, status_code=201)
def create_invoice_from_order(
    order_id: int,
    same_state: bool = True,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    return BillingService(db).create_invoice(user.tenant_id, order_id, same_state)


@router.get("/invoices/{invoice_id}/pdf")
def download_invoice_pdf_legacy(
    invoice_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    invoice = BillingService(db).get_invoice(user.tenant_id, invoice_id)
    pdf_bytes = BillingService(db).generate_pdf(user.tenant_id, invoice_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={invoice.invoice_number}.pdf"
        }
    )


@router.post("/orders/{order_id}/return")
def process_return_legacy(
    order_id: int,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    from app.core.exceptions import NotFoundException
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.tenant_id == user.tenant_id
    ).first()
    if not order:
        raise NotFoundException("Order not found")
    order.status = OrderStatus.RETURNED.value
    db.commit()
    db.refresh(order)
    return order


@router.post("/returns", response_model=dict)
def process_item_return(
    payload: ReturnItemRequest,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    return BillingService(db).process_return(
        user.tenant_id,
        payload.invoice_id,
        payload.product_id,
        payload.return_quantity,
        payload.reason,
    )