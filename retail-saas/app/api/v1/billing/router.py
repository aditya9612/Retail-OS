from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppException, ForbiddenException, NotFoundException
from app.core.security import is_tenant_wide_authorized, require_operational_write, require_permission
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.schemas.billing import (
    InvoiceCreate,
    ReturnItemRequest,
    TenderChangeRequest,
    TenderChangeResponse,
)
from app.schemas.order import InvoiceResponse
from app.schemas.cart import (
    CartCustomerResponse,
    CartCustomerSetRequest,
    CartDiscountApply,
    CartItemCreate,
    CartItemUpdate,
    CartScanRequest,
    CartStockValidationResponse,
    CartSummaryResponse,
)
from app.schemas.pos_held_cart import (
    POSHeldCartListResponse,
    POSHeldCartResponse,
    POSHoldCartRequest,
    POSRecallCartRequest,
)
from app.services.billing_service import BillingService
from app.services.cart_service import CartService
from app.services.pos_held_cart_service import POSHeldCartService


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

    if unit_price != product.selling_price:
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

        cost_price = product.cost_price or Decimal("0.00")
        if cost_price > 0 and unit_price < cost_price:
            raise AppException(
                f"Unit price cannot be lower than product cost price ({cost_price:.2f})"
            )


@router.post(
    "/cart/add-item",
    response_model=CartSummaryResponse,
    dependencies=[Depends(require_operational_write)],
)
def cart_add_item(
    payload: CartItemCreate,
    store_id: Optional[int] = Query(default=None, gt=0),
    same_state: Optional[bool] = Query(default=None),
    user: User = Depends(
        require_permission("billing:write")
    ),
    db: Session = Depends(get_db),
):
    effective_store_id = payload.store_id or store_id
    if effective_store_id is None:
        raise AppException("store_id is required in body or query")

    if user.store_id is not None and effective_store_id != user.store_id:
        raise ForbiddenException("Access denied: cannot add cart items for another store")

    if user.store_id is None:
        if not is_tenant_wide_authorized(user, db):
            raise ForbiddenException("Access denied: user has no assigned store")
        store = (
            db.query(Store)
            .filter(
                Store.id == effective_store_id,
                Store.tenant_id == user.tenant_id,
                Store.is_active.is_(True),
            )
            .first()
        )
        if not store:
            raise NotFoundException(f"Store {effective_store_id} not found")

    effective_same_state = payload.same_state if payload.same_state is not None else (same_state if same_state is not None else True)

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
        effective_store_id,
        payload.product_id,
        payload.quantity,
        payload.unit_price,
        payload.discount,
        effective_same_state,
    )

    return _to_cart_response(cart)


@router.post(
    "/cart/scan",
    response_model=CartSummaryResponse,
    dependencies=[Depends(require_operational_write)],
)
def cart_scan_item(
    payload: CartScanRequest,
    store_id: Optional[int] = Query(default=None, gt=0),
    same_state: Optional[bool] = Query(default=None),
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    """Rapid barcode scanner endpoint: Looks up product by barcode/SKU and adds/increments it in active cart."""
    effective_store_id = payload.store_id or store_id or user.store_id
    if effective_store_id is None:
        raise AppException("store_id is required in body or query")

    if user.store_id is not None and effective_store_id != user.store_id:
        raise ForbiddenException("Access denied: cannot add cart items for another store")

    if user.store_id is None:
        if not is_tenant_wide_authorized(user, db):
            raise ForbiddenException("Access denied: user has no assigned store")
        store = (
            db.query(Store)
            .filter(
                Store.id == effective_store_id,
                Store.tenant_id == user.tenant_id,
                Store.is_active.is_(True),
            )
            .first()
        )
        if not store:
            raise NotFoundException(f"Store {effective_store_id} not found")

    effective_same_state = payload.same_state if payload.same_state is not None else (same_state if same_state is not None else True)

    cart = CartService(db).scan_barcode(
        tenant_id=user.tenant_id,
        user_id=user.id,
        store_id=effective_store_id,
        barcode=payload.barcode,
        quantity=payload.quantity,
        unit_price=payload.unit_price,
        discount=payload.discount,
        same_state=effective_same_state,
    )

    return _to_cart_response(cart)


@router.put(
    "/cart/update-item",
    response_model=CartSummaryResponse,
    dependencies=[Depends(require_operational_write)],
)
def cart_update_item(
    payload: CartItemUpdate,
    user: User = Depends(
        require_permission("billing:write")
    ),
    db: Session = Depends(get_db),
):
    if payload.quantity is not None and payload.quantity == Decimal("0"):
        cart = CartService(db).remove_item(
            user.tenant_id,
            user.id,
            payload.product_id,
        )
        return _to_cart_response(cart)

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
    dependencies=[Depends(require_operational_write)],
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


@router.delete(
    "/cart/clear",
    response_model=CartSummaryResponse,
    dependencies=[Depends(require_operational_write)],
)
def cart_clear(
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    """Empties/discards the current active cart completely."""
    cart_svc = CartService(db)
    cart_svc.clear_cart(user.tenant_id, user.id)
    empty_cart = cart_svc.get_cart(user.tenant_id, user.id)
    return _to_cart_response(empty_cart)


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
    "/cart/customer",
    response_model=CartCustomerResponse,
    dependencies=[Depends(require_operational_write)],
)
def cart_set_customer(
    payload: CartCustomerSetRequest,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    """Associates a customer to the active cart by ID or phone number."""
    from app.models.customer import Customer

    customer_obj = None
    if payload.customer_id:
        customer_obj = (
            db.query(Customer)
            .filter(
                Customer.id == payload.customer_id,
                Customer.tenant_id == user.tenant_id,
            )
            .first()
        )
        if not customer_obj:
            raise NotFoundException(f"Customer {payload.customer_id} not found")
    elif payload.phone:
        clean_phone = payload.phone.strip()
        customer_obj = (
            db.query(Customer)
            .filter(
                Customer.tenant_id == user.tenant_id,
                Customer.phone == clean_phone,
            )
            .first()
        )
        if not customer_obj:
            raise NotFoundException(f"Customer with phone '{clean_phone}' not found")
    else:
        raise AppException("Either customer_id or phone must be provided")

    cart_svc = CartService(db)
    cart = cart_svc.set_customer(user.tenant_id, user.id, customer_obj.id)

    return CartCustomerResponse(
        customer_id=customer_obj.id,
        name=customer_obj.name,
        phone=customer_obj.phone,
        email=customer_obj.email,
        loyalty_points=getattr(customer_obj, "loyalty_points", Decimal("0.00")),
        credit_balance=getattr(customer_obj, "wallet_balance", getattr(customer_obj, "credit_limit", Decimal("0.00"))),
        cart=_to_cart_response(cart),
    )


@router.delete(
    "/cart/customer",
    response_model=CartSummaryResponse,
    dependencies=[Depends(require_operational_write)],
)
def cart_remove_customer(
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    """Detaches/removes the customer from the active cart."""
    cart_svc = CartService(db)
    cart = cart_svc.clear_customer(user.tenant_id, user.id)
    return _to_cart_response(cart)


@router.get(
    "/cart/validate-stock",
    response_model=CartStockValidationResponse,
)
def cart_validate_stock(
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    """Validates real-time inventory availability for all items in the active cart before checkout."""
    effective_store_id = store_id or user.store_id
    return CartService(db).validate_stock(
        tenant_id=user.tenant_id,
        user_id=user.id,
        store_id=effective_store_id,
    )


@router.post(
    "/cart/apply-discount",
    response_model=CartSummaryResponse,
    dependencies=[Depends(require_operational_write)],
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
    "/checkout",
    response_model=InvoiceResponse,
    status_code=201,
    dependencies=[Depends(require_operational_write)],
)
def billing_checkout(
    payload: InvoiceCreate,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    """Direct POS Checkout: Finalizes sale directly from active cart or provided line items, creating an invoice and linking payments."""
    effective_store_id = payload.store_id or user.store_id
    if effective_store_id is None:
        raise AppException("store_id is required")

    if user.store_id is not None and effective_store_id != user.store_id:
        raise ForbiddenException("Access denied: cannot create invoice for another store")

    if user.store_id is None:
        if not is_tenant_wide_authorized(user, db):
            raise ForbiddenException("Access denied: user has no assigned store")
        store = (
            db.query(Store)
            .filter(
                Store.id == effective_store_id,
                Store.tenant_id == user.tenant_id,
                Store.is_active.is_(True),
            )
            .first()
        )
        if not store:
            raise NotFoundException(f"Store {effective_store_id} not found")

    payload.store_id = effective_store_id
    return BillingService(db).create_invoice_from_cart(
        user.tenant_id,
        user.id,
        payload,
        user=user,
    )


@router.post(
    "/returns",
    response_model=dict,
    dependencies=[Depends(require_operational_write)],
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
        user=user,
        condition=payload.condition,
        idempotency_key=payload.idempotency_key,
        issue_credit_note=payload.issue_credit_note,
        refund_method=payload.refund_method,
    )


# ============================================================================
# POS HOLD / PARK CART ENDPOINTS (Phase 4.2)
# ============================================================================

@router.post(
    "/cart/hold",
    response_model=POSHeldCartResponse,
    dependencies=[Depends(require_operational_write)],
)
def hold_cart(
    payload: POSHoldCartRequest,
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    """Parks the user's active cart and assigns a unique hold reference."""
    return POSHeldCartService(db).hold_active_cart(user, payload)


@router.get(
    "/cart/held",
    response_model=POSHeldCartListResponse,
)
def list_held_carts(
    store_id: Optional[int] = Query(default=None, gt=0),
    status: Optional[str] = Query(default="held"),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, gt=0),
    page_size: int = Query(default=20, gt=0, le=100),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    """Lists held/parked carts for the tenant/store."""
    return POSHeldCartService(db).list_held_carts(
        user,
        store_id=store_id,
        status=status,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/cart/held/{hold_id}",
    response_model=POSHeldCartResponse,
)
def get_held_cart(
    hold_id: int,
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    """Retrieves specific held cart details."""
    return POSHeldCartService(db).get_held_cart(user, hold_id)


@router.post(
    "/cart/held/{hold_id}/recall",
    response_model=CartSummaryResponse,
    dependencies=[Depends(require_operational_write)],
)
def recall_held_cart(
    hold_id: int,
    payload: POSRecallCartRequest = POSRecallCartRequest(),
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    """Restores a held cart back into the active cart for checkout."""
    recalled_cart = POSHeldCartService(db).recall_held_cart(user, hold_id, payload)
    return _to_cart_response(recalled_cart)


@router.delete(
    "/cart/held/{hold_id}",
    response_model=POSHeldCartResponse,
    dependencies=[Depends(require_operational_write)],
)
def cancel_held_cart(
    hold_id: int,
    reason: Optional[str] = Query(default=None),
    user: User = Depends(require_permission("billing:write")),
    db: Session = Depends(get_db),
):
    """Cancels/discards a held cart."""
    return POSHeldCartService(db).cancel_held_cart(user, hold_id, reason)


# ============================================================================
# TENDER CASH / CHANGE CALCULATION ENDPOINT (Phase 4.3)
# ============================================================================

@router.post(
    "/tender-change/calculate",
    response_model=TenderChangeResponse,
    dependencies=[Depends(require_operational_write)],
)
def calculate_tender_change(
    payload: TenderChangeRequest,
    user: User = Depends(require_permission("billing:read")),
):
    """Validates cash tendered and calculates change returned to customer, with optional split tender and denomination breakdown."""
    other_payments_total = Decimal("0.00")
    if payload.other_payments:
        other_payments_total = sum(
            Decimal(str(p.amount)) for p in payload.other_payments
        )

    net_payable_cash = max(Decimal("0.00"), payload.payable_amount - other_payments_total)

    if payload.tendered_amount < net_payable_cash:
        raise AppException(
            f"Insufficient cash tendered: tendered amount ({payload.tendered_amount}) is less than payable amount ({net_payable_cash})"
        )

    change_due = (payload.tendered_amount - net_payable_cash).quantize(Decimal("0.01"))
    is_exact = change_due == Decimal("0.00")

    denominations = None
    if payload.calculate_denominations and change_due > Decimal("0.00"):
        denoms = [500, 200, 100, 50, 20, 10, 5, 2, 1]
        remaining = int(change_due)
        breakdown = {}
        for d in denoms:
            if remaining >= d:
                count = remaining // d
                remaining %= d
                breakdown[str(d)] = count
        fraction = float((change_due - Decimal(str(int(change_due)))).quantize(Decimal("0.01")))
        if fraction > 0:
            breakdown["coins"] = fraction
        denominations = breakdown

    return TenderChangeResponse(
        payable_amount=payload.payable_amount,
        tendered_amount=payload.tendered_amount,
        other_payments_total=other_payments_total.quantize(Decimal("0.01")),
        net_payable_cash=net_payable_cash.quantize(Decimal("0.01")),
        change_due=change_due,
        is_exact=is_exact,
        denominations=denominations,
        status="success",
    )
