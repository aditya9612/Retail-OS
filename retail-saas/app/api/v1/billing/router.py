from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppException, ForbiddenException
from app.core.security import require_permission
from app.models.product import Product
from app.models.user import User
from app.schemas.billing import ReturnItemRequest
from app.schemas.cart import (
    CartDiscountApply,
    CartItemCreate,
    CartItemUpdate,
    CartSummaryResponse,
)
from app.services.billing_service import BillingService
from app.services.cart_service import CartService


router = APIRouter(
    prefix="/billing",
    tags=["billing"],
)


def _to_cart_response(
    cart: dict,
) -> CartSummaryResponse:
    gst_amount = Decimal(
        str(cart.get("gst_amount", "0.00"))
    )
    cgst_amount = Decimal(
        str(cart.get("cgst_amount", "0.00"))
    )
    sgst_amount = Decimal(
        str(cart.get("sgst_amount", "0.00"))
    )
    igst_amount = Decimal(
        str(cart.get("igst_amount", "0.00"))
    )
    same_state = bool(
        cart.get("same_state", True)
    )

    if same_state:
        if igst_amount != Decimal("0.00"):
            raise AppException(
                "IGST must be zero for intra-state billing"
            )

        if cgst_amount + sgst_amount != gst_amount:
            raise AppException(
                "Total GST amount does not match the sum of CGST and SGST amounts"
            )
    else:
        if (
            cgst_amount != Decimal("0.00")
            or sgst_amount != Decimal("0.00")
        ):
            raise AppException(
                "CGST and SGST must be zero for inter-state billing"
            )

        if igst_amount != gst_amount:
            raise AppException(
                "Total GST amount does not match IGST amount"
            )

    return CartSummaryResponse(
        store_id=int(
            cart.get("store_id") or 0
        ),
        customer_id=cart.get("customer_id"),
        items=[
            {
                **item,
                "quantity": Decimal(
                    item["quantity"]
                ),
                "unit_price": Decimal(
                    item["unit_price"]
                ),
                "discount": Decimal(
                    item.get("discount", "0.00")
                ),
                "gst_rate": Decimal(
                    item["gst_rate"]
                ),
                "gst_amount": Decimal(
                    item["gst_amount"]
                ),
                "cgst_amount": Decimal(
                    item["cgst_amount"]
                ),
                "sgst_amount": Decimal(
                    item["sgst_amount"]
                ),
                "igst_amount": Decimal(
                    item["igst_amount"]
                ),
                "total_amount": Decimal(
                    item["total_amount"]
                ),
            }
            for item in cart.get("items", [])
        ],
        subtotal=Decimal(
            str(cart.get("subtotal", "0.00"))
        ),
        discount_amount=Decimal(
            str(
                cart.get(
                    "discount_amount",
                    "0.00",
                )
            )
        ),
        gst_amount=gst_amount,
        cgst_amount=cgst_amount,
        sgst_amount=sgst_amount,
        igst_amount=igst_amount,
        grand_total=Decimal(
            str(
                cart.get(
                    "grand_total",
                    "0.00",
                )
            )
        ),
        same_state=same_state,
        coupon_code=cart.get("coupon_code"),
    )


def _ensure_price_override_allowed(
    user: User,
    db: Session,
    tenant_id: int,
    product_id: int,
    unit_price: Decimal | None,
) -> None:
    if unit_price is None:
        return

    if unit_price <= 0:
        raise AppException(
            "Unit price must be greater than zero"
        )

    product = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.tenant_id == tenant_id,
        )
        .first()
    )

    if not product:
        raise AppException(
            "Product not found"
        )

    if hasattr(product, "is_active") and not product.is_active:
        raise AppException(
            "Product is inactive"
        )

    if unit_price != product.price:
        permissions = (
            user.role.permissions
            if user.role
            else []
        )

        if (
            "*" not in permissions
            and "billing:price_override"
            not in permissions
        ):
            raise ForbiddenException(
                "Price override not allowed for your role"
            )


@router.post(
    "/cart/add-item",
    response_model=CartSummaryResponse,
)
def cart_add_item(
    payload: CartItemCreate,
    store_id: int = Query(..., gt=0),
    same_state: bool = Query(default=True),
    user: User = Depends(
        require_permission("billing:write")
    ),
    db: Session = Depends(get_db),
):
    if (
        payload.store_id is not None
        and payload.store_id != store_id
    ):
        raise AppException(
            "Payload store_id does not match query store_id"
        )

    _ensure_price_override_allowed(
        user,
        db,
        user.tenant_id,
        payload.product_id,
        payload.unit_price,
    )

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


@router.put(
    "/cart/update-item",
    response_model=CartSummaryResponse,
)
def cart_update_item(
    payload: CartItemUpdate,
    user: User = Depends(
        require_permission("billing:write")
    ),
    db: Session = Depends(get_db),
):
    _ensure_price_override_allowed(
        user,
        db,
        user.tenant_id,
        payload.product_id,
        payload.unit_price,
    )

    cart = CartService(db).update_item(
        user.tenant_id,
        user.id,
        payload.product_id,
        payload.quantity,
        payload.unit_price,
        payload.discount,
    )

    return _to_cart_response(cart)


@router.delete(
    "/cart/remove-item",
    response_model=CartSummaryResponse,
)
def cart_remove_item(
    product_id: int = Query(..., gt=0),
    user: User = Depends(
        require_permission("billing:write")
    ),
    db: Session = Depends(get_db),
):
    cart = CartService(db).remove_item(
        user.tenant_id,
        user.id,
        product_id,
    )

    return _to_cart_response(cart)


@router.get(
    "/cart",
    response_model=CartSummaryResponse,
)
def get_cart(
    user: User = Depends(
        require_permission("billing:read")
    ),
    db: Session = Depends(get_db),
):
    cart = CartService(db).get_cart(
        user.tenant_id,
        user.id,
    )

    return _to_cart_response(cart)


@router.post(
    "/cart/apply-discount",
    response_model=CartSummaryResponse,
)
def cart_apply_discount(
    payload: CartDiscountApply,
    user: User = Depends(
        require_permission("billing:write")
    ),
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


@router.post(
    "/returns",
    response_model=dict,
)
def process_item_return(
    payload: ReturnItemRequest,
    user: User = Depends(
        require_permission("billing:write")
    ),
    db: Session = Depends(get_db),
):
    return BillingService(db).process_return(
        user.tenant_id,
        payload.invoice_id,
        payload.product_id,
        payload.return_quantity,
        payload.reason,
    )