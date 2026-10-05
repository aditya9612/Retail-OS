from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, ConflictException, ForbiddenException, NotFoundException
from app.models.customer import Customer
from app.models.pos_held_cart import POSHeldCart
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.schemas.cart import CartSummaryResponse
from app.schemas.pos_held_cart import (
    POSHeldCartListResponse,
    POSHeldCartResponse,
    POSHoldCartRequest,
    POSRecallCartRequest,
)
from app.services.cart_service import CartService


class POSHeldCartService:
    def __init__(self, db: Session):
        self.db = db

    def _check_store_access(self, user: User, store_id: int) -> None:
        user_role_name = getattr(user.role, "name", "").lower() if user.role else ""
        if user_role_name in ["admin", "owner", "superadmin"]:
            # Verify store belongs to tenant
            store = (
                self.db.query(Store)
                .filter(Store.id == store_id, Store.tenant_id == user.tenant_id)
                .first()
            )
            if not store:
                raise NotFoundException("Store not found in tenant")
            return

        # Staff/manager/cashier: must match user.store_id
        if user.store_id != store_id:
            raise ForbiddenException("Access denied: You are not authorized for this store")

    def hold_active_cart(self, user: User, data: POSHoldCartRequest) -> POSHeldCartResponse:
        if user.tenant_id is None:
            raise AppException("Tenant context required")

        if user.store_id is None:
            raise AppException("User must be assigned to a store to hold a cart")

        cart_svc = CartService(self.db)
        cart = cart_svc.get_cart(user.tenant_id, user.id)

        items = cart.get("items", [])
        if not items:
            raise AppException("Cart is empty. Cannot hold an empty cart.")

        # Ensure store_id on cart matches user's store
        store_id = cart.get("store_id") or user.store_id

        # Generate unique hold reference
        timestamp_str = datetime.utcnow().strftime("%Y%m%d%H%M")
        random_str = uuid.uuid4().hex[:4].upper()
        hold_ref = f"HOLD-{store_id}-{timestamp_str}-{random_str}"

        # Resolve customer info if customer_id is provided
        customer_id = data.customer_id or cart.get("customer_id")
        customer_name = data.customer_name
        customer_phone = data.customer_phone

        if customer_id and not (customer_name and customer_phone):
            cust = (
                self.db.query(Customer)
                .filter(Customer.id == customer_id, Customer.tenant_id == user.tenant_id)
                .first()
            )
            if cust:
                customer_name = customer_name or cust.name
                customer_phone = customer_phone or cust.phone

        held_cart = POSHeldCart(
            tenant_id=user.tenant_id,
            store_id=store_id,
            user_id=user.id,
            customer_id=customer_id,
            hold_reference=hold_ref,
            notes=data.notes,
            customer_name=customer_name,
            customer_phone=customer_phone,
            status="held",
            items_count=len(items),
            subtotal=Decimal(str(cart.get("subtotal", "0.00"))),
            discount_amount=Decimal(str(cart.get("discount_amount", "0.00"))),
            gst_amount=Decimal(str(cart.get("gst_amount", "0.00"))),
            grand_total=Decimal(str(cart.get("grand_total", "0.00"))),
            same_state=bool(cart.get("same_state", True)),
            cart_data=cart,
            held_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

        self.db.add(held_cart)
        self.db.flush()

        # Clear active cart from Redis/memory so cashier can serve next customer
        cart_svc.clear_cart(user.tenant_id, user.id)
        self.db.commit()
        self.db.refresh(held_cart)

        return self._to_response(held_cart, user)

    def list_held_carts(
        self,
        user: User,
        store_id: Optional[int] = None,
        status: Optional[str] = "held",
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> POSHeldCartListResponse:
        if user.tenant_id is None:
            raise AppException("Tenant context required")

        user_role_name = getattr(user.role, "name", "").lower() if user.role else ""
        is_owner_or_admin = user_role_name in ["admin", "owner", "superadmin"]

        query = self.db.query(POSHeldCart).filter(POSHeldCart.tenant_id == user.tenant_id)

        # Store scoping
        if not is_owner_or_admin:
            if user.store_id is None:
                raise ForbiddenException("User not assigned to any store")
            query = query.filter(POSHeldCart.store_id == user.store_id)
        else:
            if store_id is not None:
                self._check_store_access(user, store_id)
                query = query.filter(POSHeldCart.store_id == store_id)

        # Status filter
        if status:
            query = query.filter(POSHeldCart.status == status.lower())

        # Search filter
        if search:
            search_pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    POSHeldCart.hold_reference.ilike(search_pattern),
                    POSHeldCart.customer_name.ilike(search_pattern),
                    POSHeldCart.customer_phone.ilike(search_pattern),
                    POSHeldCart.notes.ilike(search_pattern),
                )
            )

        total = query.count()
        held_carts = (
            query.order_by(POSHeldCart.held_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        # Map cashier names
        user_ids = {c.user_id for c in held_carts}
        cashier_map = {}
        if user_ids:
            cashiers = self.db.query(User).filter(User.id.in_(user_ids)).all()
            cashier_map = {u.id: u.full_name for u in cashiers}

        items = []
        for c in held_carts:
            resp = POSHeldCartResponse.model_validate(c)
            resp.cashier_name = cashier_map.get(c.user_id)
            items.append(resp)

        return POSHeldCartListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=items,
        )

    def get_held_cart(self, user: User, hold_id: int) -> POSHeldCartResponse:
        if user.tenant_id is None:
            raise AppException("Tenant context required")

        held_cart = (
            self.db.query(POSHeldCart)
            .filter(POSHeldCart.id == hold_id, POSHeldCart.tenant_id == user.tenant_id)
            .first()
        )
        if not held_cart:
            raise NotFoundException("Held cart not found")

        self._check_store_access(user, held_cart.store_id)

        cashier = self.db.query(User).filter(User.id == held_cart.user_id).first()
        return self._to_response(held_cart, cashier)

    def recall_held_cart(
        self,
        user: User,
        hold_id: int,
        data: POSRecallCartRequest,
    ) -> Dict[str, Any]:
        if user.tenant_id is None:
            raise AppException("Tenant context required")

        if user.store_id is None:
            raise AppException("User must be assigned to a store to recall a cart")

        held_cart = (
            self.db.query(POSHeldCart)
            .filter(POSHeldCart.id == hold_id, POSHeldCart.tenant_id == user.tenant_id)
            .with_for_update()
            .first()
        )
        if not held_cart:
            raise NotFoundException("Held cart not found")

        self._check_store_access(user, held_cart.store_id)

        if held_cart.status != "held":
            raise ConflictException(f"Cannot recall cart: cart is already {held_cart.status}")

        cart_svc = CartService(self.db)
        active_cart = cart_svc.get_cart(user.tenant_id, user.id)

        active_items = active_cart.get("items", [])
        if active_items and not data.force_override:
            raise ConflictException(
                "Active cart contains items. Hold or clear the active cart first, or pass force_override=true"
            )

        # Validate that products in the held cart still exist and are active
        for item in held_cart.cart_data.get("items", []):
            prod_id = item.get("product_id")
            prod = (
                self.db.query(Product)
                .filter(Product.id == prod_id, Product.tenant_id == user.tenant_id)
                .first()
            )
            if not prod:
                raise AppException(f"Product ID {prod_id} from held cart no longer exists")
            if hasattr(prod, "is_active") and not prod.is_active:
                raise AppException(f"Product '{prod.name}' from held cart is currently inactive")

        # Restore cart into active Redis/memory cart
        recalled_cart_payload = {
            **held_cart.cart_data,
            "store_id": user.store_id,  # ensure current cashier store
        }
        cart_svc._save_cart(user.tenant_id, user.id, recalled_cart_payload)

        # Update held cart status to recalled
        held_cart.status = "recalled"
        held_cart.recalled_at = datetime.utcnow()
        self.db.commit()

        # Return the restored cart
        restored = cart_svc.get_cart(user.tenant_id, user.id)
        return restored

    def cancel_held_cart(
        self,
        user: User,
        hold_id: int,
        reason: Optional[str] = None,
    ) -> POSHeldCartResponse:
        if user.tenant_id is None:
            raise AppException("Tenant context required")

        held_cart = (
            self.db.query(POSHeldCart)
            .filter(POSHeldCart.id == hold_id, POSHeldCart.tenant_id == user.tenant_id)
            .with_for_update()
            .first()
        )
        if not held_cart:
            raise NotFoundException("Held cart not found")

        self._check_store_access(user, held_cart.store_id)

        if held_cart.status != "held":
            raise ConflictException(f"Cannot cancel cart: cart is already {held_cart.status}")

        held_cart.status = "cancelled"
        held_cart.cancelled_at = datetime.utcnow()
        if reason:
            existing_notes = held_cart.notes or ""
            held_cart.notes = f"{existing_notes} [Cancelled: {reason.strip()}]".strip()

        self.db.commit()
        self.db.refresh(held_cart)

        cashier = self.db.query(User).filter(User.id == held_cart.user_id).first()
        return self._to_response(held_cart, cashier)

    def _to_response(self, held_cart: POSHeldCart, cashier: Optional[User] = None) -> POSHeldCartResponse:
        resp = POSHeldCartResponse.model_validate(held_cart)
        if cashier:
            resp.cashier_name = cashier.full_name
        return resp

