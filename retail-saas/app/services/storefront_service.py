from datetime import datetime
from decimal import Decimal
import json
import uuid
from typing import Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.core.logger import logger
from app.core.redis_client import get_redis
from app.models.category import Category
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.store import Store
from app.schemas.storefront import (
    StorefrontCartItemResponse,
    StorefrontCartResponse,
    StorefrontCategoryItem,
    StorefrontCheckoutRequest,
    StorefrontCheckoutResponse,
    StorefrontCustomerProfileResponse,
    StorefrontOrderDetailResponse,
    StorefrontOrderSummary,
    StorefrontProductItem,
    StorefrontProductListResponse,
)


class StorefrontService:
    def __init__(self, db: Session):
        self.db = db
        try:
            self.redis = get_redis()
        except Exception:
            self.redis = None
        self._local_cart_store: Dict[str, dict] = {}

    def _cart_key(self, tenant_id: int, customer_id: int) -> str:
        return f"storefront:cart:{tenant_id}:{customer_id}"

    def _load_cart_data(self, tenant_id: int, customer_id: int) -> dict:
        key = self._cart_key(tenant_id, customer_id)
        if self.redis:
            try:
                raw = self.redis.get(key)
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        return self._local_cart_store.get(key, {"items": {}})

    def _save_cart_data(self, tenant_id: int, customer_id: int, cart: dict) -> None:
        key = self._cart_key(tenant_id, customer_id)
        if self.redis:
            try:
                self.redis.setex(key, 86400 * 7, json.dumps(cart))
            except Exception:
                pass
        self._local_cart_store[key] = cart

    # --------------------------------------------------------------------------
    # 1. Catalog & Categories
    # --------------------------------------------------------------------------

    def get_categories(self, tenant_id: int) -> List[StorefrontCategoryItem]:
        categories = (
            self.db.query(Category)
            .filter(Category.tenant_id == tenant_id, Category.is_active.is_(True))
            .order_by(Category.name.asc())
            .all()
        )
        return [
            StorefrontCategoryItem(
                id=c.id,
                name=c.name,
                description=c.description,
            )
            for c in categories
        ]

    def get_products(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        category_id: Optional[int] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> StorefrontProductListResponse:
        query = self.db.query(Product).filter(
            Product.tenant_id == tenant_id,
            Product.is_active.is_(True),
        )

        if category_id:
            query = query.filter(Product.category_id == category_id)

        if search:
            search_clean = search.strip()
            query = query.filter(
                (Product.name.ilike(f"%{search_clean}%"))
                | (Product.barcode == search_clean)
                | (Product.sku.ilike(f"%{search_clean}%"))
            )

        total = query.count()
        products = (
            query.order_by(Product.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        # Map inventory stock if store_id provided
        stock_map = {}
        if store_id:
            p_ids = [p.id for p in products]
            if p_ids:
                inv_records = (
                    self.db.query(Inventory)
                    .filter(
                        Inventory.tenant_id == tenant_id,
                        Inventory.store_id == store_id,
                        Inventory.product_id.in_(p_ids),
                    )
                    .all()
                )
                for inv in inv_records:
                    stock_map[inv.product_id] = inv.quantity

        items = []
        for p in products:
            curr_stock = stock_map.get(p.id, 999) if store_id else 999
            selling_price = getattr(p, "selling_price", getattr(p, "price", Decimal("0.00")))
            mrp_val = getattr(p, "mrp", selling_price) or selling_price
            items.append(
                StorefrontProductItem(
                    id=p.id,
                    name=p.name,
                    sku=p.sku,
                    price=Decimal(str(selling_price)),
                    mrp=Decimal(str(mrp_val)),
                    unit=getattr(p, "unit", "pcs"),
                    category_id=p.category_id,
                    category_name=p.category.name if p.category else None,
                    in_stock=(curr_stock > 0),
                    stock_quantity=max(0, curr_stock),
                    image_url=None,
                )
            )

        return StorefrontProductListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    # --------------------------------------------------------------------------
    # 2. Shopping Cart
    # --------------------------------------------------------------------------

    def get_cart(self, tenant_id: int, customer_id: int) -> StorefrontCartResponse:
        cart_data = self._load_cart_data(tenant_id, customer_id)
        raw_items = cart_data.get("items", {})

        cart_items: List[StorefrontCartItemResponse] = []
        subtotal = Decimal("0.00")
        total_items = 0

        if raw_items:
            product_ids = [int(pid) for pid in raw_items.keys()]
            products = (
                self.db.query(Product)
                .filter(Product.tenant_id == tenant_id, Product.id.in_(product_ids))
                .all()
            )
            prod_dict = {p.id: p for p in products}

            for pid_str, item_info in raw_items.items():
                pid = int(pid_str)
                product = prod_dict.get(pid)
                if not product or not product.is_active:
                    continue

                qty = int(item_info.get("quantity", 1))
                price = Decimal(str(product.selling_price))
                item_total = price * qty

                cart_items.append(
                    StorefrontCartItemResponse(
                        product_id=product.id,
                        name=product.name,
                        unit_price=price,
                        quantity=qty,
                        total_price=item_total,
                        unit=getattr(product, "unit", "pcs"),
                    )
                )
                subtotal += item_total
                total_items += qty

        # Estimated Tax (Intra-state GST approximation)
        tax_amount = (subtotal * Decimal("0.05")).quantize(Decimal("0.01"))
        total_amount = subtotal + tax_amount

        return StorefrontCartResponse(
            items=cart_items,
            subtotal=subtotal,
            discount_amount=Decimal("0.00"),
            tax_amount=tax_amount,
            total_amount=total_amount,
            total_items=total_items,
        )

    def add_to_cart(
        self,
        tenant_id: int,
        customer_id: int,
        product_id: int,
        quantity: int = 1,
    ) -> StorefrontCartResponse:
        product = (
            self.db.query(Product)
            .filter(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
            )
            .first()
        )
        if not product:
            raise NotFoundException(f"Product {product_id} not found or inactive")

        cart_data = self._load_cart_data(tenant_id, customer_id)
        items = cart_data.setdefault("items", {})

        pid_str = str(product_id)
        current_qty = items.get(pid_str, {}).get("quantity", 0)
        new_qty = current_qty + quantity
        items[pid_str] = {"quantity": new_qty}

        self._save_cart_data(tenant_id, customer_id, cart_data)
        return self.get_cart(tenant_id, customer_id)

    def update_cart_item(
        self,
        tenant_id: int,
        customer_id: int,
        product_id: int,
        quantity: int,
    ) -> StorefrontCartResponse:
        cart_data = self._load_cart_data(tenant_id, customer_id)
        items = cart_data.setdefault("items", {})

        pid_str = str(product_id)
        if quantity <= 0:
            items.pop(pid_str, None)
        else:
            items[pid_str] = {"quantity": quantity}

        self._save_cart_data(tenant_id, customer_id, cart_data)
        return self.get_cart(tenant_id, customer_id)

    def remove_from_cart(
        self,
        tenant_id: int,
        customer_id: int,
        product_id: int,
    ) -> StorefrontCartResponse:
        return self.update_cart_item(tenant_id, customer_id, product_id, quantity=0)

    def clear_cart(self, tenant_id: int, customer_id: int) -> None:
        key = self._cart_key(tenant_id, customer_id)
        if self.redis:
            try:
                self.redis.delete(key)
            except Exception:
                pass
        self._local_cart_store.pop(key, None)

    # --------------------------------------------------------------------------
    # 3. Checkout & Order Placement
    # --------------------------------------------------------------------------

    def checkout(
        self,
        tenant_id: int,
        customer: Customer,
        payload: StorefrontCheckoutRequest,
    ) -> StorefrontCheckoutResponse:
        cart = self.get_cart(tenant_id, customer.id)
        if not cart.items:
            raise AppException("Your cart is empty. Please add items before checkout.")

        # Find store for this tenant (main store or first active store)
        store = (
            self.db.query(Store)
            .filter(Store.tenant_id == tenant_id, Store.is_active.is_(True))
            .order_by(Store.is_main.desc(), Store.id.asc())
            .first()
        )
        if not store:
            raise NotFoundException("Store outlet not available for checkout")

        # Resolve delivery address
        final_address = payload.delivery_address or customer.address or "Store Pickup Counter"

        # Check wallet balance if payment_method is wallet
        if payload.payment_method == "wallet":
            from app.models.customer import CustomerWallet
            wallet = self.db.query(CustomerWallet).filter(CustomerWallet.customer_id == customer.id).first()
            wallet_bal = wallet.balance if wallet else Decimal("0.00")
            if wallet_bal < cart.total_amount:
                raise AppException(f"Insufficient wallet balance (Available: Rs.{wallet_bal}, Required: Rs.{cart.total_amount})")
            wallet.balance -= cart.total_amount

        # Generate unique order number
        order_uid = uuid.uuid4().hex[:6].upper()
        timestamp_str = datetime.utcnow().strftime("%y%m%d%H%M")
        order_number = f"ORD-ONL-{timestamp_str}-{order_uid}"

        # Intra-state tax splitting (half CGST, half SGST)
        half_tax = (cart.tax_amount / Decimal("2")).quantize(Decimal("0.01"))

        # Create Order
        order = Order(
            tenant_id=tenant_id,
            store_id=store.id,
            customer_id=customer.id,
            order_number=order_number,
            order_type="online",
            status="pending",
            subtotal=cart.subtotal,
            discount_amount=cart.discount_amount,
            cgst_amount=half_tax,
            sgst_amount=half_tax,
            igst_amount=Decimal("0.00"),
            tax_amount=cart.tax_amount,
            round_off=Decimal("0.00"),
            total_amount=cart.total_amount,
            payment_method=payload.payment_method.upper(),
            payment_status="paid" if payload.payment_method == "wallet" else "pending",
            notes=f"Mode: {payload.delivery_type.capitalize()} | Address: {final_address} | {payload.notes or ''}".strip(),
        )
        self.db.add(order)
        self.db.flush()

        # Create OrderItems
        for item in cart.items:
            half_item_tax = ((item.total_price * Decimal("0.05")) / Decimal("2")).quantize(Decimal("0.01"))
            order_item = OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount_amount=Decimal("0.00"),
                cgst_amount=half_item_tax,
                sgst_amount=half_item_tax,
                igst_amount=Decimal("0.00"),
                tax_amount=half_item_tax * Decimal("2"),
                total_amount=item.total_price + (half_item_tax * Decimal("2")),
                notes=f"Online item: {item.name}",
            )
            self.db.add(order_item)

        # Clear cart upon order creation
        self.clear_cart(tenant_id, customer.id)

        self.db.commit()
        self.db.refresh(order)

        # Asynchronously send WhatsApp confirmation if configured
        try:
            from app.tasks.whatsapp_tasks import send_order_confirmation_task
            send_order_confirmation_task.delay(
                phone=customer.phone,
                order_number=order.order_number,
                total=str(order.total_amount),
                tenant_id=tenant_id,
                store_id=store.id,
                store_name=store.name,
            )
        except Exception as exc:
            logger.info("WhatsApp order confirmation queued/skipped: %s", exc)

        return StorefrontCheckoutResponse(
            order_id=order.id,
            order_number=order.order_number,
            status=order.status,
            total_amount=order.total_amount,
            delivery_type=payload.delivery_type,
            payment_method=payload.payment_method,
            payment_status=order.payment_status,
            message="Order placed successfully! The store has received your order.",
            created_at=order.created_at or datetime.utcnow(),
        )

    # --------------------------------------------------------------------------
    # 4. Customer Orders & Self-Service
    # --------------------------------------------------------------------------

    def get_my_orders(
        self,
        tenant_id: int,
        customer_id: int,
    ) -> List[StorefrontOrderSummary]:
        orders = (
            self.db.query(Order)
            .filter(
                Order.tenant_id == tenant_id,
                Order.customer_id == customer_id,
            )
            .order_by(Order.id.desc())
            .all()
        )
        return [
            StorefrontOrderSummary(
                id=o.id,
                order_number=o.order_number,
                status=o.status,
                order_type=o.order_type,
                total_amount=o.total_amount,
                payment_method=o.payment_method,
                payment_status=o.payment_status,
                items_count=len(o.items) if o.items else 0,
                created_at=o.created_at or datetime.utcnow(),
            )
            for o in orders
        ]

    def get_order_details(
        self,
        tenant_id: int,
        customer_id: int,
        order_id: int,
    ) -> StorefrontOrderDetailResponse:
        order = (
            self.db.query(Order)
            .filter(
                Order.id == order_id,
                Order.tenant_id == tenant_id,
                Order.customer_id == customer_id,
            )
            .first()
        )
        if not order:
            raise NotFoundException(f"Order #{order_id} not found")

        items_list = []
        for it in order.items:
            items_list.append(
                {
                    "product_id": it.product_id,
                    "product_name": it.product.name if it.product else f"Product #{it.product_id}",
                    "quantity": it.quantity,
                    "unit_price": float(it.unit_price),
                    "total_amount": float(it.total_amount),
                }
            )

        invoice_url = None
        if order.invoice:
            invoice_url = f"/api/v1/invoices/{order.invoice.id}/pdf"

        return StorefrontOrderDetailResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            subtotal=order.subtotal,
            tax_amount=order.tax_amount,
            discount_amount=order.discount_amount,
            total_amount=order.total_amount,
            payment_method=order.payment_method,
            payment_status=order.payment_status,
            notes=order.notes,
            created_at=order.created_at or datetime.utcnow(),
            items=items_list,
            invoice_url=invoice_url,
        )

    def get_customer_profile(
        self,
        tenant_id: int,
        customer_id: int,
    ) -> StorefrontCustomerProfileResponse:
        customer = (
            self.db.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == tenant_id)
            .first()
        )
        if not customer:
            raise NotFoundException(f"Customer #{customer_id} not found")

        from app.models.customer import CustomerWallet
        wallet = self.db.query(CustomerWallet).filter(CustomerWallet.customer_id == customer.id).first()
        wallet_balance = wallet.balance if wallet else Decimal("0.00")

        return StorefrontCustomerProfileResponse(
            customer_id=customer.id,
            name=customer.name,
            phone=customer.phone,
            email=customer.email,
            address=customer.address,
            loyalty_points=customer.loyalty_points or 0,
            wallet_balance=wallet_balance,
            outstanding_balance=customer.outstanding_balance or Decimal("0.00"),
            credit_limit=customer.credit_limit or Decimal("0.00"),
            status=customer.status,
        )
